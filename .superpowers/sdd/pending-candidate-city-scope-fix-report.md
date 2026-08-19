# Pending-candidate city-scope fix re-review

## Verdict

**Addressed.** The change in `3071b74` correctly rejects standalone district,
county, and sub-city values while retaining city-level values. No new Critical
or Important issue was found in `apps/api` relative to `c946cdf`.

## Evidence reviewed

- `_SUB_CITY_PATTERN = re.compile(r'(?:区|县)$')` is applied to
  `candidate.city` in `_clean_pending_candidates` before a candidate is kept.
- `test_pending_candidates_require_city_level_city_values` covers the three
  original problematic values: `朝阳区`, `海淀区`, and `浦东新区`.
- A direct cleaner check confirmed those values, plus district `昌平区` and
  county `密云县`, are rejected; `北京市`, `Beijing`, `Shanghai`, and `Guangzhou`
  are accepted. The direct check is needed for `Guangzhou` because the public
  response intentionally retains at most three valid pending candidates.

## Verification

From `apps/api`:

```text
pytest -q tests/test_ai_matcher.py -k require_city_level_city_values
1 passed, 49 deselected

pytest -q
132 passed in 0.64s
```
