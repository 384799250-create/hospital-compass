# DeepSeek AI Match Final Fix Report

## Status

Implemented all final backend review findings for commit `25691a8`. The pre-existing frontend working-tree changes were not modified or staged.

## Delivered fixes

- Changed `AIMatchRequest.ai_consent` to Pydantic `StrictBool`, so only JSON booleans are accepted. String and numeric representations now receive HTTP 400 through the existing validation handler and cannot reach the external transport.
- Moved the synchronous `ai_match` call, including its `urllib` network work, out of the async route's event loop with Starlette's `run_in_threadpool`.
- Declared `response_model=AIMatchResponse` on `POST /v1/ai-matches`, exposing the inherited match fields and required `ai` metadata through OpenAPI.
- Added an endpoint success test using the real AI matcher with an injected local transport. The test proves the transport runs without an active event loop, the AI response is wired through to hospital results, and neither the symptom query nor API key appears in request logs.

## TDD evidence

The endpoint regressions were added before production changes and observed failing for the intended reasons:

- Eight string/numeric consent cases returned HTTP 200 instead of HTTP 400.
- The injected transport observed an active event loop because the async route called the synchronous matcher directly.
- The OpenAPI 200 response schema was `{}` rather than a reference to `AIMatchResponse`.

After the minimal production changes, the focused regression run reported `10 passed, 6 deselected`.

## Verification

Run from `apps/api`:

```text
pytest -q
........................................................................ [ 71%]
.............................                                            [100%]
101 passed in 0.64s
```

The API-file whitespace check also completed successfully:

```text
git diff --check -- apps/api/app/main.py apps/api/app/schemas.py apps/api/tests/test_contracts.py
```

## Files in the task commit

- `apps/api/app/main.py`
- `apps/api/app/schemas.py`
- `apps/api/tests/test_contracts.py`
- `.superpowers/sdd/deepseek-ai-match-final-fix-report.md`

## Commit

This report is included in the task commit; resolve its immutable hash with `git rev-parse HEAD` after commit creation.

## Concerns

- The external transport remains synchronous by design, but the API route now isolates the entire matcher call in Starlette's worker thread pool.
- Retries remain intentionally out of scope.
- Pre-existing uncommitted frontend edits remain in `apps/web/app/page.module.css`, `apps/web/app/page.tsx`, and `apps/web/tests/page.test.tsx`; they were preserved and excluded from this task's commit.
