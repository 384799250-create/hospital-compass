# 官网专科依据自动沉淀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已登记医院官网中明确验证的专科等级依据异步写入正式 SQLite 数据库，并在后续任意地域范围的推荐中复用。

**Architecture:** 新增专用存储模块负责官网域名准入、schema 兼容迁移、幂等写入和 180 天复核失效。实时检索在候选医院完成本地身份映射后交由 FastAPI 后台任务持久化；`tertiary_rows()` 读取原文、URL 与状态并复用现有评分和展示链路。

**Tech Stack:** Python 3.12、FastAPI `BackgroundTasks`、SQLite、pytest、现有 `SearchDocument`。

---

## File Structure

- Create: `apps/api/app/official_specialty_evidence_store.py` - 官网准入、迁移和三层表事务写入。
- Create: `apps/api/tests/test_official_specialty_evidence_store.py` - 存储模块隔离测试。
- Modify: `apps/api/app/tertiary_store.py` - 读取原文、链接、状态并兼容旧库。
- Modify: `apps/api/app/main.py` - 构造写入项目并调度后台任务。
- Modify: `apps/api/app/realtime_search.py` - 证据提取保留完整原文。
- Modify: `apps/api/tests/test_tertiary_store.py`、`apps/api/tests/test_contracts.py`、`apps/api/tests/test_realtime_search.py` - 回归测试。

### Task 1: 建立官网证据存储接口

**Files:**
- Create: `apps/api/app/official_specialty_evidence_store.py`
- Create: `apps/api/tests/test_official_specialty_evidence_store.py`

- [ ] **Step 1: 写失败测试：合法官网来源写入三层表**

创建最小正式库 fixture，含 `hospitals(hospital_id, canonical_name, official_domain)`、`departments(department_id, standard_name)`、`sources`、`evidence`、`department_capabilities`。插入 `H1/合浦县人民医院/hospital.example.org` 和 `D1/神经内科`。新增：

```python
def test_persist_official_capability_writes_source_evidence_and_capability(tmp_path):
    database = _create_official_database(tmp_path)
    report = persist_official_capabilities([
        OfficialSpecialtyEvidence(
            hospital_id='H1', department='神经内科',
            strength_level='广西医疗卫生重点学科（县级）',
            quoted_text='神经内科为广西医疗卫生重点学科（县级）',
            evidence_url='https://hospital.example.org/about',
            source_title='医院简介', fetched_at='2026-08-17T00:00:00+00:00',
        ),
    ], path=database)
    assert report.inserted == 1
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT is_official FROM sources').fetchone()[0] == 1
        assert db.execute(
            'SELECT specialty_strength_level, evidence_summary, evidence_url, verification_status '
            'FROM department_capabilities'
        ).fetchone() == (
            '广西医疗卫生重点学科（县级）',
            '神经内科为广西医疗卫生重点学科（县级）',
            'https://hospital.example.org/about', '官网自动核验',
        )
```

- [ ] **Step 2: 确认失败**

运行 `python -m pytest apps/api/tests/test_official_specialty_evidence_store.py::test_persist_official_capability_writes_source_evidence_and_capability -v`。预期：`ModuleNotFoundError`。

- [ ] **Step 3: 实现最小模块**

定义以下接口：

```python
@dataclass(frozen=True)
class OfficialSpecialtyEvidence:
    hospital_id: str
    department: str
    strength_level: str
    quoted_text: str
    evidence_url: str
    source_title: str
    fetched_at: str

@dataclass(frozen=True)
class PersistReport:
    inserted: int
    refreshed: int
    rejected: int

def persist_official_capabilities(items: Iterable[OfficialSpecialtyEvidence], *, path: Path) -> PersistReport: ...
```

仅在缺列时给 `department_capabilities` 增加 `evidence_fingerprint TEXT`、`last_verified_at TEXT`，并创建：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_auto_capability_fingerprint
ON department_capabilities(hospital_id, department_id, evidence_url, evidence_fingerprint)
WHERE verification_status = '官网自动核验';
```

用以下规则校验域名：

```python
def _matches_official_domain(url: str, official_domain: str) -> bool:
    source = urlparse(url)
    registered = urlparse(official_domain if '://' in official_domain else f'https://{official_domain}')
    host, domain = (source.hostname or '').casefold(), (registered.hostname or '').casefold()
    return source.scheme == 'https' and bool(domain) and (host == domain or host.endswith(f'.{domain}'))
