# 校准专科实力评分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有医院以综合实力形成稳定的专科基础分，并仅以当前方向的直接专科证据提供受等级限制的增量。

**Architecture:** 后端在 `rank_candidates` 中先计算既有医院综合实力，再由其生成专科基础分；一个纯函数从当前方向的结构化能力、官网片段和专科排名中选择最高证据增量。前端保留五项评分详情：无直接专科依据时显示后端返回的基础分，并额外说明该项尚无直接依据，不再抹除该分数或重算总分。

**Tech Stack:** Python 3.11、FastAPI/Pydantic、pytest、TypeScript、React、Vitest。

---

## 文件结构

- 修改：`apps/api/app/realtime_search.py` - 专科基础分、证据增量分类、排名增量和遗留结果归一化。
- 修改：`apps/api/tests/test_realtime_search.py` - 后端评分校准、等级边界、排名上限及遗留归一化回归测试。
- 修改：`apps/web/lib/result-score.ts` - 不再删除无直接证据医院的后端专科基础分。
- 修改：`apps/web/tests/result-score.test.ts` - 验证前端保留后端专科基础分和总分。
- 修改：`apps/web/app/page.tsx` - 评分详情在保留数值的同时提示“暂无直接专科依据”。
- 修改：`apps/web/app/page.module.css` - 为专科依据状态提示提供紧凑、非阻塞的文字样式。
- 修改：`apps/web/tests/result-controls.test.tsx` - 验证详情同时显示基础分和缺少直接依据的提示。

### Task 1: 后端评分校准的失败测试

**Files:**
- Modify: `apps/api/tests/test_realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 写入两个医院的比较回归测试**

在 `test_rank_result_exposes_source_backed_capability_before_general_ranking` 之后新增以下测试。两个候选医院使用相同地点、相同抓取时间和可用官网，避免地理、时效与服务分影响断言。

```python
def test_county_specialty_evidence_is_a_limited_bonus_on_institutional_strength():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    county = HospitalCandidate(
        name='县级医院', city='北海市', province='广西壮族自治区', district='合浦县',
        public_capability=77.3,
        sources=[SearchDocument(
            title='县级医院简介', url='https://county.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。', fetched_at=fetched_at,
        )],
    )
    flagship = HospitalCandidate(
        name='综合实力医院', city='南宁市', province='广西壮族自治区', district='青秀区',
        public_capability=97.0,
        sources=[SearchDocument(
            title='综合实力医院简介', url='https://flagship.example.org/about',
            snippet='三级甲等综合医院。', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [county, flagship], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '', 'district': ''},
        scope='province', as_of=fetched_at,
    )

    specialty = {item['name']: item['score_breakdown']['specialty'] for item in ranked}
    assert specialty['县级医院'] == 54.38
    assert specialty['综合实力医院'] == 58.2
    assert ranked[0]['name'] == '综合实力医院'
```

- [ ] **Step 2: 写入等级解析与“不叠加”测试**

```python
@pytest.mark.parametrize(("snippet", "expected"), [
    ('神经内科为县级重点学科。', 54.38),
    ('神经内科为北海市重点学科。', 58.38),
    ('神经内科为广西省级重点专科。', 64.38),
    ('神经内科为国家临床重点专科。', 71.38),
])
def test_specialty_bonus_uses_the_explicit_evidence_level(snippet, expected):
    candidate = HospitalCandidate(
        name='分级医院', city='北海市', public_capability=77.3,
        sources=[SearchDocument(
            title='神经内科简介', url='https://example.org/about', snippet=snippet,
            fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
        )],
    )
    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'},
        scope='city', as_of=datetime(2026, 8, 17, tzinfo=UTC),
    )
    assert ranked[0]['score_breakdown']['specialty'] == expected


def test_multiple_specialty_evidence_records_use_only_the_highest_bonus():
    candidate = HospitalCandidate(
        name='多证据医院', city='北海市', public_capability=77.3,
        sources=[SearchDocument(
            title='医院简介', url='https://example.org/about',
            snippet='神经内科为县级重点学科；神经内科为北海市重点学科。',
            fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
        )],
    )
    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'},
        scope='city', as_of=datetime(2026, 8, 17, tzinfo=UTC),
    )
    assert ranked[0]['score_breakdown']['specialty'] == 58.38
