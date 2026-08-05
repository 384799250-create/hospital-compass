# Task 2 report: deterministic emergency-safe matching

## Changed files

- `apps/api/app/data.py` — three explicitly labelled, in-memory demo hospitals.
- `apps/api/app/matcher.py` — deterministic match response, emergency interruption, eligibility filtering, scoring, and stable tie-breaking.
- `apps/api/app/main.py` — wires `POST /v1/matches` to the matcher.
- `apps/api/tests/test_matcher.py` — emergency, deterministic specialty ordering, and missing-score behavior tests.

## TDD evidence

Red command (run from `apps/api`):

```text
python -m pytest tests/test_matcher.py -v
```

Result: failed during collection with `ModuleNotFoundError: No module named 'app.matcher'`, as required before implementation.

Second red command (run from `apps/api`):

```text
python -m pytest tests/test_matcher.py -v
```

Result: `test_missing_score_fields_contribute_zero` failed with `TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'` before missing values were scored as zero.

Green commands (run from `apps/api`):

```text
python -m pytest tests/test_matcher.py -v
python -m pytest -v
```

Results: matcher suite passed `3 passed in 0.15s`; full API suite passed `5 passed in 0.40s`.

## Commit

Implementation commit: `3f079c1d70eb326183fb3bf4363aa432bc179c08` (`feat: add deterministic hospital matching`).

## Self-review

- Emergency terms short-circuit normal matching and return no results.
- Query content is used only within the request path and is neither persisted nor logged.
- Only published, verified records with sources no older than 180 days are eligible.
- Missing score fields contribute zero; scores tie-break by source freshness and then stored pinyin name.
- The API retains Task 1 validation behavior and returns the match response directly.

## Concerns

- The hospital records are intentionally minimal in-memory demo data. A production data source would need independently verified data refresh and expiry handling.

## Review fix report

### Changes

- Invalid, missing, and future `source_date` values are now ineligible before scoring or sorting.
- The source age check explicitly requires a `date` and accepts only the inclusive range 0–180 days, preventing freshness values above 100.
- Tests now cover all requested filters, no-city redistribution for all three priorities, exact missing-field scoring, and freshness/pinyin tie breaks.

### Focused TDD commands and results

Red command (run from `apps/api`):

```text
python -m pytest tests/test_matcher.py -v
```

Result: 3 failed and 10 passed. Missing and malformed `source_date` values raised `TypeError` in `_is_eligible`; a future date incorrectly produced a result with score `97.5556`.

Green commands (run from `apps/api`):

```text
python -m pytest tests/test_matcher.py -v
python -m pytest -v
```

Results: focused matcher suite passed `13 passed in 0.28s`; full API suite passed `15 passed in 0.40s`.

### Remaining concern

- Source validation treats `datetime` values as invalid rather than silently converting them, so data-ingestion code must normalize timestamps to calendar dates before calling the matcher.
