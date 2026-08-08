# Authoritative Specialty Rankings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a traceable specialty-ranking evidence layer that combines authoritative public rankings, official specialty credentials, hospital pages, and live search without excluding hospitals absent from a ranking.

**Architecture:** Store normalized ranking evidence in the existing F-drive SQLite database through a focused repository and importer. Extend candidate construction and deterministic scoring to consume matched evidence, while preserving current search and DeepSeek fallback behavior. Expose evidence metadata in the API result and render it in the existing hospital detail surface.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, React/TypeScript, Vite.

---

### Task 1: Define ranking evidence contract

**Files:**
- Create: `apps/api/app/specialty_rankings.py`
- Test: `apps/api/tests/test_specialty_rankings.py`

- [ ] Write failing tests for normalized ranking records, rank-to-score conversion, missing-rank fallback, and year/source preservation.
- [ ] Run `pytest apps/api/tests/test_specialty_rankings.py -q` and verify the new tests fail because the module is absent.
- [ ] Implement `SpecialtyRankingEvidence`, normalization helpers, and deterministic conversion of rank/tier to a 0-100 score.
- [ ] Run the focused tests and verify they pass.

### Task 2: Persist and import ranking data

**Files:**
- Modify: `apps/api/app/hospital_store.py`
- Create: `apps/api/app/specialty_ranking_store.py`
- Test: `apps/api/tests/test_specialty_ranking_store.py`

- [ ] Write failing tests for SQLite schema creation on F drive, CSV/JSON row import, deduplication, and default `待核验` status.
- [ ] Run the focused tests and verify they fail for the missing table/repository.
- [ ] Add the independent `specialty_rankings` table and indexes without changing existing hospital rows.
- [ ] Implement import and query methods that retain original source URL, ranking title, year, and raw hospital/specialty values.
- [ ] Run focused persistence tests and verify they pass.

### Task 3: Match evidence to hospital candidates

**Files:**
- Modify: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] Add failing tests for exact normalized hospital/city/specialty matches, aliases, cross-city non-matches, and multiple-year selection.
- [ ] Run the focused tests and verify they fail before candidate evidence is populated.
- [ ] Add an optional evidence field to `HospitalCandidate` and merge it without overwriting grounded addresses or advantages.
- [ ] Select the newest usable ranking evidence and preserve all source metadata for display.
- [ ] Run realtime-search tests and verify they pass.

### Task 4: Integrate evidence into deterministic scoring

**Files:**
- Modify: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

- [ ] Add failing tests for the 50/25/15/10 specialty evidence weighting, renormalization when evidence is missing, old-year freshness handling, and no hospital-specific exception.
- [ ] Run the focused tests and verify the new assertions fail.
- [ ] Implement the specialty evidence score and keep the existing five overall dimensions unchanged.
- [ ] Include ranking source, year, rank/tier, and evidence status in result payloads and score reasons.
- [ ] Run all API tests and verify the full suite remains green.

### Task 5: Protect AI synthesis and expose API fields

**Files:**
- Modify: `apps/api/app/web_ranker.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_web_ranker.py`

- [ ] Write failing tests showing DeepSeek cannot replace existing ranking evidence, addresses, or core advantages.
- [ ] Run the focused tests and verify they fail with the current synthesis behavior.
- [ ] Extend the strict JSON contract and merge logic to preserve deterministic evidence fields.
- [ ] Return a stable `specialty_evidence` object in API responses, including source and `待核验` state.
- [ ] Run API tests and verify they pass.

### Task 6: Render evidence in the web UI

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Test: existing frontend typecheck/build commands

- [ ] Add the typed evidence shape and render a compact “权威专科依据” row in each hospital detail area.
- [ ] Show ranking title, year, specialty rank/tier, source link, and `待核验` badge; hide the row when no evidence exists.
- [ ] Run `npm.cmd run typecheck` and `npm.cmd run build`.

### Task 7: End-to-end verification and service handoff

**Files:**
- Modify: `apps/api/tests/test_contracts.py` only if the response contract requires coverage.

- [ ] Run the complete backend suite and frontend typecheck/build.
- [ ] Verify `http://127.0.0.1:8000/health` and `http://127.0.0.1:5173/` remain available.
- [ ] Exercise one ranked search with a known specialty evidence row and confirm the UI displays source, year, rank, and verification status.
- [ ] Report any unverified or unavailable public ranking sources explicitly; do not claim national completeness.

