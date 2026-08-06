# Task 1 report: pilot hospital import validation

## Files

- Added `apps/api/app/importer.py` with row-level import validation and aggregate reports.
- Added `apps/api/app/data/pilot_hospitals.csv` with 30 inert draft placeholders (10 each for Beijing, Shanghai, and Guangzhou).
- Added `apps/api/tests/test_importer.py`.
- Updated `apps/api/app/data.py` with a path constant only; the draft file is not loaded into `DEMO_HOSPITALS` or an API route.

## TDD evidence

Red commands observed:

```text
python -m pytest tests/test_importer.py -v
ModuleNotFoundError: No module named 'app.importer'

python -m pytest tests/test_importer.py -v
2 failed, 1 passed (missing required validation)

python -m pytest tests/test_importer.py -v
1 failed, 3 passed (pilot CSV absent)

python -m pytest tests/test_importer.py -v
1 failed, 4 passed (HTTPS URL without host was accepted)
```

Green commands observed:

```text
python -m pytest tests/test_importer.py -v
5 passed

python -m pytest -v
30 passed
```

## Review

- Validation accumulates all invalid fields per row and never throws for malformed source dates.
- IDs are unique within an import batch; source URLs require both HTTPS and a host.
- Source dates must be ISO-formatted, nonfuture, and no more than 80 days old.
- Draft rows remain `published=false` and `verified=false`; they are not added to the public in-memory dataset, so existing public endpoints cannot serve them.

## Commit

`d1e8fa2 feat: add pilot hospital import validation`

## Concerns

No blocking concerns. Valid tiers are explicitly limited to `primary`, `secondary`, and `tertiary`; future source conventions would need to map to one of those values before import.

## Review remediation

Follow-up review found that `urlparse(...).netloc` could accept an HTTPS URL
without a hostname, and that `None` values could throw while validating dates
or tag fields. Focused red tests demonstrated five failures: `https://user@`,
`https://:443`, and `None` for each of `source_date`, `specialties`, and
`disease_tags`.

The importer now requires a parsed HTTPS hostname, validates field types before
normalization, and catches malformed source-date input as a row-level error.
The final API verification was `python -m pytest -v` with **36 passed**.
