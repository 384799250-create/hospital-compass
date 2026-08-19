# 收藏夹抽屉与独立页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为医院搜索结果提供跨搜索保留的收藏夹抽屉，并可放大为独立收藏页面。

**Architecture:** `local-profile.ts` 将收藏 ID 与可展示的医院快照一起持久化，并兼容旧版仅存 ID 的记录。`FavoriteDrawer` 只负责渲染抽屉或整页列表，`page.tsx` 保留搜索状态并负责打开、放大、详情加载和取消收藏。

**Tech Stack:** React 19、TypeScript、CSS Modules、Vitest、Testing Library、浏览器 localStorage。

---

### Task 1: 持久化收藏医院快照

**Files:**
- Modify: `apps/web/lib/local-profile.ts`
- Modify: `apps/web/tests/local-profile.test.ts`

- [ ] **Step 1: 写入失败测试，要求真实医院快照会与 ID 一起保存**

```ts
it('persists a favorite hospital snapshot alongside its ID', () => {
  addFavorite({ id: 'a49c5d1e5de78232', name: '示例医院', city: '广州市', tier: '三级甲等', address: '越秀区中山路 1 号', score: 92, department: '心血管内科', officialWebsiteUrl: 'https://hospital.example.org' });
  expect(getProfile().favoriteHospitals).toEqual([expect.objectContaining({ id: 'a49c5d1e5de78232', name: '示例医院', score: 92 })]);
});
```

- [ ] **Step 2: 运行测试并确认其因 `favoriteHospitals` 尚不存在而失败**

Run: `npm.cmd test -- local-profile.test.ts --run`

Expected: FAIL，断言无法读取 `favoriteHospitals`。

- [ ] **Step 3: 定义并持久化收藏医院快照**

```ts
export type FavoriteHospital = { id: string; name: string; city: string; tier: string; address: string; score: number | null; department: string; officialWebsiteUrl: string | null; };
export type LocalProfile = { favorites: string[]; favoriteHospitals: FavoriteHospital[]; };
export function addFavorite(hospital: FavoriteHospital): LocalProfile {
  const profile = readProfile();
  const snapshot = sanitizeFavoriteHospital(hospital);
  if (!snapshot) return profile;
  return saveProfile({ favorites: [...new Set([...profile.favorites, snapshot.id])], favoriteHospitals: [...profile.favoriteHospitals.filter((item) => item.id !== snapshot.id), snapshot] });
}
```

Implement `sanitizeFavoriteHospital` so malformed snapshot fields are excluded. Old payloads without `favoriteHospitals` must read as `{ favorites, favoriteHospitals: [] }`. Update `removeFavorite` to remove the snapshot too.

- [ ] **Step 4: 运行本地资料测试并确认通过**

Run: `npm.cmd test -- local-profile.test.ts --run`

Expected: PASS。

- [ ] **Step 5: 提交数据层改动**

```bash
git add apps/web/lib/local-profile.ts apps/web/tests/local-profile.test.ts && git commit -m "feat: persist favorite hospital snapshots"
```

### Task 2: 创建可复用的收藏夹内容组件

**Files:**
- Create: `apps/web/app/favorite-drawer.tsx`
- Modify: `apps/web/app/page.module.css`
- Create: `apps/web/tests/favorite-drawer.test.tsx`

- [ ] **Step 1: 写入失败测试，要求抽屉展示收藏医院并可触发放大与移除**

```tsx
it('shows saved hospitals and exposes expand and remove actions', async () => {
  const user = userEvent.setup();
  render(<FavoriteDrawer open favorites={[favorite]} onClose={vi.fn()} onExpand={expand} onRemove={remove} onOpenDetail={vi.fn()} />);
  expect(screen.getByText('示例医院')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: '取消收藏 示例医院' }));
  expect(remove).toHaveBeenCalledWith(favorite.id);
});
```

- [ ] **Step 2: 运行测试并确认其因组件不存在而失败**

Run: `npm.cmd test -- favorite-drawer.test.tsx --run`

Expected: FAIL，模块 `../app/favorite-drawer` 不存在。

- [ ] **Step 3: 实现抽屉和共享医院列表**

```tsx
export function FavoriteDrawer({ open, favorites, onClose, onExpand, onRemove, onOpenDetail }: FavoriteDrawerProps) {
  if (!open) return null;
  return <aside className={styles.favoriteDrawer} aria-label="收藏夹" aria-modal="true" role="dialog">
    <header><div><span>我的收藏</span><h2>收藏夹</h2></div><button type="button" aria-label="放大查看收藏夹" onClick={onExpand}>放大查看</button><button type="button" aria-label="关闭收藏夹" onClick={onClose}>关闭</button></header>
    <FavoriteHospitalList favorites={favorites} onRemove={onRemove} onOpenDetail={onOpenDetail} />
  </aside>;
}
```

