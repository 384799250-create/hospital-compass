# Task 3 Report: Realtime Hospital Ranking Endpoint

## Implemented

- Added `POST /v1/realtime-hospital-search` in `apps/api/app/main.py`.
- Emergency requests return `EMERGENCY` before invoking AI or Bocha.
- AI is invoked only when `ai_consent` is strictly true; unconsented requests never reach DeepSeek through the endpoint.
- Bocha availability is surfaced as `SEARCH_UNAVAILABLE`; an empty or fully filtered result set is `NO_RESULTS`.
- Added conservative document-to-candidate conversion, exact district/city/province/national scope filtering, deterministic de-duplication, and a hard ten-result cap.
- Added explainable ranking with fixed 35/25/20/10/10 weights, source URLs, per-source timestamps, and registration URL allowlisting.

## Verification

- Focused: `python -m pytest -q apps/api/tests/test_contracts.py -k realtime` (4 passed).
- Full API suite: `python -m pytest -q apps/api/tests` (169 passed).

No Bocha or DeepSeek secrets were added to source, tests, logs, or frontend files.
