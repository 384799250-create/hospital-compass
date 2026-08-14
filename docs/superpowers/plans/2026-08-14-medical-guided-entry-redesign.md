# Medical Guided Entry Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current public entry page with a single warm, guided patient flow that starts with one button, uses AI clarification cards, collects address and preference, then shows disease direction, department, and hospital rankings.

**Architecture:** Keep the existing FastAPI endpoints, hospital database, ranking logic, detail panel, official website/source links, and WeChat appointment text. Extract the new intake state machine into a focused React component, let the page own the hospital-result response and existing result-card renderer, and connect the two through one typed recommendation callback. The landing state hides all secondary actions; later states expose only the controls needed for the current step.

**Tech Stack:** React 19, TypeScript, Vite, CSS Modules, Vitest, Testing Library, existing `/v1/triage`, `/v1/symptom-clarification`, `/v1/realtime-hospital-search`, and `/v1/realtime-hospitals/:id` APIs.

---

## File Map

- Create: `apps/web/app/guided-intake.tsx` - staged landing, symptom, clarification, direction, preference, and location UI plus intake state transitions.
- Modify: `apps/web/app/page.tsx` - mount the guided flow, connect its recommendation callback to the existing realtime search/detail/card rendering, and remove the duplicate legacy entry forms from the primary surface.
- Modify: `apps/web/app/page.module.css` - add the landing, modal, stepper, card, location, preference, loading, error, and reduced-motion styles while preserving hospital result styles.
- Create: `apps/web/tests/guided-intake-flow.test.tsx` - focused flow regression tests with API mocks.
- Modify: `apps/web/tests/symptom-clarification-card.test.tsx` - move selectors and assertions to the new guided flow semantics while retaining coverage of AI clarification behavior.
- Modify: `apps/web/tests/hospital-detail-regression.test.tsx` - exercise the new path to the existing result card/detail footer.
- Read only: `apps/web/lib/api.ts` - reuse existing API types and functions; change only if a missing type is discovered during implementation.
- Do not modify for this redesign: `apps/api/*`; backend behavior is already sufficient and is covered by existing tests.

## Task 1: Lock the New Surface With Failing Tests

**Files:**
- Create: `apps/web/tests/guided-intake-flow.test.tsx`
- Modify: `apps/web/tests/symptom-clarification-card.test.tsx`
- Modify: `apps/web/tests/hospital-detail-regression.test.tsx`

- [ ] **Step 1: Add the landing contract test**

Render `<Page />` and assert that the initial document exposes exactly one interactive control, `开始使用`, has no symptom textbox, no hospital links, and no secondary navigation controls. The assertion should scope to the main page and use accessible roles rather than CSS selectors.

```tsx
it('opens with one primary start action and no secondary interactions', () => {
  render(<Page />);
  expect(screen.getByRole('button', { name: '开始使用' })).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryAllByRole('link')).toHaveLength(0);
  expect(screen.getAllByRole('button')).toHaveLength(1);
});
```

- [ ] **Step 2: Add the staged-flow contract test**

Mock `triageSymptoms`, `clarifySymptoms`, and `realtimeSearchHospitals`. Click `开始使用`, assert the symptom dialog is visible, submit a symptom, answer the returned clarification question, assert the direction/department block appears before the preference controls, submit address and preference, and assert the hospital result callback path is reached.

- [ ] **Step 3: Run the new tests and confirm RED**

Run from `apps/web`:

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx tests/symptom-clarification-card.test.tsx tests/hospital-detail-regression.test.tsx
```

Expected: failures because the current page still renders legacy forms and has no guided landing state.

- [ ] **Step 4: Commit the failing test contract**

```powershell
git add apps/web/tests/guided-intake-flow.test.tsx apps/web/tests/symptom-clarification-card.test.tsx apps/web/tests/hospital-detail-regression.test.tsx
git commit -m "test: define guided medical entry flow"
```

## Task 2: Implement the Landing and Dialog Shell

**Files:**
- Create: `apps/web/app/guided-intake.tsx`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`