```

- [ ] **Step 3: 更新旧规则测试为新规则**

将 `test_specialty_score_is_zero_without_direct_specialty_evidence` 更名为 `test_specialty_score_uses_institutional_baseline_without_direct_evidence`，设置 `public_capability=72.1` 并断言 `43.26`。将 `test_normalize_result_specialty_score_repairs_legacy_hidden_specialty_points` 的断言改为专科 `43.26`、总分 `71.916`，以验证遗留结果由医院综合实力重建基础分。

- [ ] **Step 4: 运行新增测试，确认其因实现缺失而失败**

Run: `python -m pytest -q tests/test_realtime_search.py -k "county_specialty_evidence or specialty_bonus_uses or multiple_specialty_evidence or institutional_baseline_without or normalize_result_specialty"`

Expected: FAIL。当前代码仍将无直接依据专科分归零，且把“重点学科（县级）”按通用重点学科算为高分。

### Task 2: 实现统一的专科基础分与证据增量

**Files:**
- Modify: `apps/api/app/realtime_search.py:450-508`
- Modify: `apps/api/app/realtime_search.py:1019-1113`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 定义明确、不可叠加的证据增量常量与帮助函数**

在 `_DIRECT_SPECIALTY_MARKERS` 附近新增常量和函数。使用大小写无关的当前方向同义词匹配，并先识别“县级”，避免它落入通用“重点学科”匹配。

```python
_SPECIALTY_BASELINE_RATIO = 0.60
_SPECIALTY_RANKING_BONUS_CAP = 30.0


def _specialty_base_score(institutional_strength: float) -> float:
    return round(max(0.0, min(100.0, institutional_strength)) * _SPECIALTY_BASELINE_RATIO, 4)


def _specialty_level_bonus(text: str) -> float:
    value = text.casefold()
    if any(marker in value for marker in ('国家临床重点专科', '国家重点专科', '国家医学中心', '国家区域医疗中心')):
        return 25.0
    if any(marker in value for marker in ('省级区域医疗中心', '省级重点专科', '省重点专科', '省级重点学科')):
        return 18.0
    if '县级' in value and any(marker in value for marker in ('重点学科', '重点专科')):
        return 8.0
    if any(marker in value for marker in ('市级重点学科', '市重点学科', '市级重点专科', '市重点专科', '院内临床重点专科')):
        return 12.0
    if any(marker in value for marker in ('重点学科', '重点专科', '专病中心', '诊疗中心', '医学中心', '特色专科')):
        return 12.0
    return 0.0
```

新增 `_specialty_evidence_bonus(candidate, source, directions, profile)`：收集当前方向匹配的 `capability_evidence` 文本和来源中按句子拆分的文本，映射到 `_specialty_level_bonus`；当前方向仅能从普通结构化科室记录或 `candidate.specialties` 确认时，返回 `2.0`；否则返回 `0.0`。返回所有匹配记录的 `max`，不能累加。

- [ ] **Step 2: 将专科排名从“专科分地板”改为有上限的排名增量**

新增帮助函数，复用现有 `_ranking_specialty_match`、`_ranking_scope_weight` 与已存储的 `score`：

```python
def _specialty_ranking_bonus(ranked_specialties: Sequence[tuple[dict[str, object], int, float]]) -> float:
    if not ranked_specialties:
        return 0.0
    exact = [item for item in ranked_specialties if item[1] == 2]
    selected = exact or list(ranked_specialties)
    weighted_score = max(
        float(item[0].get('score') or 0)
        * _ranking_scope_weight(item[0].get('ranking_scope') or item[0].get('scope') or item[0].get('ranking_name'))
        * item[2]
        for item in selected
    )
    return round(min(_SPECIALTY_RANKING_BONUS_CAP, max(0.0, weighted_score) * 0.30), 4)
```

在 `rank_candidates` 中将 `capability = _institutional_strength_score(...)` 移到专科计算前，并替换现有 `_specialty_strength_score`、`ranking_floor`、无依据归零和综合排名 `82` 分封顶逻辑：

```python
capability = _institutional_strength_score(candidate, source, profile)
specialty_bonus = _specialty_evidence_bonus(candidate, source, directions, profile)
specialty = _specialty_base_score(capability)
specialty = min(100.0, specialty + specialty_bonus + _specialty_ranking_bonus(selected_rankings))
specialty = round(specialty, 4)
```

保留 `has_direct_specialty_evidence` 的现有布尔语义，仅供来源展示与前端提示使用；它不得再覆盖或归零 `specialty`。

- [ ] **Step 3: 修正遗留结果归一化**

将 `normalize_result_specialty_score` 改为：当 `has_direct_specialty_evidence is False` 时，读取 `score_breakdown['public_capability']`，写入 `_specialty_base_score(...)`，并使用既有 `RANKING_WEIGHTS` 重算 `score` 和 `score_reasons`。当缺少完整评分明细时，保留原总分，避免猜测缺失维度。

```python
if result.get('has_direct_specialty_evidence') is False:
    breakdown = dict(result.get('score_breakdown') or {})
    breakdown['specialty'] = _specialty_base_score(float(breakdown.get('public_capability') or 0))
    # 保留既有的完整性检查和加权重算。
