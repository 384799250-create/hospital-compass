# AI-Driven Intake UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with checkpoints.

**Goal:** Make AI the sole source for clarification questions, question count, possible disease directions, and departments, while polishing the guided intake UI and keeping safe emergency handling.

**Architecture:** The clarification service will use one validated AI decision contract on every non-emergency round. The API will return HTTP 503 when AI is unavailable or returns unusable output, and the client will preserve the current step and retry without falling back to local disease rules. The existing guided intake stages remain intact, with improved status/error presentation and dynamic progress.

**Tech Stack:** FastAPI, Pydantic, Python 3.12, React 19, TypeScript, CSS Modules, Vitest, Testing Library, Playwright/browser QA.

---

### Task 1: Lock the AI-only backend contract with failing tests

**Files:**
- Modify: `apps/api/tests/test_symptom_clarification.py`
- Modify: `apps/api/tests/test_contracts.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Add failing tests for AI-unavailable behavior**

Add tests asserting that a non-emergency request with `environ={}` raises the clarification-unavailable error instead of returning a fallback question or local direction. Add an API contract test asserting `POST /v1/symptom-clarification` returns HTTP 503 with a stable detail message when the error is raised.

```python
def test_ai_unavailable_does_not_use_local_question_or_direction():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('不舒服', answers=[], ai_consent=True, environ={})

def test_clarification_endpoint_returns_503_when_ai_is_unavailable(client, monkeypatch):
    monkeypatch.setattr('app.main.clarify_symptoms', lambda *args, **kwargs: (_ for _ in ()).throw(ClarificationUnavailableError()))
    response = client.post('/v1/symptom-clarification', json={
        'query': '不舒服', 'answers': [], 'ai_consent': True,
    })
    assert response.status_code == 503
    assert response.json()['detail'] == 'AI clarification is temporarily unavailable'
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
cd apps/api
python -m pytest -q tests/test_symptom_clarification.py tests/test_contracts.py -k "clarification or symptom"
```

Expected: FAIL because the exception class and 503 route handling do not exist.

- [ ] **Step 3: Add the explicit unavailable exception and route mapping**

In `apps/api/app/symptom_clarification.py`, define `ClarificationUnavailableError`. In `apps/api/app/main.py`, import it and wrap the threadpool call:

```python
try:
    return await run_in_threadpool(clarify_symptoms, ...)
except ClarificationUnavailableError as exc:
    raise HTTPException(status_code=503, detail='AI clarification is temporarily unavailable') from exc
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same command. Expected: the new tests pass while existing contract tests remain green.

- [ ] **Step 5: Commit the contract change**

```powershell
git add apps/api/app/main.py apps/api/app/symptom_clarification.py apps/api/tests/test_symptom_clarification.py apps/api/tests/test_contracts.py
git commit -m "feat: expose AI clarification unavailability"
```

### Task 2: Remove local disease/question fallback and enforce AI decisions

**Files:**
- Modify: `apps/api/app/symptom_clarification.py:QUESTION, _fallback_question, _fallback_follow_up_question, clarify_symptoms`
- Modify: `apps/api/tests/test_symptom_clarification.py`

- [ ] **Step 1: Add failing tests for AI-only multi-round decisions**

Add tests covering:

```python
def test_ai_controls_follow_up_and_completion():
    # transport returns an AI question, then an AI completion payload
    assert first['status'] == 'NEEDS_CLARIFICATION'
    assert second['status'] == 'COMPLETE'
    assert second['directions'][0]['department'] == '全科医学科'

def test_invalid_ai_direction_does_not_return_local_disease_guess():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('胸闷', answers=[{'question_id': 'location', 'value': '胸口'}], ...)

def test_ai_question_is_required_for_first_round():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('头疼', answers=[], ai_consent=True, environ={})
```

Keep the emergency test: red-flag answers must still return `EMERGENCY` without an AI call.

- [ ] **Step 2: Run the focused symptom tests and verify RED**

Run:

```powershell
cd apps/api
python -m pytest -q tests/test_symptom_clarification.py
```

Expected: new tests fail because current code returns deterministic questions/directions.

- [ ] **Step 3: Make the clarification service AI-only**

Change `clarify_symptoms` so that, after the emergency check:

```python
if not answers:
    question = _ai_question(...)
    if question is None:
        raise ClarificationUnavailableError()
    return needs_clarification(question)

decision = _ai_next_step(...)
if decision is None:
    raise ClarificationUnavailableError()
if decision['status'] == 'NEEDS_CLARIFICATION':
    return needs_clarification(decision['question'])
return complete(decision['directions'], decision['urgent_warning'])
```

Delete the local `QUESTION`, `HEADACHE_QUESTION`, `DURATION_QUESTION`, `_fallback_question`, `_fallback_follow_up_question`, and the local disease-direction branches. Keep `_validate_question`, `_parse_directions`, duplicate filtering, maximum question count, and red-flag detection. At the maximum count, accept only an AI `COMPLETE` response; otherwise raise `ClarificationUnavailableError`.