- [ ] **Step 1: Define the typed flow boundary**

Add these types at the top of `guided-intake.tsx`:

```tsx
type GuidedStage = 'landing' | 'symptom' | 'clarification' | 'direction' | 'preferences' | 'results';

type GuidedRecommendationInput = {
  query: string;
  direction: string;
  preference: 'overall' | 'specialty' | 'convenience';
  location: { province: string; city: string; district: string };
};

type GuidedIntakeProps = {
  onRecommend: (input: GuidedRecommendationInput) => Promise<void>;
  onStageChange?: (stage: GuidedStage) => void;
};
```

The component owns `stage`, `query`, `triageResponse`, `clarification`, `clarificationAnswers`, selected preference, location fields, loading state, and error state. It must not persist symptom text to local storage.

- [ ] **Step 2: Implement the landing markup**

Render the `医途` wordmark, the approved headline `先说清楚症状，再找到合适的医院`, static non-interactive supporting display, and exactly one button. On click, set stage to `symptom`; expose no anchor links or secondary buttons in this stage.

- [ ] **Step 3: Implement the centered symptom dialog**

Render a native `role="dialog"` with `aria-modal="true"`, title `先告诉我，你哪里不舒服？`, a labelled textarea, four non-submitting quick-example buttons, a continue button disabled for blank input, and the health-information disclaimer. Add an Escape handler that returns to the landing stage and restores focus to `开始使用`.

- [ ] **Step 4: Connect the component in `page.tsx`**

Replace the visible legacy matching form and duplicate realtime form at the primary entry surface with `<GuidedIntake onRecommend={handleGuidedRecommendation} />`. Keep the existing hospital card/detail renderer available for the result stage.

- [ ] **Step 5: Add the shell styles**

Add CSS module classes for the full-viewport landing, centered content, single CTA, scrim, modal, focus states, and mobile layout. Use existing project tokens where possible, keep corner radii at 8px or less, and add:

```css
@media (prefers-reduced-motion: reduce) {
  .guidedDialog,
  .guidedStageContent,
  .guidedResultReveal { animation: none; transition: none; }
}
```

- [ ] **Step 6: Run the landing test and typecheck**

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx
npm.cmd run typecheck
```

Expected: the landing assertions pass; remaining staged-flow assertions may still fail until Tasks 3-5 are complete.

- [ ] **Step 7: Commit the shell**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/app/page.tsx apps/web/app/page.module.css apps/web/tests/guided-intake-flow.test.tsx
git commit -m "feat: add guided medical entry shell"
```

## Task 3: Implement AI Clarification Cards

**Files:**
- Modify: `apps/web/app/guided-intake.tsx`
- Modify: `apps/web/tests/guided-intake-flow.test.tsx`
- Modify: `apps/web/tests/symptom-clarification-card.test.tsx`

- [ ] **Step 1: Add the triage/clarification RED cases**

Cover these behaviors with mocked API responses:

```tsx
it('skips cards when triage is already clear', async () => { /* triage has one confident direction; expect direction block */ });
it('shows one plain-language card for ambiguous triage', async () => { /* expect one region and current progress */ });
it('submits uncertain and custom answers', async () => { /* assert exact clarifySymptoms payload */ });
it('returns to the previous card without losing the answer', async () => { /* answer two cards, go back, edit, continue */ });
it('stops on an emergency response', async () => { /* expect alert and no preference controls */ });
```

- [ ] **Step 2: Implement triage submission**

On symptom submit, call `triageSymptoms({ query, ai_consent: true })`. If there is exactly one confident direction, skip clarification and show the direction stage. Otherwise call `clarifySymptoms({ query, answers: [], ai_consent: true })` and enter the clarification stage when the response is `NEEDS_CLARIFICATION`.

- [ ] **Step 3: Implement the single-card renderer**

