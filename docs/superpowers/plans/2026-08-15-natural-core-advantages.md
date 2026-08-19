# 自然化医院核心优势说明 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每张医院结果卡的 `core_advantages` 成为基于现有证据的 2 至 3 句自然中文说明，而不是等级、科室和整段公开简介的字段拼接。

**Architecture:** 保留当前的确定性搜索、排序、分数与原始 `database_evidence.public_introduction` 数据。DeepSeek 仅在已有候选的事实范围内组织自然说明，`web_ranker` 会拒绝过短、过长、标签化或缺乏证据相关性的生成文本；本地排序结果则用同一组证据优先级确定性生成说明，不再将公开简介全文附到结果上。

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, DeepSeek chat-completions API.

---

### Task 1: 用失败测试锁定自然说明的输出合同

**Files:**
- Modify: `apps/api/tests/test_realtime_search.py:443-465,646-650`
- Modify: `apps/api/tests/test_web_ranker.py:302-331`
- Modify: `apps/api/app/realtime_search.py`
- Modify: `apps/api/app/web_ranker.py`

- [ ] **Step 1: 把公开简介拼接的旧期望改为自然说明期望，并添加本地兜底用例**

在 `test_realtime_search.py` 中将 `test_rank_result_appends_database_public_introduction_after_specialty_evidence` 重命名为 `test_rank_result_builds_natural_advantages_without_appending_public_introduction`。保留同样的 `HospitalCandidate`，断言输出没有 `公开简介：`、没有完整公开简介原文，且仍含已核验的 `妇产科` 与 `三级甲等`。再添加一例没有专科证据的候选，验证说明明确资料限制、不把长公开简介直接复制到 `core_advantages`，且保留原始资料字段：

```python
assert '公开简介：' not in ranked[0]['core_advantages']
assert candidate.public_introduction not in ranked[0]['core_advantages']
assert '妇产科' in ranked[0]['core_advantages']
assert '三级甲等' in ranked[0]['core_advantages']
assert ranked[0]['database_evidence']['public_introduction'] == candidate.public_introduction
```

- [ ] **Step 2: 添加 AI 输出格式拒绝用例**

在 `test_web_ranker.py` 中增加一个带 `database_evidence.public_introduction` 的候选。让模拟 AI 返回一段含 `公开简介：` 和整段公开简介的 `core_advantages`，然后断言合成后的结果没有该标签或整段原文，并回退为本地自然说明。再增加一例 2 句、含 `心血管专科公开介绍` 与 `三级甲等` 的 70 至 140 字生成文本，断言它能被保留：

```python
assert '公开简介：' not in output[0]['core_advantages']
assert long_introduction not in output[0]['core_advantages']
assert '当前公开资料未提供' in output[0]['core_advantages']

assert output[0]['core_advantages'] == generated_advantages
```

- [ ] **Step 3: 运行聚焦测试并确认 RED**

Run:

```powershell
Set-Location apps/api
python -m pytest -q tests/test_realtime_search.py tests/test_web_ranker.py -k "core_advantages or natural_advantages or richer_advantage"
```

Expected: FAIL，因为现有代码仍会附加 `公开简介：` 和完整简介，且不会拒绝标签化 AI 输出。

- [ ] **Step 4: 仅在失败原因符合预期后进入实现**

确认失败来自旧行为的字符串差异，而非测试导入、时间、网络或候选筛选异常。不要在这一步改生产代码。

### Task 2: 实现确定性自然说明组合器并移除整段简介拼接

**Files:**
- Modify: `apps/api/app/realtime_search.py:476-555`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 用最多两类证据生成完整句子**

删除 `_append_public_introduction` 调用与该函数。将 `_fallback_core_advantages` 改为先取与 `directions` 相关的专科排名或能力，再补一条医院等级、综合排名或简短的、可验证的服务定位。输出最多三句，且不使用分号字段清单、`公开简介：` 标签或医院名称重复。遵循以下最小分支：

```python
if specialty_sentence:
    sentences.append(specialty_sentence)
else:
    sentences.append('当前公开资料未提供与该方向直接对应的专科依据。')

if institutional_sentence:
    sentences.append(institutional_sentence)
elif profile_sentence:
    sentences.append(profile_sentence)

return ''.join(sentences)[:180]
```

`specialty_sentence` 只能来自相关专科排名、`capability_evidence.department` 或已匹配的 `candidate.specialties`；`institutional_sentence` 只能来自 `tier` 或无专科名称的综合排名；`profile_sentence` 只能取公开简介中的首个完整句子，并排除 `愿景`、`使命`、`致力于`、`一流` 等宣传词。没有直接专科证据时，不得把等级或综合排名写成该专科的优势。

- [ ] **Step 2: 让结果循环只使用已自然化的说明**

在 `rank_candidates` 中保留：

```python
core_advantages = candidate.core_advantages or _fallback_core_advantages(candidate, directions, source)
```

删除紧随其后的公开简介追加。`database_evidence['public_introduction']` 保持不变，供详情页和 AI 整理读取；不修改评分、排序、`match_reason`、来源或官网字段。

