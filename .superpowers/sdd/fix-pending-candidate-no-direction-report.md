# Fix report: preserve pending candidates without directions

## Root cause

`ai_match` filtered AI directions and immediately returned the local fallback
when the filtered list was empty. That branch ran before
`pending_candidates` were cleaned and considered, so a valid candidate from a
valid AI JSON response was discarded whenever every AI direction was empty or
not in the local allowlist.

## Change

- Added a regression test for an AI response with `directions=[]`, one valid
  pending candidate, consent enabled, and no local verified matches.
- Clean pending candidates before selecting the no-direction fallback.
- Use fallback only when both the filtered directions and cleaned candidate
  list are empty. The normal result construction keeps the AI summary,
  `directions=[]`, `ai.used=true`, `fallback=false`, and the cleaned candidate.

Existing guards remain unchanged: no consent, emergency, malformed AI data,
and AI output with neither valid directions nor valid candidates still return
the local fallback. Candidates remain empty when verified results are present.

## TDD and verification evidence

1. RED: `python -m pytest -q tests/test_ai_matcher.py::test_compliant_pending_candidates_are_preserved_without_ai_directions`
   failed before the implementation because `response.ai.used` was `False`
   instead of `True`; the early no-direction fallback caused the failure.
2. GREEN: the same focused test passed after the minimal branch-condition
   change.
3. Full verification: `python -m pytest -q` passed: **124 passed in 0.65s**.

## Scope

No frontend files were changed by this fix. Pre-existing unrelated worktree
changes remain uncommitted and are excluded from this commit.
