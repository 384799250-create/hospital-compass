# Pending candidate city-scope fix

## Scope

Backend-only validation change for AI pending candidates. No frontend files were edited.

## Root cause

`_DETAILED_CITY_ADDRESS_PATTERN` rejected district/county markers only when a
province or city marker preceded them. Consequently, standalone sub-city values
such as `朝阳区`, `海淀区`, and `浦东新区` passed the candidate cleaner.

## Change

Added `_SUB_CITY_PATTERN = re.compile(r'(?:区|县)$')` to the pending-candidate
city address checks. This rejects district- and county-level city values while
leaving city-level Chinese values (for example, `北京市`) and the current English
city values (`Beijing`, `Shanghai`, `Guangzhou`) valid. Existing detailed-address,
hospital-suffix, prohibited-content, and medical-advice guards remain unchanged.

## TDD evidence

Added `test_pending_candidates_require_city_level_city_values`.

- Red: `pytest -q tests/test_ai_matcher.py -k require_city_level_city_values`
  failed because `['朝阳区', '海淀区', '浦东新区']` were returned.
- Green: the same command passed after the validation change.

## Verification

From `apps/api`:

```text
pytest -q
132 passed in 0.64s
```
