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
