# 全国专科排名分段曲线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全国专科排名的 40 分加分上限映射为 1-20 名 1.00-0.70、20-100 名 0.70-0.25 的两段线性权重。

**Architecture:** 在 `realtime_search` 中把全国排名的名次转换封装为私有函数，再由现有的专科排名加分函数按范围、方向匹配系数和 40 分上限组合。省市县排名沿用现有数据分值及范围权重，不受该全国曲线影响。

**Tech Stack:** Python 3.12, FastAPI, pytest。

---

### Task 1: 锁定全国名次边界

**Files:**
- Modify: `apps/api/tests/test_realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 写入失败的边界测试**

```python
assert _national_specialty_ranking_bonus(1) == 40.0
assert _national_specialty_ranking_bonus(20) == 28.0
assert _national_specialty_ranking_bonus(21) == 27.775
assert _national_specialty_ranking_bonus(100) == 10.0
assert _national_specialty_ranking_bonus(101) == 0.0
```

- [ ] **Step 2: 运行测试，确认当前实现不能根据名次计算上述值**

Run: `pytest tests/test_realtime_search.py -k national_specialty_ranking_bonus -v`

Expected: FAIL，因为函数尚不存在。

### Task 2: 实现分段排名加分

**Files:**
- Modify: `apps/api/app/realtime_search.py:727-738`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 新增全国名次到排名加分的函数**

```python
def _national_specialty_ranking_bonus(rank: int) -> float:
    if 1 <= rank <= 20:
        weight = 1.0 - (rank - 1) * 0.30 / 19
    elif 20 < rank <= 100:
        weight = 0.70 - (rank - 20) * 0.45 / 80
    else:
        return 0.0
    return round(_SPECIALTY_RANKING_BONUS_CAP * weight, 4)
```

- [ ] **Step 2: 在专科排名加分中对全国记录使用名次函数**

```python
if _ranking_scope_weight(scope) == _SPECIALTY_RANKING_SCOPE_WEIGHTS['national']:
    return _national_specialty_ranking_bonus(rank) * direction_match
```

只在范围为全国时使用新曲线；其他范围保留既有 `score` 与范围权重的计算。

- [ ] **Step 3: 运行定向测试**

Run: `pytest tests/test_realtime_search.py -k 'national_specialty_ranking_bonus or specialty' -v`

Expected: PASS。

### Task 3: 回归验证

**Files:**
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] **Step 1: 运行 API 评分测试**

Run: `pytest tests/test_realtime_search.py -v`

Expected: PASS。

- [ ] **Step 2: 运行 API 全量测试**

Run: `pytest`

Expected: PASS。
