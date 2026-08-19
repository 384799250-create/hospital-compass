# Specialty Score Evidence Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Show the public specialty-capability evidence that produces a specialty score, separately from hospital-wide rankings.

**Architecture:** Extend the existing \`specialty_evidence\` result payload with a normalized record made from an explicit, direction-matching source sentence when the source itself grants specialty strength. Keep directional capability records and specialty rankings in the specialty group; send generic rankings to a distinct group in the existing payload. The React card classifies those records by specialty/department and rank, then renders separate labeled sections.

**Tech Stack:** Python 3.12, FastAPI response dictionaries, pytest, React 19, TypeScript, Vitest, Testing Library.

---

### Task 1: Return Source-Backed Specialty Capability Evidence

**Files:**

- Modify: \`apps/api/app/realtime_search.py:582-611\`
- Modify: \`apps/api/tests/test_realtime_search.py:854-879\`

- [ ] **Step 1: Write the failing backend regression test**

Add this test beside the existing visible-evidence tests:

\`\`\`python
def test_rank_result_exposes_source_backed_capability_before_general_ranking():
    candidate = HospitalCandidate(
        name='合浦县人民医院', city='北海市', tier='三级甲等',
        ranking_evidence=({
            'specialty': '', 'rank': 765, 'year': 2024,
            'ranking_source_name': '2024年度全国三甲医院综合实力排名',
        },),
        sources=[SearchDocument(
            title='医院简介 - 合浦县人民医院',
            url='https://hospital.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。北海市重点（建设）学科为神经内科。',
            fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '合浦县'},
        scope='district',
    )

    evidence = ranked[0]['specialty_evidence']
    assert evidence[0] == {
        'department': '神经内科',
        'strength_level': '神经内科为广西医疗卫生重点学科（县级）',
        'source': 'https://hospital.example.org/about',
        'ranking_source_name': '医院简介 - 合浦县人民医院',
        'verification_status': '公开资料',
    }
    assert evidence[1]['rank'] == 765
    assert ranked[0]['score_breakdown']['specialty'] == 82.0
\`\`\`

- [ ] **Step 2: Run the test to verify it fails**

Run:

\`\`\`powershell
python -m pytest apps/api/tests/test_realtime_search.py::test_rank_result_exposes_source_backed_capability_before_general_ranking -v
\`\`\`

Expected: failure because the first result evidence is the generic ranking and no source-backed capability record exists.

- [ ] **Step 3: Add minimal source-evidence extraction and merge it into visible evidence**

In \`apps/api/app/realtime_search.py\`, add an \`_source_capability_evidence\` helper before \`_visible_evidence\`. It must only return records when the source passes \`_source_has_direct_specialty_evidence\`; split its snippet by sentence punctuation; keep sentences containing both a direction alias and one of the direct-specialty markers; derive the first non-empty direction as \`department\`; and return this record shape:

\`\`\`python
{
    'department': direction,
    'strength_level': sentence.strip(' 。；;'),
    'source': source.url,
    'ranking_source_name': source.title,
    'verification_status': '公开资料',
}
\`\`\`

Update \`_visible_evidence\` to accept the candidate source and return the order below:

\`\`\`python
directional = [item for item in evidence if _evidence_matches_direction(item, directions)]
source_capabilities = _source_capability_evidence(source, directions, profile)
general_rankings = _ordered_general_rankings(candidate)
return _deduplicate_evidence([*directional, *source_capabilities, *general_rankings])
\`\`\`

Update the \`rank_candidates\` result assembly to call \`_visible_evidence(candidate, source, directions, profile)\`.

- [ ] **Step 4: Run the backend regression test to verify it passes**

Run:

\`\`\`powershell
python -m pytest apps/api/tests/test_realtime_search.py::test_rank_result_exposes_source_backed_capability_before_general_ranking -v
\`\`\`

Expected: \`1 passed\`.

- [ ] **Step 5: Commit the backend change**

\`\`\`powershell
git add apps/api/app/realtime_search.py apps/api/tests/test_realtime_search.py
git commit -m "feat: expose specialty score source evidence"
\`\`\`

### Task 2: Render Specialty and Hospital-Strength Evidence Separately

**Files:**

- Modify: \`apps/web/lib/api.ts:61-75\`
- Modify: \`apps/web/app/page.tsx:737-789\`
- Modify: \`apps/web/app/page.module.css:221-225\`
- Modify: \`apps/web/tests/result-controls.test.tsx:114-146\`

- [ ] **Step 1: Write the failing frontend regression test**

Replace the current generic-ranking-only evidence fixture with a direct capability record followed by a generic ranking record, then assert:

\`\`\`tsx
expect(await screen.findByText('专科能力依据')).toBeTruthy();
expect(screen.getByText(/神经内科.*广西医疗卫生重点学科/)).toBeTruthy();
expect(screen.getByText('医院综合实力依据')).toBeTruthy();
expect(screen.getByText(/2024年全国综合排名第1552名/)).toBeTruthy();
expect(screen.queryByText('权威专科依据')).toBeNull();
\`\`\`

- [ ] **Step 2: Run the test to verify it fails**

Run from \`apps/web\`:

\`\`\`powershell
npm test -- --run tests/result-controls.test.tsx
\`\`\`

Expected: failure because the card renders one \`相关排名依据\` block and does not render the source capability record as an independent group.

- [ ] **Step 3: Add types and separate evidence groups in the result card**

Add \`strength_level?: string\` to the \`specialty_evidence\` item type in \`apps/web/lib/api.ts\`.

In \`renderRealtimeCard\`, keep the current deduplication then derive:

\`\`\`tsx
const specialtyCapabilityEvidence = evidenceItems.filter((item) => Boolean(
  (item.department?.trim() || item.specialty?.trim()) && !item.rank,
));
const specialtyRankingEvidence = evidenceItems.filter((item) => Boolean(
  item.rank && (item.department?.trim() || item.specialty?.trim()),
));
const hospitalStrengthEvidence = evidenceItems.filter((item) => Boolean(
  item.rank && !(item.department?.trim() || item.specialty?.trim()),
));
\`\`\`

Render \`specialtyCapabilityEvidence\` and \`specialtyRankingEvidence\` in a \`专科能力依据\` block. Render \`hospitalStrengthEvidence\` in a separate \`医院综合实力依据\` block. Capability rows use \`department || specialty\` plus \`strength_level\`; ranking rows keep the existing year/title/rank text. Keep source links and verification status on every row.

- [ ] **Step 4: Add scoped visual differentiation**

Use the existing \`.specialtyEvidence\` base style for both sections. Add a \`.hospitalStrengthEvidence\` modifier in \`apps/web/app/page.module.css\` with a neutral white background and \`#d5e6e1\` border so hospital-wide rankings are visibly secondary to the green specialty-capability section.

- [ ] **Step 5: Run the frontend regression test to verify it passes**

Run from \`apps/web\`:

\`\`\`powershell
npm test -- --run tests/result-controls.test.tsx
\`\`\`

Expected: the focused test file passes with no failed assertions.

- [ ] **Step 6: Commit the frontend change**

\`\`\`powershell
git add apps/web/lib/api.ts apps/web/app/page.tsx apps/web/app/page.module.css apps/web/tests/result-controls.test.tsx
git commit -m "feat: separate specialty and hospital evidence"
\`\`\`

### Task 3: Verify the Integrated User Scenario

**Files:**

- Modify: none

- [ ] **Step 1: Run the relevant backend test suite**

\`\`\`powershell
python -m pytest apps/api/tests/test_realtime_search.py -q
\`\`\`

Expected: all tests pass.

- [ ] **Step 2: Run the relevant frontend tests and type check**

Run from \`apps/web\`:

\`\`\`powershell
npm test -- --run tests/result-controls.test.tsx tests/result-score.test.ts
npm run typecheck
\`\`\`

Expected: both commands exit with code 0.

- [ ] **Step 3: Reproduce the hospital response through the local API**

\`\`\`powershell
$payload = @{ query = '脑卒中'; location = @{ province = '广西壮族自治区'; city = '北海市'; district = '合浦县' }; location_level = 'district'; scope = 'district'; ai_consent = $false; confirmed_direction = '神经内科'; hospital_tiers = @('tertiary_a') } | ConvertTo-Json -Depth 5
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/v1/realtime-hospital-search' -Method Post -ContentType 'application/json; charset=utf-8' -Body $payload
$response.results | Where-Object name -eq '合浦县人民医院' | ConvertTo-Json -Depth 10
\`\`\`

Expected: \`specialty_evidence\` contains a \`department\` of \`神经内科\` with the corresponding \`strength_level\`, plus a separate generic ranking record with no department or specialty.

- [ ] **Step 4: Confirm no unrelated edits are staged**

\`\`\`powershell
git status --short
\`\`\`

Expected: only user-owned pre-existing changes remain; do not stage or revert them.