```

- [ ] **Step 4: 运行后端定向测试，确认通过**

Run: `python -m pytest -q tests/test_realtime_search.py -k "county_specialty_evidence or specialty_bonus_uses or multiple_specialty_evidence or institutional_baseline_without or normalize_result_specialty"`

Expected: PASS，且县级 `77.3` 加县级依据为 `54.38`，综合实力 `97` 且无直接依据为 `58.2`。

- [ ] **Step 5: 调整受旧“归零/地板”假设影响的测试并运行完整后端套件**

将所有断言 `specialty == 0.0`、`specialty <= 82.0` 或旧 `ranking_floor` 数值的测试改为验证新规则：无依据时等于 `public_capability * 0.60`；专科排名按范围仍有序但只产生最高一项增量；综合排名不得作为专科排名使用。

Run: `python -m pytest -q`

Expected: PASS。

- [ ] **Step 6: 提交后端评分变更**

```bash
git add apps/api/app/realtime_search.py apps/api/tests/test_realtime_search.py
git commit -m "fix: calibrate specialty strength scores"
```

### Task 3: 保留基础分并标注缺少直接依据的前端回归

**Files:**
- Modify: `apps/web/tests/result-score.test.ts`
- Modify: `apps/web/tests/result-controls.test.tsx`
- Test: `apps/web/tests/result-score.test.ts`
- Test: `apps/web/tests/result-controls.test.tsx`

- [ ] **Step 1: 将结果分数工具测试改为保留后端专科基础分**

替换现有测试，确保前端不会重写后端计算的 `specialty` 和 `score`：

```typescript
it('preserves the backend specialty baseline without direct evidence', () => {
  const result = getDisplayedResultScore({
    score: 71.916,
    score_breakdown: {
      specialty: 43.26,
      public_capability: 72.1,
      geography: 100,
      freshness_completeness: 87.5,
      official_service: 100,
    },
    has_direct_specialty_evidence: false,
    specialty_evidence: [{ specialty: '', rank: 1271 }],
  });

  expect(result.hasDirectSpecialtyEvidence).toBe(false);
  expect(result.breakdown.specialty).toBe(43.26);
  expect(result.score).toBe(71.916);
});
```

- [ ] **Step 2: 更新结果卡片失败测试**

在“只有医院综合实力依据”的卡片数据中将 `score_breakdown.specialty` 设为 `58.2`、`public_capability` 设为 `97`。断言评分详情同时包含 `58.2` 和“暂无直接专科依据”，且仍只在“医院综合实力依据”中展示综合排名。

- [ ] **Step 3: 运行前端定向测试，确认因旧抹除逻辑而失败**

Run: `npm test -- --run tests/result-score.test.ts tests/result-controls.test.tsx`

Expected: FAIL。当前 `getDisplayedResultScore` 将 `specialty` 改为 `0`，卡片也不会显示基础分。

### Task 4: 前端显示校准后的专科基础分

**Files:**
- Modify: `apps/web/lib/result-score.ts`
- Modify: `apps/web/app/page.tsx:815-829`
- Modify: `apps/web/app/page.module.css`
- Test: `apps/web/tests/result-score.test.ts`
- Test: `apps/web/tests/result-controls.test.tsx`

- [ ] **Step 1: 停止在前端抹除后端专科基础分**

将 `getDisplayedResultScore` 缩减为只复制评分明细和判断直接证据状态：

```typescript
export function getDisplayedResultScore(result: ResultScoreInput) {
  const breakdown = { ...(result.score_breakdown ?? {}) };
  const inferredEvidence = (result.specialty_evidence ?? []).some((item) => Boolean(
    item.specialty?.trim() || item.department?.trim(),
  ));
  const hasDirectSpecialtyEvidence = result.has_direct_specialty_evidence ?? inferredEvidence;
  return { breakdown, hasDirectSpecialtyEvidence, score: result.score };
}
```

删除已不使用的 `SCORE_WEIGHTS`。

- [ ] **Step 2: 在评分详情中显示数值和依据状态**

在 `page.tsx` 的评分详情映射中，删除 `missingSpecialtyEvidence ? 0 : score` 的分支，使环形图和数值始终使用 `score`。保留 `hasSpecialtyEvidence` 的计算，并在专科项的 `dt` 后输出状态文本：

```tsx
<dt>
  {label}
  {key === 'specialty' && !hasSpecialtyEvidence
    ? <small className={styles.specialtyEvidenceMissing}>暂无直接专科依据</small>
    : null}