- [ ] **Step 3: 运行本地说明测试并确认 GREEN**

Run:

```powershell
Set-Location apps/api
python -m pytest -q tests/test_realtime_search.py -k "core_advantages or natural_advantages"
```

Expected: PASS，且输出不再含 `公开简介：` 或整段数据库简介。

- [ ] **Step 4: 提交本地说明组合器**

```powershell
git add apps/api/app/realtime_search.py apps/api/tests/test_realtime_search.py
git commit -m "feat: naturalize fallback hospital advantages"
```

### Task 3: 限制 DeepSeek 说明并在不合格时回退

**Files:**
- Modify: `apps/api/app/web_ranker.py:45-93,164-180,326-337`
- Test: `apps/api/tests/test_web_ranker.py`

- [ ] **Step 1: 收紧 AI 文案提示词**

修改当前英文 `SYSTEM_PROMPT` 中关于 `core_advantages` 的段落，明确要求中文 2 至 3 句、70 至 140 个汉字，先写与当前推荐方向有关的可验证专科证据，再补等级、综合排名或事实性服务定位。删除“append it as a clearly labeled public-profile supplement”要求，并加入禁止项：不得输出 `公开简介：`、分号式字段罗列、医院名称重复、口号、未经候选资料证明的能力。要求没有直接专科证据时明确资料限制。

- [ ] **Step 2: 增加核心优势专用校验器**

在 `_grounded_generated_text` 旁新增 `_grounded_core_advantages`，复用现有内部推理、方向相关性、冲突专科和证据 token 校验，再增加如下可读性约束：

```python
def _grounded_core_advantages(value, base, directions, query):
    normalized = str(value or '').strip()
    if not _grounded_generated_text(normalized, base, directions, query):
        return None
    if not 30 <= len(normalized) <= 180:
        return None
    if '公开简介：' in normalized or '；' in normalized:
        return None
    if _contains_full_public_introduction(normalized, base):
        return None
    return normalized
```

`_contains_full_public_introduction` 只在数据库简介非空且其完整规范化文本包含于生成结果时返回真，不因共享短语误杀正常说明。现有 `_grounded_generated_text` 继续服务 `match_reason`，不要把其长度规则施加到理由上。

- [ ] **Step 3: 替换 AI 合并链路**

在 `synthesize_hospital_results` 用 `_grounded_core_advantages` 获取 `generated_advantages`，并对已有 `base['core_advantages']` 也做标签与全文简介清理。删除 `_append_public_introduction` 及其调用，让不合格输出走 `_fallback_hospital_strength(base)`。更新 `_fallback_hospital_strength`：它只用等级、综合排名和来源首句生成两句以内的中性说明，不使用 `医院公开简介：` 标签或大段 `snippet`。

- [ ] **Step 4: 运行 AI 合成测试并确认 GREEN**

Run:

```powershell
Set-Location apps/api
python -m pytest -q tests/test_web_ranker.py
```

Expected: PASS，正常的证据化 AI 说明被保留；标签化、冗长或整段简介式文本回退到本地中性说明。

- [ ] **Step 5: 提交 AI 说明约束**

```powershell
git add apps/api/app/web_ranker.py apps/api/tests/test_web_ranker.py
git commit -m "feat: validate evidence-based hospital advantages"
```

### Task 4: 全量回归与运行中验证

**Files:**
- Modify only if verification exposes a concrete regression: `apps/api/app/realtime_search.py`, `apps/api/app/web_ranker.py`, or their tests
- Test: `apps/api/tests/`

- [ ] **Step 1: 运行完整后端测试套件**

Run:

```powershell
Set-Location apps/api
python -m pytest -q
```

Expected: 所有测试通过；原有排序、评分、详情和合成接口合同保持稳定。

- [ ] **Step 2: 重新启动后端并检查健康状态**

使用项目现有启动脚本或已配置的 API 启动命令重启 8001 服务。随后运行：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/docs | Select-Object -ExpandProperty StatusCode
```

Expected: `200`。

- [ ] **Step 3: 用真实结果接口检查不变量**

针对一个有公开简介和专科资料的医院结果，验证 `core_advantages` 有 2 至 3 句、没有 `公开简介：`、没有整段简介；同时验证 `database_evidence.public_introduction` 仍完整可用，分数、科室和医院顺序未因本次变更改变。

- [ ] **Step 4: 提交验证中产生的必要修正**

```powershell
git add apps/api/app/realtime_search.py apps/api/app/web_ranker.py apps/api/tests/test_realtime_search.py apps/api/tests/test_web_ranker.py
git commit -m "test: verify natural hospital advantage summaries"
```

## 自检

- 设计文档的每项规则均有对应任务：自然 2 至 3 句（任务 2、3）、AI 优先和本地兜底（任务 2、3）、不拼接整段简介（任务 1、2、3）、不改变排序与原始资料（任务 2、4）。
- 已检查术语一致性：运行时字段始终为 `core_advantages`，原始公开简介始终为 `database_evidence.public_introduction`。
- 本计划不包含 `TBD`、`TODO` 或“类似上一任务”的占位步骤。
