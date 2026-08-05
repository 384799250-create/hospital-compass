# Task 3 implementation report

## Scope delivered

- Added the React patient matching page, semantic search controls, responsive styles, and API client.
- Added the emergency acknowledgement dialog. Emergency responses never render the `推荐医院` section.
- Added a fixed non-diagnostic disclaimer, labelled demo results, and 503 fallback copy directing users to official sources.
- The page keeps the submitted text only in component state while making the request; it does not log, persist, or send telemetry for it.

## TDD evidence

### Red: emergency interruption

Test written first: `apps/web/tests/page.test.tsx` mocks the complete emergency response, enters `突发胸痛`, clicks `开始匹配`, and asserts the emergency message while `推荐医院` is absent.

Command (executed as `npm.cmd` because this Windows session blocks `npm.ps1`):

```text
cd apps/web && npm.cmd test -- --run tests/page.test.tsx
```

Observed red result: Vitest failed before test execution with `Cannot find module '/app/page'`, because the page and client did not yet exist.

### Green: emergency interruption

After the minimal page and client implementation:

```text
cd apps/web && npm.cmd test -- --run tests/page.test.tsx
```

Observed green result: 1 test passed.

### Red and green: HTTP 503 fallback

Added a second behavior test for a mocked `MatchApiError(503)`. The test initially failed because the generic error copy did not contain the required official-source guidance. After adding the status-specific fallback branch, it passed.

```text
cd apps/web && npm.cmd test -- --run tests/page.test.tsx
```

Observed green result: 2 tests passed.

## Final verification

```text
cd apps/web && npm.cmd test -- --run
```

Result: 1 test file passed; 2 tests passed.

```text
cd apps/api && python -m pytest -v
```

Result: 15 tests passed.

## Commit

`feat: add patient matching experience`

## Concerns

- The current Task 1-2 API response supplies only name, city, demo label, and score for each result. The UI supports optional `specialties`, `score_reasons`, and `source_date` when the API later supplies them; with the present contract it truthfully displays `未提供` for source date and uses the API directions plus a generic explanation. No backend contract expansion was made because it is outside Task 3.
- No telemetry implementation was added, so symptom text is not included in telemetry.
