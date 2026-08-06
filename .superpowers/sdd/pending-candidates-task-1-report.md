# Pending-verification Candidates Task 1 Report

## Status

Implemented the backend-only pending-candidate contract in `app/ai_matcher.py`. No frontend files were modified for this task.

## Delivered behavior

- Added the required `PendingCandidate` response model and required `AIMatchResponse.pending_candidates` array.
- Accepts the optional DeepSeek `pending_candidates` array without allowing a malformed candidate to fail the whole AI match.
- Keeps only candidates whose exact fields are `name`, `city`, `direction`, and `reason`; all values must be non-empty strict strings after trimming.
- Enforces maximum lengths of 80 for `name`, 40 for `city`, and 180 for `reason`; restricts `direction` to locally supported specialty directions; returns at most three valid candidates.
- Returns candidates only after a successful, non-emergency, consented AI call when `match_directions` found no verified results.
- Returns an empty candidate list whenever verified results exist or the request is unconsented, lacks an API key, is an emergency, or encounters an HTTP/model/JSON validation failure.
- Strengthened the system prompt to identify candidate names as pending manual verification only, prohibit diagnosis or treatment, and prohibit invented addresses, phone numbers, and source links.
- Extended the endpoint and OpenAPI contract tests for the required candidate field and schema.

## TDD evidence

Each new behavior was introduced through a focused failing test before its minimal implementation:

- A compliant no-result response first failed because the unknown `pending_candidates` field caused the AI path to fall back.
- Verified-result suppression first failed by exposing the supplied pending candidate.
- Mixed malformed candidates first failed by collapsing the whole AI response into fallback.
- The three-item limit first failed by returning a fourth valid candidate.
- The prompt contract first failed with the prior system instruction.
- The OpenAPI requirement first failed because `pending_candidates` was not yet a required response field.

Focused tests were rerun green after each implementation step.

## Verification

Run from `apps/api`:

```text
pytest -q
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 0.65s
```

Task-file whitespace validation also completed successfully:

```text
git diff --check -- apps/api/app/ai_matcher.py apps/api/tests/test_ai_matcher.py apps/api/tests/test_contracts.py
```

## Task files

- `apps/api/app/ai_matcher.py`
- `apps/api/tests/test_ai_matcher.py`
- `apps/api/tests/test_contracts.py`
- `.superpowers/sdd/pending-candidates-task-1-report.md`

## Safeguards and concerns

- Consent and emergency gates remain ahead of all external transport calls.
- The API key remains confined to the authorization header, and existing secret/query log assertions remain green.
- Candidates are names pending manual verification, never promoted into verified match results.
- Invalid candidates are dropped rather than echoed or used for matching.
- No new network retry behavior or candidate persistence was added; both remain outside this task.
- Pre-existing changes in `.superpowers/sdd/deepseek-ai-match-final-fix-report.md`, `apps/web/app/page.module.css`, and `.playwright-cli/` were preserved and excluded from this task commit.
