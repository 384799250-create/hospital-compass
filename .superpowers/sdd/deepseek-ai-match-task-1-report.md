# DeepSeek AI Match Task 1 Report

## Status

Implemented the backend-only `POST /v1/ai-matches` feature. No frontend file was changed by this task.

## Delivered behavior

- Added `AIMatchRequest`, extending the existing match request with required `ai_consent: bool`.
- Added `app/ai_matcher.py` with injectable environment and transport boundaries; tests use only local fake transports.
- Reads `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL` (default `deepseek-chat`).
- Calls `https://api.deepseek.com/chat/completions` with a 10-second timeout and `response_format={"type":"json_object"}`.
- Does not log the API key or query.
- Skips all network access when consent is absent, the API key is absent, or the local matcher marks the query as an emergency.
- Validates that AI content is exactly a JSON object containing a string `summary` of at most 240 characters and a string-array `directions` field.
- Filters and de-duplicates AI directions against the values of the existing `SPECIALTY_KEYWORDS`, then passes the filtered values to the matcher.
- Falls back to the unchanged local match plus `ai={used:false, summary:null, directions:[], fallback:true}` for missing credentials, transport/timeout/URL/HTTP failures, empty or malformed responses, invalid output, and empty/unknown-only directions.
- Returns `ai={used:true, summary:<validated>, directions:<filtered>, fallback:false}` on valid AI output.

## TDD evidence

The work was implemented through observed RED/GREEN cycles for:

- missing-key endpoint contract (RED: HTTP 404; GREEN: local fallback response),
- successful injectable DeepSeek JSON response (RED: missing injectable contract; GREEN: JSON-mode request and AI-directed match),
- no-consent network gate (RED: fake transport was called; GREEN: local fallback without transport),
- emergency network gate (RED: fake transport was called; GREEN: original emergency response without transport),
- unknown-direction filtering (RED: unknown direction leaked into response; GREEN: allowlisted directions only),
- malformed/empty output and transport/HTTP errors (RED: 15 failures; GREEN: all fallback cases pass).

## Verification

Run from `apps/api`:

```text
pytest -q
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 0.59s
```

## Files in the task commit

- `apps/api/app/ai_matcher.py`
- `apps/api/app/main.py`
- `apps/api/app/matcher.py`
- `apps/api/app/schemas.py`
- `apps/api/tests/test_ai_matcher.py`
- `apps/api/tests/test_contracts.py`
- `.superpowers/sdd/deepseek-ai-match-task-1-report.md`

## Concerns

- The production path uses Python's standard-library `urllib` transport; retries are intentionally not included because they were not requested.
- The worktree contains pre-existing uncommitted frontend changes in `apps/web/app/page.module.css`, `apps/web/app/page.tsx`, and `apps/web/tests/page.test.tsx`; they were neither modified nor staged by this task.
