# Hospital Compass MVP final-fix report

## Status

All requested final-review fixes are implemented. The API and web suites, TypeScript typecheck, production build, dependency checks, and both development and preview proxy smoke tests pass.

## Implemented fixes

- Replaced import-time relative fixture dates with immutable calendar dates. Matching, scoring, and public detail eligibility now consume an injected `as_of` date; the FastAPI clock is overrideable in tests.
- Unknown queries with no controlled direction return empty directions and empty results. Recognized queries include only hospitals that advertise the matched specialty.
- Added accessible result-card favorite toggles with `aria-pressed`, state-restoring labels, browser-local disclosure, restored local state, and clear-state synchronization.
- Constrained favorite IDs to the demo hospital-ID format (maximum 64 characters), sanitized stored arrays, deduplicated IDs, and rejected invalid writes.
- Replaced the vacuous optional privacy assertion with tests that exercise a real local-storage write and prove symptom text is absent. The API log test now proves request logging occurred before asserting that the symptom is absent.
- Added exact direct dependency pins, `uvicorn`, Python development extras, an npm lockfile backed by exact package versions, supported Node engines, `dev`, `start`, and `typecheck` scripts, Vite development/preview proxies, and strict TypeScript configuration.
- Documented clean repository-root startup for the API, development web server, production preview, proxy behavior, tests, and typecheck.

## TDD evidence

Production changes followed focused red/green cycles:

- `python -m pytest tests/test_matcher.py -q` initially reported 3 failures: unsupported input returned three hospitals, a nonmatching specialty remained in results, and `match(..., as_of=...)` was not supported. After the minimal matcher/date changes: 17 passed.
- `npm.cmd test -- --run tests/local-profile.test.ts tests/page.test.tsx` initially reported 4 failures: malformed/arbitrary favorite IDs were accepted and both accessible favorite-control tests could not find a favorite button. After the minimal storage/UI changes: 10 passed.
- `python -m pytest tests/test_privacy_and_detail.py::test_detail_uses_an_overrideable_clock_for_source_expiry -q` initially failed because `current_date` did not exist. After routing the dependency through detail and matching endpoints, the full focused file passed (7 passed).
- Before tooling changes, `python -m uvicorn --version` failed with `No module named uvicorn`; `npm.cmd run typecheck`, `npm.cmd run dev -- --help`, and `npm.cmd start -- --help` each failed because the scripts were missing. The first configured typecheck then caught an implicit-`any` test callback; that callback was typed and the gate passed.

## Final verification

- `python -m pytest -v` — 26 passed in 0.58 seconds.
- `python -m pip check` — no broken requirements found.
- `python -m uvicorn --version` — uvicorn 0.52.1 on CPython 3.12.10.
- `npm.cmd ci` — installed 106 packages; 0 vulnerabilities.
- `npm.cmd test -- --run` — 2 files, 10 tests passed.
- `npm.cmd run typecheck` — passed with no diagnostics.
- `npm.cmd run build` — Vite 8.2.0 production build passed with no warnings.
- Development end-to-end smoke — Vite `127.0.0.1:5173` proxied `GET /health` (`ok`) and `POST /v1/matches` (one direction, three matched demo records) to uvicorn `127.0.0.1:8000`.
- Preview smoke — `npm start` served the built index with HTTP 200 and proxied `/health` successfully on `127.0.0.1:4173`.
- `git diff --check` — passed.
- Independent final diff review — no Critical, Important, or Minor findings.

## Safety and remaining operational concern

The changes preserve emergency interruption, demo-data labeling, source/publication eligibility, query-free request logging, and browser-only ID storage. The immutable demo sources will intentionally expire after 180 days; they must be reverified and replaced with new fixed source dates rather than programmatically refreshed. Exact dependency upgrades are also intentionally explicit maintenance work.

## Commit

Commit message: `fix: complete hospital compass final review`.
