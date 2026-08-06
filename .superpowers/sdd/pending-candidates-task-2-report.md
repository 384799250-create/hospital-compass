# Pending Candidates Task 2 Report

## Delivered

- Extended the web AI-match response contract with `pending_candidates`, whose items contain `name`, `city`, `direction`, and `reason`.
- Added a separate candidate section after the formal matching-results area. It appears only for non-empty AI candidates when there are no verified hospital results and the response is not an emergency.
- Candidate cards display only the approved fields plus the `待人工核验` label; they have no score, address, phone, source link, favorite control, or recommendation copy.
- Kept the pre-existing responsive `aiConsent` visual change in `page.module.css` unstaged and unmodified.

## TDD evidence

The tests were introduced before the UI implementation. The first focused run failed because the candidate heading was absent. After the minimal section was added, the empty-list and verified-result tests failed in turn; the render condition was then narrowed to enforce both requirements.

## Verification

From `apps/web`:

```text
npm.cmd test -- --run
2 passed, 18 passed

npm.cmd run typecheck
tsc --noEmit exited 0

npm.cmd run build
vite build exited 0
```

## Commit scope

The task commit includes the API type, page rendering, task CSS additions, page tests, and this report. Existing edits to the backend re-review report, responsive `aiConsent` CSS rule, and `.playwright-cli/` remain outside the commit.