Add `FavoriteHospitalList` with an accessible empty state, a score label that uses `暂无保存评分` for `null`, a “查看详情” button, and a symbol-only removal button with an accessible name. Add CSS for a fixed right drawer, backdrop, compact rows, and a full-width small-screen layout. Reuse the same list in page mode with `variant="page"`.

- [ ] **Step 4: 运行组件测试并确认通过**

Run: `npm.cmd test -- favorite-drawer.test.tsx --run`

Expected: PASS。

- [ ] **Step 5: 提交组件改动**

```bash
git add apps/web/app/favorite-drawer.tsx apps/web/app/page.module.css apps/web/tests/favorite-drawer.test.tsx && git commit -m "feat: add favorite drawer component"
```

### Task 3: 在主页面连接收藏夹和独立页面

**Files:**
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/tests/page.test.tsx`

- [ ] **Step 1: 写入失败流程测试，要求收藏后可从导航打开抽屉并放大**

```tsx
it('opens the favorite drawer and expands it without losing results', async () => {
  const user = userEvent.setup();
  await completeFlow(user);
  await user.click((await screen.findAllByRole('button', { name: '收藏 示例医院' }))[0]);
  await user.click(screen.getByRole('button', { name: /收藏夹 1/ }));
  expect(screen.getByRole('dialog', { name: '收藏夹' })).toBeTruthy();
  await user.click(screen.getByRole('button', { name: '放大查看收藏夹' }));
  expect(screen.getByRole('heading', { name: '收藏医院' })).toBeTruthy();
  expect(screen.getByText('示例医院')).toBeTruthy();
});
```

- [ ] **Step 2: 运行测试并确认其因导航入口和页面状态尚不存在而失败**

Run: `npm.cmd test -- page.test.tsx --run`

Expected: FAIL，找不到名称匹配“收藏夹 1”的按钮。

- [ ] **Step 3: 将实时医院结果转换为收藏快照并管理抽屉状态**

```tsx
const [favoriteDrawerOpen, setFavoriteDrawerOpen] = useState(false);
const [favoritePageOpen, setFavoritePageOpen] = useState(false);
const [favoriteHospitals, setFavoriteHospitals] = useState<FavoriteHospital[]>([]);
function favoriteFromResult(hospital: RealtimeHospitalResult): FavoriteHospital {
  return { id: hospital.id, name: hospital.name, city: hospital.city, tier: hospital.tier || '', address: hospital.address || '', score: Number.isFinite(hospital.score) ? hospital.score : null, department: hospital.department || realtimeResponse?.directions.join('、') || '', officialWebsiteUrl: hospital.official_website_url || null };
}
function toggleFavorite(hospital: RealtimeHospitalResult) {
  const profile = favorites.includes(hospital.id) ? removeFavorite(hospital.id) : addFavorite(favoriteFromResult(hospital));
  setFavorites(profile.favorites); setFavoriteHospitals(profile.favoriteHospitals);
}
```

Update both existing favorite buttons to call `toggleFavorite(hospital)`. Render a count-bearing navigation button, `FavoriteDrawer`, and a dedicated full-page section with heading “收藏医院”. The independent page back button closes only that page and leaves the existing result state untouched.

On load and whenever saved IDs lack a snapshot, call `getRealtimeHospitalDetail(id)` and merge a snapshot with `score: null`; catch failures and keep the ID without deleting it. Do not request a new hospital search.

- [ ] **Step 4: 运行页面流程测试并确认通过**

Run: `npm.cmd test -- page.test.tsx --run`

Expected: PASS。

- [ ] **Step 5: 提交页面连接改动**

```bash
git add apps/web/app/page.tsx apps/web/tests/page.test.tsx && git commit -m "feat: add favorite drawer and full page"
```

### Task 4: 运行完整验证

**Files:**
- Verify only: `apps/web`

- [ ] **Step 1: 运行完整前端测试**

Run: `npm.cmd test -- --run`

Expected: 所有测试通过。

- [ ] **Step 2: 运行 TypeScript 类型检查**

Run: `npm.cmd run typecheck`

Expected: 退出码为 0。

- [ ] **Step 3: 运行生产构建**

Run: `npm.cmd run build`

Expected: Vite 构建完成且无 TypeScript 错误。

- [ ] **Step 4: 复查本地服务**

Run: `Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing | Select-Object -ExpandProperty StatusCode`

Expected: `200`。