```

在同一事务中校验医院和标准科室存在、确认等级可被现有 `_specialty_level_bonus()` 识别、计算 `sha256(quoted_text)`，再写入或刷新 `sources`（`source_type='医院官网'`、`is_official=1`）、`evidence`（`review_status='官网自动核验'`）和 `department_capabilities`（`verification_status='官网自动核验'`）。

- [ ] **Step 4: 确认通过并提交**

运行 `python -m pytest apps/api/tests/test_official_specialty_evidence_store.py::test_persist_official_capability_writes_source_evidence_and_capability -v`，预期 `1 passed`。随后运行 `git add apps/api/app/official_specialty_evidence_store.py apps/api/tests/test_official_specialty_evidence_store.py` 和 `git commit -m "feat: persist verified official specialty evidence"`。

### Task 2: 覆盖拒绝、去重、人工优先和过期规则

**Files:**
- Modify: `apps/api/app/official_specialty_evidence_store.py`
- Modify: `apps/api/tests/test_official_specialty_evidence_store.py`

- [ ] **Step 1: 写失败测试**

参数化测试传入以下组合，全部断言 `inserted == 0` 且三个表无新增：HTTP URL、`https://third-party.example.org/about`、不存在医院 ID、`department='不存在科室'`、空原文、`strength_level='特色专科介绍'`。

重复调用同一条 `OfficialSpecialtyEvidence`，断言能力记录数仍为 1、第二次 `refreshed == 1`。预置人工 `verification_status='已核验'`、`strength_level='国家级重点'` 行后写入县级自动项，断言人工行完全不变。预置自动行 `last_verified_at='2026-02-01T00:00:00+00:00'`，断言过期后其状态变为“待复核”，人工行仍为“已核验”。

- [ ] **Step 2: 确认失败**

运行 `python -m pytest apps/api/tests/test_official_specialty_evidence_store.py -v`。预期：拒绝、重复或过期用例失败。

- [ ] **Step 3: 实现完整规则**

实现：

```python
REVIEW_WINDOW = timedelta(days=180)

def expire_stale_official_capabilities(*, path: Path, now: datetime) -> int:
    cutoff = (now - REVIEW_WINDOW).isoformat()
    with _connect(path) as db:
        cursor = db.execute(
            "UPDATE department_capabilities SET verification_status = ? "
            "WHERE verification_status = ? AND last_verified_at < ?",
            ('待复核', '官网自动核验', cutoff),
        )
    return cursor.rowcount
```

每次持久化前执行过期处理；相同指纹再次命中官网时刷新 `last_verified_at` 并恢复“官网自动核验”。所有拒绝检查必须发生在插入 `sources` 前；自动逻辑的 `UPDATE` 只能匹配“官网自动核验”，不得更新人工行。

- [ ] **Step 4: 确认通过并提交**

运行 `python -m pytest apps/api/tests/test_official_specialty_evidence_store.py -v`，预期该文件全绿。随后运行 `git add apps/api/app/official_specialty_evidence_store.py apps/api/tests/test_official_specialty_evidence_store.py` 和 `git commit -m "feat: guard and expire official specialty evidence"`。

### Task 3: 扩展读取层并过滤待复核依据

**Files:**
- Modify: `apps/api/app/tertiary_store.py`
- Modify: `apps/api/tests/test_tertiary_store.py`

- [ ] **Step 1: 写失败测试**

给现有能力 fixture 增加 `evidence_summary`、`evidence_url`、`verification_status`，并断言读取结果含：

```python
{
    'department': '心血管内科', 'diagnosis_scope': '冠心病介入诊疗',
    'strength_level': '国家级重点', 'evidence_summary': '官网原文',
    'evidence_url': 'https://hospital.example/cardio',
    'verification_status': '官网自动核验',
}
```

再添加“待复核”行，断言不会出现在 `specialty_capabilities`。

- [ ] **Step 2: 确认失败**

运行 `python -m pytest apps/api/tests/test_tertiary_store.py -v`。预期：新字段丢失、待复核行未过滤。

- [ ] **Step 3: 实现动态列兼容**

在 `tertiary_rows()` 读取 `PRAGMA table_info(department_capabilities)`，使用：

```python
summary = 'dc.evidence_summary' if 'evidence_summary' in capability_columns else "''"
url = 'dc.evidence_url' if 'evidence_url' in capability_columns else "''"
status = 'COALESCE(dc.verification_status, \'已核验\')' if 'verification_status' in capability_columns else "'已核验'"
```

把字段加入查询和能力字典。跳过状态属于 `{'待复核', '来源不可访问', '失效'}` 的行；缺少状态列的旧记录按“已核验”保留。

- [ ] **Step 4: 确认通过并提交**

