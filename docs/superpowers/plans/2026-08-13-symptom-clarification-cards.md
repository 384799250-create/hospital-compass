# Symptom Clarification Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When symptom input is ambiguous, ask one dynamically generated clarification question at a time before producing disease-direction and department recommendations.

**Architecture:** Add a small backend clarification contract that uses the existing AI triage path when available and deterministic rules as fallback. The frontend keeps the current submit flow, inserts a single-question card only when the backend says clarification is needed, and submits accumulated answers until the backend returns a final triage result or an emergency stop. Answers stay in memory for the current session.

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, Vitest, Testing Library.

---

### Task 1: Define clarification API contract and fallback engine

**Files:**
- Create: `apps/api/app/symptom_clarification.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_symptom_clarification.py`

- [ ] **Step 1: Write failing tests** for ambiguous input returning one question, answer submission returning a final direction, and red-flag answers returning emergency status.
- [ ] **Step 2: Run the focused tests and confirm they fail** because the module and route do not exist.
- [ ] **Step 3: Implement the minimal Pydantic models and `clarify_symptoms` function** with AI transport injection, deterministic fallback questions, answer normalization, and red-flag detection.
- [ ] **Step 4: Add `POST /v1/symptom-clarification`** requiring consent and returning `{status, question, progress, directions, urgent_warning}`.
- [ ] **Step 5: Run focused backend tests and confirm they pass.**

### Task 2: Add frontend clarification-card state and API client

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Modify: `apps/web/tests/symptom-clarification-card.test.tsx`

- [ ] **Step 1: Write failing UI tests** for showing one question only when clarification is required, selecting “不确定”, advancing to final directions, and showing an emergency warning that blocks normal matching.
- [ ] **Step 2: Run the focused UI tests and confirm the expected failures.**
- [ ] **Step 3: Add typed API client and state** for the clarification session, current question, answer history, loading, and emergency state.
- [ ] **Step 4: Render the single-question card** with primarily radio choices, an “不确定/跳过” option, progress text, and a continue action.
- [ ] **Step 5: Connect final directions to the existing triage panel and hospital matching flow.**
- [ ] **Step 6: Run focused UI tests, typecheck, and build.**

### Task 3: Integration regression coverage

**Files:**
- Modify: `apps/api/tests/test_contracts.py`
- Modify: `apps/web/tests/hospital-detail-regression.test.tsx`

- [ ] **Step 1: Add contract coverage** proving the existing `/v1/triage` behavior remains unchanged for clear input.
- [ ] **Step 2: Add a UI regression** proving clear input skips clarification and still reaches existing matching controls.
- [ ] **Step 3: Run the full API test suite and all frontend tests.**

### Task 4: Final verification

- [ ] Run `python -m pytest -q` in `apps/api`.
- [ ] Run `npm.cmd test -- --run` in `apps/web`.
- [ ] Run `npm.cmd run typecheck` and `npm.cmd run build` in `apps/web`.
- [ ] Check that no user answer is persisted outside in-memory React state.