Render one accessible radiogroup from `clarification.question.options`, plus `不确定` and `以上都不符合，我自己填写`. When the custom option is selected, reveal a labelled textarea. Disable continue until a valid option or non-blank custom answer exists.

- [ ] **Step 4: Implement answer history and back navigation**

Store answers as `SymptomClarificationAnswer[]`, append the current answer before calling the API, and keep a history of prior responses sufficient to restore the previous question and selected value. The back button must be keyboard reachable and must not issue an API call.

- [ ] **Step 5: Implement completion and error states**

For `COMPLETE`, replace the card with the returned directions and move to `direction`. For `EMERGENCY`, clear the card and render an alert with the urgent message. Catch request failures into a retryable alert without losing the query.

- [ ] **Step 6: Run clarification tests**

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx tests/symptom-clarification-card.test.tsx
```

Expected: all clarification tests pass.

- [ ] **Step 7: Commit clarification flow**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/tests/guided-intake-flow.test.tsx apps/web/tests/symptom-clarification-card.test.tsx
git commit -m "feat: add AI symptom clarification cards"
```

## Task 4: Implement Direction Confirmation, Preference, and Location

**Files:**
- Modify: `apps/web/app/guided-intake.tsx`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Modify: `apps/web/tests/guided-intake-flow.test.tsx`

- [ ] **Step 1: Add the direction-before-results RED assertion**

After a `COMPLETE` response, assert that the possible disease direction, `建议就诊科室`, basis, disclaimer, and a continue button render before any hospital card or score.

- [ ] **Step 2: Implement the direction stage**

Render all returned directions, the possible-disease line when present, the recommended department, basis, urgent warning, and the non-diagnosis disclaimer. Continue uses the selected direction department as the `direction` field for recommendation.

- [ ] **Step 3: Implement preference cards**

Render three native radio controls labelled `综合信息`, `专科方向`, and `就近便利`; default to `overall`. Keep the labels explanatory but short, and expose the selected state through `aria-checked`.

- [ ] **Step 4: Implement address controls and location fallback**

Reuse the existing area data. Render province, city, and district selects plus `使用当前位置`. On geolocation success, populate the fields; on denial, timeout, unsupported browser, or reverse-geocode failure, show a status message and leave manual selects usable.

- [ ] **Step 5: Submit the recommendation input**

Validate province and city before submission. Call the page callback with:

```tsx
{
  query,
  direction: selectedDirection.department,
  preference,
  location: { province, city, district },
}
```

Show a loading state and disable the submit button while the callback is pending.

- [ ] **Step 6: Run preference/location tests**

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx
```

Expected: disease direction appears before preference controls, the exact location payload is sent, and invalid/failed location states remain recoverable.

- [ ] **Step 7: Commit the final intake stages**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/app/page.tsx apps/web/app/page.module.css apps/web/tests/guided-intake-flow.test.tsx
git commit -m "feat: collect guided location and care preference"
```

## Task 5: Connect Hospital Ranking and Result Order

**Files:**
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/guided-intake.tsx`
- Modify: `apps/web/tests/guided-intake-flow.test.tsx`
- Modify: `apps/web/tests/hospital-detail-regression.test.tsx`

- [ ] **Step 1: Add the callback integration RED test**

Mock a successful realtime response and assert that the request includes the selected direction, province/city/district, `location_level`, `scope`, and `hospital_tiers`. Assert that the direction/department summary appears before the first hospital card.

- [ ] **Step 2: Implement `handleGuidedRecommendation` in `page.tsx`**

Set the existing realtime query/location/preference state, call `realtimeSearchHospitals` with the existing request shape and `confirmed_direction`, store the response, clear any stale detail, and set the guided stage to `results` through the callback completion.

- [ ] **Step 3: Reuse the current hospital card renderer**

Keep the existing `renderRealtimeCard` output, including score breakdown, official website, public source, hospital detail, and `预约方式：医院公众号`. Do not introduce a second card implementation.

- [ ] **Step 4: Render result sections in the approved order**

Place the triage direction summary above the cards. Render hospital cards only after a successful response. Keep search errors, no-results fallback, emergency state, and retry actions visible within the guided dialog/result surface.

- [ ] **Step 5: Update detail regression coverage**

Drive the test through `开始使用` and the minimum mocked steps, then assert the public source, official website link, appointment text, and the existing detail action remain present.

- [ ] **Step 6: Run integration tests**

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx tests/hospital-detail-regression.test.tsx tests/symptom-clarification-card.test.tsx
```