运行 `python -m pytest apps/api/tests/test_tertiary_store.py -v`，预期全绿。随后运行 `git add apps/api/app/tertiary_store.py apps/api/tests/test_tertiary_store.py` 和 `git commit -m "feat: expose verified official specialty evidence"`。

### Task 4: 在实时检索中异步提交官网依据

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/realtime_search.py`
- Modify: `apps/api/tests/test_contracts.py`

- [ ] **Step 1: 写端点失败测试**

模拟本地候选不足十个和以下来源：

```python
SearchDocument(
    title='医院简介 - 合浦县人民医院',
    url='https://hospital.example.org/about',
    snippet='神经内科为广西医疗卫生重点学科（县级）。',
    fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
)
```

模拟同名、同市、`id='H1'`、`official_domain='hospital.example.org'` 的数据库行。monkeypatch `main.persist_official_capabilities`，调用 `POST /v1/realtime-hospital-search`，断言 `200/OK` 且后台收到一条 `hospital_id='H1'`、`department='神经内科'` 的项目。把 URL 改为第三方域名时断言后台没有项目；让 mock 抛 `sqlite3.Error` 时断言响应仍是 `200/OK`。

- [ ] **Step 2: 确认失败**

运行 `python -m pytest apps/api/tests/test_contracts.py -k "official_specialty" -v`。预期：端点尚未提交任务。

- [ ] **Step 3: 实现安全后台调度**

从 `fastapi` 导入 `BackgroundTasks`，并导入存储模块。端点签名改为：

```python
async def realtime_hospital_search(
    request: RealtimeSearchRequest, background_tasks: BackgroundTasks,
) -> dict[str, object]: ...
```

在 `external_candidates = _apply_database_identity(...)` 后构造 `_official_specialty_evidence_items(external_candidates, directions, database_rows)`。helper 必须按规范化医院名和城市匹配医院 ID，按登记 `official_domain` 先过滤 URL，调用 `_source_capability_evidence()` 获取方向、等级和原文。只有项目非空时调度：

```python
background_tasks.add_task(
    _persist_official_specialty_evidence_safely, items, tertiary_database_path(),
)
```

安全 wrapper 捕获 `sqlite3.Error`、`ValueError` 并 `logger.warning(..., exc_info=True)`。同步修改 `_source_capability_evidence()`，将完整句子放到 `diagnosis_scope`，使展示和沉淀共享同一原文。

- [ ] **Step 4: 确认通过并提交**

运行 `python -m pytest apps/api/tests/test_contracts.py -k "official_specialty" -v`，预期全绿。随后运行 `git add apps/api/app/main.py apps/api/app/realtime_search.py apps/api/tests/test_contracts.py` 和 `git commit -m "feat: learn verified specialty evidence from official sites"`。

### Task 5: 验证跨范围复用和全量回归

**Files:**
- Modify: `apps/api/tests/test_contracts.py`
- Modify: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 写跨范围失败测试**

先调用 `persist_official_capabilities()` 写入合浦县人民医院“神经内科/县级重点学科”，再由 `tertiary_rows(path=database)` 构造候选，在 `scope='province'` 调用 `rank_candidates()`，断言：

```python
assert ranked[0]['score_breakdown']['specialty'] == 54.38
assert ranked[0]['specialty_evidence'][0]['verification_status'] == '官网自动核验'
assert ranked[0]['specialty_evidence'][0]['evidence_url'] == 'https://hospital.example.org/about'
```

- [ ] **Step 2: 确认失败并完成透传**

运行 `python -m pytest apps/api/tests/test_contracts.py -k "official_specialty" apps/api/tests/test_realtime_search.py -v`。修复 `_directory_fallback_candidates()`、`_visible_evidence()`、`_deduplicate_evidence()` 对 `evidence_summary`、`evidence_url`、`verification_status` 的透传；不得改动评分权重或 `_specialty_level_bonus()` 的现有分值。

- [ ] **Step 3: 执行全量验证和手动检查**

运行：

```powershell
python -m pytest apps/api/tests -q
Set-Location apps/web
npm.cmd test -- --run
npm.cmd run build
Invoke-RestMethod http://127.0.0.1:8001/health
```

预期：后端、前端和构建通过；既有 bundle 大小警告单独记录。浏览器中先完成一次合浦县“神经内科”的官网证据命中查询，再切换到省级范围；预期仍显示“官网自动核验”、原文和 URL，且不阻塞或跳转当前页面。

- [ ] **Step 4: 提交最终回归**

运行 `git add apps/api/tests/test_contracts.py apps/api/tests/test_realtime_search.py` 和 `git commit -m "test: cover official evidence reuse across scopes"`。
