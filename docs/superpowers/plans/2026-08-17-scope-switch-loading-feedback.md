# Region Scope Switch Loading Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a ranking-range change visibly in progress while preserving the current hospital list in place.

**Architecture:** Keep the existing `realtimeResponse` rendered during a scope request. Track scope switching independently from other preserved requests, render an accessible status card directly below the scope controls, and apply a non-layout-changing busy treatment to the prior result list.

**Tech Stack:** React 19, TypeScript, CSS Modules, Vitest, Testing Library.

---

### Task 1: Specify Scope-Only Loading Behavior

**Files:**
- Modify: `apps/web/tests/result-controls.test.tsx`

- [x] **Step 1: Write a deferred range-change test**

Add a test with a pending `realtimeSearchHospitals` promise after the initial result. Switch from `市级` to `省级`, then assert:

```tsx
expect(screen.getByRole('status')).toHaveTextContent('正在切换到省级排名');
expect(screen.getByText('保留当前结果，新的医院范围正在刷新')).toBeTruthy();
expect(screen.getByRole('tab', { name: '市级' })).toBeDisabled();
expect(screen.getByLabelText('实时医院排名')).toHaveAttribute('aria-busy', 'true');
expect(screen.getByText('示例医院')).toBeTruthy();
```

- [x] **Step 2: Run the focused test to verify it fails**

Run from `apps/web`:

```powershell
npm.cmd test -- --run tests/result-controls.test.tsx
```

Expected: the assertions fail because no target-scope status card or busy list state exists.

### Task 2: Render the Status Card and Preserve the List

**Files:**
- Modify: `apps/web/app/page.tsx:204-252`
- Modify: `apps/web/app/page.tsx:988-989`

- [x] **Step 1: Keep scope-switch state distinct from other preserved searches**

Extend `searchRealtime` with a final `isScopeSwitch` parameter defaulting to `false`; set `scopeSwitching` from that parameter. Call it as follows:

```tsx
await searchRealtime(nextScope, selectedDirection, true, district, realtimeCity, province, true);
```

Only `switchRealtimeScope` passes `true`; direction and location requests retain the current results without presenting scope-change copy.

- [x] **Step 2: Render target-scope status and busy list semantics**

Create a `SCOPE_LABELS` constant. After each scope bar, render this status card only while `scopeSwitching && realtimeLoading`:

```tsx
<div className={styles.scopeSwitchStatus} role="status" aria-live="polite">
  <span className={styles.scopeSwitchSpinner} aria-hidden="true" />
  <div>
    <strong>正在切换到{SCOPE_LABELS[scope]}排名</strong>
    <p>保留当前结果，新的医院范围正在刷新</p>
  </div>
</div>
```

Apply `aria-busy={scopeSwitching && realtimeLoading}` and `styles.resultsBusy` to the existing realtime ranking list. Do not clear or reposition the list.

- [x] **Step 3: Run the focused test to verify it passes**

Run:

```powershell
npm.cmd test -- --run tests/result-controls.test.tsx
```

Expected: the focused test file passes.

### Task 3: Add Motion-Safe Visual Treatment and Verify

**Files:**
- Modify: `apps/web/app/page.module.css:295-311`

- [x] **Step 1: Style the inline status card and busy list**

Add styles that keep the card under the scope bar and use a transform-only `0.8s` spin:

```css
.scopeSwitchStatus { display:flex; align-items:center; gap:12px; margin-top:10px; padding:13px 14px; border:1px solid #e7cfaa; background:#fff8ec; color:#704a18; }
.scopeSwitchSpinner { width:24px; height:24px; flex:0 0 auto; border:3px solid #e7d2b4; border-top-color:#b86f20; border-radius:50%; animation:button-spin .8s linear infinite; }
.resultsBusy { opacity:.56; pointer-events:none; user-select:none; }
```

Use a responsive rule so the card remains readable at `560px` and a `prefers-reduced-motion` rule that disables only the spinner animation.

- [x] **Step 2: Run front-end verification**

Run from `apps/web`:

```powershell
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
```

Expected: all commands exit with code `0`.

- [x] **Step 3: Run UI mechanical checks**

Run from the repository root:

```powershell
node C:\Users\Administrator\.codex\skills\impeccable\scripts\detect.mjs --json apps/web/app/page.tsx apps/web/app/page.module.css
```

Expected: no new blocking finding associated with the new status card or animation.

- [x] **Step 4: Verify desktop and narrow viewports in the browser**

Open the local web app, submit a recommendation request, switch range, and confirm the card is visible while the previous list remains in place. Repeat at a narrow viewport and ensure the status card and tabs do not overlap.