</dt>
```

`displayText` 对非零专科基础分始终使用 `score.toFixed(1)`；`aria-label` 仍包含“暂无直接专科依据”状态，方便读屏工具理解数值来自基础分而非直接证据。

- [ ] **Step 3: 添加紧凑状态样式**

在 `page.module.css` 中新增：

```css
.specialtyEvidenceMissing {
  display: block;
  margin-top: 4px;
  color: #8a5a24;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.35;
}
```

该提示只占专科评分项自身的文字区域，不改变环形评分组件的固定尺寸。

- [ ] **Step 4: 运行前端定向测试，确认通过**

Run: `npm test -- --run tests/result-score.test.ts tests/result-controls.test.tsx`

Expected: PASS，评分详情对无直接证据医院展示基础分和状态提示；综合排名仍不出现在专科能力依据中。

- [ ] **Step 5: 运行完整前端测试与构建**

Run: `npm test -- --run`

Expected: PASS。

Run: `npm run build`

Expected: exit code 0。允许既有的 bundle 大小提示，但不得出现 TypeScript 或构建错误。

- [ ] **Step 6: 提交前端展示变更**

```bash
git add apps/web/lib/result-score.ts apps/web/app/page.tsx apps/web/app/page.module.css apps/web/tests/result-score.test.ts apps/web/tests/result-controls.test.tsx
git commit -m "fix: show calibrated specialty baselines"
```

### Task 4.5: 校准地理位置评分等级

**Files:**
- Modify: `apps/api/app/realtime_search.py:338-361`
- Modify: `apps/api/tests/test_realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 更新地理位置失败断言**

将 `test_geography_score_uses_the_users_smallest_filled_region` 的同市不同区县期望改为 `85.0`，同省不同城市期望改为 `70.0`；市级请求下的同省其他城市同样断言 `70.0`。

- [ ] **Step 2: 运行测试确认旧规则失败**

Run: `python -m pytest -q tests/test_realtime_search.py -k geography_score_uses_the_users_smallest_filled_region`

Expected: FAIL，旧规则分别返回 `80.0` 和 `60.0`。

- [ ] **Step 3: 替换同省地理位置分值**

在 `_geography_score` 中保留同区县 `100.0`，将同市但不同区县返回值替换为 `85.0`，将同省但不同城市返回值替换为 `70.0`。市级请求中的同省其他城市也返回 `70.0`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest -q tests/test_realtime_search.py -k geography_score_uses_the_users_smallest_filled_region`

Expected: PASS。

### Task 5: 端到端评分样例验证

**Files:**
- No source changes expected.

- [ ] **Step 1: 启动带正式医院数据库的后端与前端**

Run:

```powershell
$env:HOSPITAL_COMPASS_DATABASE_PATH = 'F:\hospital-database\db\hospital_database.db'
$env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH = 'F:\hospital-database\db\hospital_database.db'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Run: `npm run dev -- --host 127.0.0.1 --port 5173`

Expected: 后端监听 `http://127.0.0.1:8001`，前端监听 `http://127.0.0.1:5173`。

- [ ] **Step 2: 验证广西神经内科样例**

向 `POST http://127.0.0.1:8001/v1/realtime-hospital-search` 提交：

```json
{
  "query": "脑卒中",
  "location": {
    "province": "广西壮族自治区",
    "city": "北海市",
    "district": "合浦县"
  },
  "location_level": "district",
  "scope": "province",
  "ai_consent": false,
  "confirmed_direction": "神经内科",
  "hospital_tiers": ["tertiary_a"]
}
```

Expected: 合浦县人民医院的 `specialty_evidence` 仍含“广西医疗卫生重点学科（县级）”；该项专科分只获得县级增量。广西医科大学第一附属医院即使没有直接神经内科依据，也有非零专科基础分。两者使用同一范围、同一请求时，综合实力更强医院不会仅因缺少低等级直接证据而被压低。

- [ ] **Step 3: 检查工作树与提交边界**

Run: `git status --short`

Expected: 仅本计划所列文件由对应提交暂存或提交；保留并不触碰已有的用户工作树改动、服务日志和运行缓存。
