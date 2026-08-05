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

- No telemetry implementation was added, so symptom text is not included in telemetry.

## Review follow-up

### Accessibility modal behavior

- Replaced the visual-only overlay with a native `<dialog>` opened through `showModal()` when the browser supports it.
- The background `<main>` is inert while the dialog is shown, the acknowledgement control is focused on open, Tab remains within the dialog, Escape does not bypass acknowledgement, and acknowledgement restores focus to `开始匹配`.
- The accessibility assertions were added before the implementation. The web red run failed because `main` did not have `inert`; after extending the test with Tab behavior, it failed because focus escaped to `body`.

### Per-result card metadata

- The API now returns required `specialties`, `score_reasons`, and `source_date` fields for every eligible result. Reasons reflect the actual scoring inputs available for that record; source date is the verified record date.
- The UI client types require those fields and cards render them directly, with no generic explanation or `未提供` placeholder.
- The matcher metadata test was added before the implementation and failed with `AttributeError: 'MatchResult' object has no attribute 'specialties'`.

### Follow-up commands and results

```text
cd apps/web && npm.cmd test -- --run tests/page.test.tsx
```

Green result: 1 test file passed; 3 tests passed.

```text
cd apps/api && python -m pytest tests/test_matcher.py -v
```

Green result: 14 tests passed.
