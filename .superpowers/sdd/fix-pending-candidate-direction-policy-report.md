# Fix report: pending candidate direction policy

## Root cause

`PendingCandidate.direction` reused the verified-match direction allowlist, so a
valid pending candidate was discarded whenever its direction was not already in
`SPECIALTY_KEYWORDS`. Candidate cleanup also scanned every display field with a
blanket `[省市区县路街号]` rule, which incorrectly treated a legitimate city such
as `北京市` as a detailed address.

## Change

- Kept formal AI `directions` filtered through the verified local allowlist.
- Made pending-candidate `direction` an independent trimmed strict string with a
  40-character maximum.
- Made address filtering field-aware: legitimate city labels such as `北京市`
  are accepted, while road/street/number cues and province/city-to-district or
  county hierarchies are rejected.
- Required every candidate name to end in `医院`; department, clinic, practice,
  and center names therefore do not pass candidate cleanup.
- Updated the DeepSeek system prompt with the complete Chinese-hospital-name,
  `医院` suffix, empty-array-on-uncertainty, and forbidden-name-type rules.
- Preserved the three-candidate limit, strict field types and lengths, and
  filtering for links, phone/contact details, recommendation wording, address
  content, and diagnosis/treatment advice.
- Left consent, emergency, verified-result suppression, transport/JSON error,
  and local fallback behavior unchanged.

## TDD evidence

1. RED: the new regression test supplied a valid AI object with
   `directions=['神经内科']`, a `北京大学第一医院` candidate in `北京市`, and
   candidate direction `神经内科`. It failed because `response.ai.used` was
   `False` instead of `True`; cleanup had removed the candidate and selected the
   fallback.
2. RED: the prompt contract failed against the old instructions, and a
   non-hospital name (`神经内科门诊`) leaked through candidate cleanup.
3. RED: focused diagnosis/treatment-advice cases were returned before their
   output-boundary filter was added.
4. GREEN: the focused AI matcher suite passed with 49 tests after the minimal
   policy and safety changes.

## Verification

Run from `apps/api`:

```text
python -m pytest -q
........................................................................ [ 54%]
...........................................................              [100%]
131 passed in 0.71s
```

The task-file whitespace check passed before commit.

## Scope

Changed only:

- `apps/api/app/ai_matcher.py`
- `apps/api/tests/test_ai_matcher.py`
- `.superpowers/sdd/fix-pending-candidate-direction-policy-report.md`

No frontend file was modified. Existing unrelated worktree changes were left
untouched and excluded from the commit.
