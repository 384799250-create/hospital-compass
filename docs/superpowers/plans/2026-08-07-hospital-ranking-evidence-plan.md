# 医院证据化排名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 让实时医院搜索返回 DeepSeek 风格的 10 家排名结果，并展示核心优势、匹配理由、评分详情和区域回退入口。

**Architecture:** 保留现有 Bocha 检索和 FastAPI 接口，将候选证据标准化后交给 DeepSeek 生成最终结构化排名；本地仅做医院实体和城市安全校验。前端通过统一实时结果类型渲染卡片、折叠评分和范围切换。

**Tech Stack:** FastAPI/Pydantic, Python pytest, DeepSeek Chat Completions, React/TypeScript, Vite.

---

### Task 1: 扩展实时结果契约

**Files:**
- Modify: `apps/api/app/web_ranker.py`
- Modify: `apps/api/app/realtime_search.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_realtime_search.py`
- Test: `apps/api/tests/test_contracts.py`

- [ ] **Step 1: Write failing tests** for `core_advantages`, `match_reason`, `evidence_status`, `score_breakdown`, and `fallback_scope` fields.
- [ ] **Step 2: Run the focused tests** with `python -m pytest -q --basetemp .pytest-tmp apps/api/tests/test_realtime_search.py apps/api/tests/test_contracts.py` and confirm the new fields are absent.
- [ ] **Step 3: Extend Pydantic synthesis models and prompt** so DeepSeek returns the new fields, while preserving the original candidate source URLs and IDs.
- [ ] **Step 4: Add deterministic fallbacks** for missing AI fields (`暂无公开资料`, source snippet, and existing score dimensions) without fabricating an address.
- [ ] **Step 5: Run all backend tests** and confirm the complete suite passes.
- [ ] **Step 6: Commit** with `git commit -m "feat: add evidence fields to hospital ranking"`.

### Task 2: Add hierarchical location and fallback behavior

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/schemas.py`
- Test: `apps/api/tests/test_contracts.py`

- [ ] **Step 1: Write failing API tests** for district default scope, fewer-than-ten results returning `fallback_scope`, and city/province/national reruns.
- [ ] **Step 2: Run the focused tests** and confirm fallback metadata is missing.
- [ ] **Step 3: Implement `fallback_scope` and `fallback_message`** without changing the requested `scope`; use the next wider scope only when the result count is below ten.
- [ ] **Step 4: Validate location fields** and keep the smallest user-supplied address as the default scope.
- [ ] **Step 5: Run backend tests** and verify no existing scope tests regress.
- [ ] **Step 6: Commit** with `git commit -m "feat: add geographic ranking fallback"`.

### Task 3: Update frontend result presentation

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Test: `apps/web` TypeScript build

- [ ] **Step 1: Add typed fields** for advantages, match reasons, evidence status, score breakdown, and fallback metadata.
- [ ] **Step 2: Add a shared result-card renderer** in `page.tsx` so the duplicate realtime sections render the same fields.
- [ ] **Step 3: Add collapsed `评分详情` control** that expands score dimensions and source links per hospital.
- [ ] **Step 4: Add scope label and fallback action** above results; clicking the action submits the same query at `fallback_scope`.
- [ ] **Step 5: Set realtime consent default to checked and disable submit when unchecked** with an accessible message.
- [ ] **Step 6: Run `npm.cmd run typecheck` and `npm.cmd run build`**.
- [ ] **Step 7: Commit** with `git commit -m "feat: show hospital strengths and match reasons"`.

### Task 4: Verify the complete workflow

**Files:**
- Test: `apps/api/tests`
- Verify: `apps/web`

- [ ] **Step 1: Run `python -m pytest -q --basetemp .pytest-tmp apps/api/tests`** and record the passing count.
- [ ] **Step 2: Run frontend typecheck and production build.**
- [ ] **Step 3: Restart backend and frontend through `start-hospital-compass.ps1` with hidden windows.**
- [ ] **Step 4: Submit `心绞痛 + 广东省/广州市/南山区` and verify ten localized results, advantages, match reasons, and score expansion.
- [ ] **Step 5: Verify the browser URL is `http://127.0.0.1:5173/` and `/health` returns `{"status":"ok"}`.
- [ ] **Step 6: Run `git diff --check` and commit the final verification notes.**