Expected: all guided flow, detail, and clarification tests pass.

- [ ] **Step 7: Commit result integration**

```powershell
git add apps/web/app/page.tsx apps/web/app/guided-intake.tsx apps/web/tests/guided-intake-flow.test.tsx apps/web/tests/hospital-detail-regression.test.tsx
git commit -m "feat: show guided direction before hospital results"
```

## Task 6: Finish Responsive Motion and Accessibility

**Files:**
- Modify: `apps/web/app/guided-intake.tsx`
- Modify: `apps/web/app/page.module.css`
- Modify: `apps/web/tests/guided-intake-flow.test.tsx`

- [ ] **Step 1: Add keyboard and reduced-motion tests**

Assert that Escape closes the dialog, the initial start button regains focus, the selected radio can be changed by keyboard, and the dialog has `aria-modal="true"` and a labelled heading.

- [ ] **Step 2: Implement motion and focus management**

Use CSS transitions for scrim/dialog/card replacement, `requestAnimationFrame` only for focus/scroll handoff, and a `prefers-reduced-motion` override. Keep the current step content visible during transitions and avoid layout shift by using stable dialog dimensions.

- [ ] **Step 3: Add mobile rules**

At narrow widths, make the dialog nearly full width with safe padding, stack address fields, keep the primary action reachable without horizontal scrolling, and ensure long hospital names and custom answers wrap inside their parents.

- [ ] **Step 4: Run focused tests and typecheck**

```powershell
npm.cmd test -- --run tests/guided-intake-flow.test.tsx tests/symptom-clarification-card.test.tsx tests/hospital-detail-regression.test.tsx
npm.cmd run typecheck
```

- [ ] **Step 5: Commit polish pass**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/app/page.module.css apps/web/tests/guided-intake-flow.test.tsx
git commit -m "feat: polish guided intake motion and accessibility"
```

## Task 7: Full Verification and Visual QA

**Files:**
- Modify only if verification exposes a defect: `apps/web/app/guided-intake.tsx`, `apps/web/app/page.tsx`, `apps/web/app/page.module.css`, or the focused tests.

- [ ] **Step 1: Run the complete API suite without changing backend behavior**

From `apps/api`:

```powershell
python -m pytest -q
```

Expected: all existing API tests pass.

- [ ] **Step 2: Run the complete web suite and record unrelated legacy failures**

From `apps/web`:

```powershell
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
```

The old page tests currently contain legacy labels; update only assertions that intentionally describe the replaced entry surface. Do not weaken hospital detail, clarification, accessibility, or persistence assertions.

- [ ] **Step 3: Run the Impeccable detector once over changed UI targets**

```powershell
node C:\Users\Administrator\.codex\skills\impeccable\scripts\detect.mjs --json apps/web/app/guided-intake.tsx apps/web/app/page.tsx apps/web/app/page.module.css
```

Fix mechanical findings that conflict with the approved design, then do not rerun the detector.

- [ ] **Step 4: Capture desktop and mobile screenshots**

Use the running Vite page at `http://127.0.0.1:5173` to capture at least one desktop and one narrow mobile viewport for the landing, dialog, clarification card, and result order. Check that only the start button is interactive in the landing state, the dialog stays inside the viewport, text does not overlap, and the hospital footer links remain visible.

- [ ] **Step 5: Commit the verification record**

```powershell
git add apps/web
git commit -m "test: verify guided medical entry redesign"
```