- [ ] **Step 4: Run the symptom tests and verify GREEN**

Run the focused command. Expected: all AI sequence tests, safety tests, and the new no-fallback tests pass.

- [ ] **Step 5: Commit the AI-only backend behavior**

```powershell
git add apps/api/app/symptom_clarification.py apps/api/tests/test_symptom_clarification.py
git commit -m "feat: make AI the source of symptom clarification"
```

### Task 3: Preserve intake state and add retry-aware UI states

**Files:**
- Modify: `apps/web/lib/api.ts:MatchApiError, clarifySymptoms`
- Modify: `apps/web/app/guided-intake.tsx:answerClarification, beginTriage`
- Modify: `apps/web/app/page.module.css:guided status/error styles`
- Test: `apps/web/tests/guided-intake-flow.test.tsx`
- Test: `apps/web/tests/symptom-clarification-card.test.tsx`

- [ ] **Step 1: Add failing UI tests for retry and AI status**

Add tests that mock a 503 first and success second, then assert the original symptom, selected answer, question card, and a retry action remain visible. Add tests that assert the clarification card exposes an `aria-live="polite"` status while loading and displays the dynamic progress returned by the API.

```tsx
expect(screen.getByRole('alert')).toHaveTextContent('智能整理服务暂时不可用，请重试。');
expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
expect(screen.getByText('第 2 / 2 个问题')).toBeTruthy();
```

- [ ] **Step 2: Run the focused web tests and verify RED**

Run:

```powershell
cd apps/web
npm.cmd test -- --run tests/guided-intake-flow.test.tsx tests/symptom-clarification-card.test.tsx
```

Expected: FAIL because there is no retry state or live AI status yet.

- [ ] **Step 3: Implement a pending clarification request**

In `guided-intake.tsx`, keep the submitted answer in a `pendingAnswer` state until the API succeeds. Extract the request into `continueClarification(answer)` so both the first click and retry use the same payload. On a `MatchApiError` with status 503, keep the current card and answer, show the retry button, and do not reset the form. On success, append the answer exactly once and transition based on `NEEDS_CLARIFICATION`, `COMPLETE`, or `EMERGENCY`.

Render a concise live status:

```tsx
{loading && <p className={styles.guidedStatus} aria-live="polite">AI 正在根据你的回答调整问题…</p>}
{error && <div role="alert" className={styles.guidedError}>...</div>}
{error && pendingAnswer && <button type="button" onClick={() => void continueClarification(pendingAnswer)}>重试</button>}
```

Use the same 503-specific message during initial symptom submission and clarification. Preserve the current question and selected option on failure.

- [ ] **Step 4: Refine the card visual hierarchy and responsive states**

In `page.module.css`, introduce shared tokens for the guided surface, make the question heading the dominant element, give options a stable minimum height and clear selected/focus state, style progress as quiet metadata, and add a compact status row with a non-blocking spinner. Keep the existing light green paper theme, 4px radius system, keyboard outlines, reduced-motion rule, and single-column mobile layout. Ensure the retry action has the same contrast as the primary action without creating two competing primary buttons.

- [ ] **Step 5: Run the focused web tests and verify GREEN**

Run the same Vitest command. Expected: all existing card-flow tests and retry/status tests pass.

- [ ] **Step 6: Commit the UI state change**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/app/page.module.css apps/web/lib/api.ts apps/web/tests/guided-intake-flow.test.tsx apps/web/tests/symptom-clarification-card.test.tsx
git commit -m "feat: add retryable AI clarification states"
```

### Task 4: Full verification and browser visual QA

**Files:**
- Modify only if QA finds a concrete issue: `apps/web/app/guided-intake.tsx`, `apps/web/app/page.module.css`
- Test: all existing API and web tests

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
cd apps/api
python -m pytest -q
cd ..\web
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
```

Expected: all backend tests pass, all web tests pass, `tsc --noEmit` exits 0, and Vite produces `dist/` successfully.

- [ ] **Step 2: Start or reload the local services**

Use the existing project launcher. Verify `http://127.0.0.1:5173` and `http://127.0.0.1:8001/docs` respond with HTTP 200.

- [ ] **Step 3: Exercise the real AI flow in the browser**

Check these paths at desktop and mobile widths:

1. Start page shows only the start action.
2. Symptom submission shows loading state and then one AI question.
3. An unresolved answer shows a second AI question with updated progress.
4. AI completion shows possible diseases and department before preferences.
5. Simulated 503 preserves input and exposes retry.
6. Red-flag response interrupts normal flow with the emergency notice.

- [ ] **Step 4: Run the Impeccable detector once over changed UI files**

```powershell
node C:\Users\Administrator\.codex\skills\impeccable\scripts\detect.mjs --json apps/web/app/guided-intake.tsx apps/web/app/page.module.css
```

Fix only concrete findings, rerun the relevant tests, and record any residual warning in the handoff.

- [ ] **Step 5: Commit final verification adjustments**

```powershell
git add apps/web/app/guided-intake.tsx apps/web/app/page.module.css
git commit -m "chore: verify AI intake UI"
```
