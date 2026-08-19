# 结果页顶部小型标题区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将医院推荐结果页顶部的大型宣传横幅压缩为保留品牌氛围的小型标题区，让疾病方向、地区和医院结果更早进入首屏。

**Architecture:** 保持结果页现有 React 状态和数据流，只重构 `page.tsx` 中 Hero 的展示内容并调整 `page.module.css` 的布局规则。标题区从现有 `realtimeResponse`、地址状态和范围标签读取上下文；抽象装饰和固定平台统计移除，不新增后端接口。

**Tech Stack:** React 19、TypeScript、Vite、CSS Modules、Vitest + Testing Library。

---

### Task 1: 固定结果页标题区的回归行为

**Files:**
- Modify: `apps/web/tests/page.test.tsx`

- [x] **Step 1: 写失败测试**

在结果页流程测试中加入断言：结果状态下仍显示标题“找到更适合的医院信息”，并显示当前方向和地区上下文；入口页仍保留原有首页标题。测试使用现有 `completeFlow`，不改变 API mock。

```tsx
it('shows a compact result hero with current matching context', async () => {
  const user = userEvent.setup();
  await completeFlow(user);

  expect(screen.getByRole('heading', { name: '找到更适合的医院信息' })).toBeTruthy();
  expect(screen.getByText('心血管内科 · 广东省 · 广州市 · 市级')).toBeTruthy();
});
```

- [x] **Step 2: 运行测试确认失败**

运行：`npm test -- --run tests/page.test.tsx -t "compact result hero"`

预期：FAIL，因为当前 Hero 没有渲染当前方向和地区上下文。

### Task 2: 实现小型标题区内容

**Files:**
- Modify: `apps/web/app/page.tsx:1003-1011`

- [x] **Step 1: 编写最小实现**

保留 `section.hero` 和标题、免责声明，在标题下增加只显示非空字段的上下文行。使用现有 `realtimeResponse?.directions`、`province`、`city`、`scope` 和 `SCOPE_LABELS`；移除 `heroStats` 与 `artwork` 节点。

```tsx
const resultContext = [
  realtimeResponse?.directions?.join('、'),
  [province, city].filter(Boolean).join(' · '),
  realtimeResponse?.scope ? SCOPE_LABELS[realtimeResponse.scope] : '',
].filter(Boolean);

<section className={styles.hero} aria-labelledby="page-title">
  <div className={styles.heroCopy}>
    <p className={styles.eyebrow}>演示医院信息匹配</p>
    <h1 id="page-title">找到更适合的医院信息</h1>
    <p className={styles.disclaimer}>本工具仅供查找演示医院信息，不提供诊断、治疗或疗效建议。</p>
    {resultContext.length > 0 && <p className={styles.heroContext}>{resultContext.join('  ·  ')}</p>}
  </div>
</section>
```

- [x] **Step 2: 运行回归测试**

运行：`npm test -- --run tests/page.test.tsx -t "compact result hero"`

预期：PASS。

### Task 3: 调整结果页 Hero 的桌面与窄屏布局

**Files:**
- Modify: `apps/web/app/page.module.css:338-341, 279-285`

- [x] **Step 1: 收缩 Hero 样式**

新增只作用于结果状态的 `.heroResults` 规则，设为单列、约 150px 高度、自然流布局，保留浅绿色背景和内边距；结果状态隐藏 `.artwork`、`.heroStats`，输入状态继续使用原 Hero 布局；把 `.search` 的 `margin:0 auto` 保持为自然垂直间距；新增 `.heroContext` 样式。

```css
.heroResults { min-height: 152px; padding: 28px clamp(28px, 8vw, 120px); display:flex; align-items:center; }
.heroResults .heroCopy { max-width: 820px; }
.heroResults h1 { font-size: clamp(30px, 3.2vw, 48px); }
.disclaimer { margin-top: 10px; font-size: 12px; }
.heroContext { margin: 12px 0 0; color: #21635b; font-size: 12px; font-weight: 750; }
.heroResults .artwork, .heroResults .heroStats { display: none; }
.search { margin: 0 auto; }
```

- [x] **Step 2: 校验窄屏规则**

在 `max-width: 850px` 和 `max-width: 560px` 规则中，将 `.heroResults` 内边距缩小为 `24px 22px`、`20px 16px`，标题字号分别限制为 `36px`、`30px`；不要隐藏 `.heroContext`，并保持输入状态 Hero 的原有响应式布局。

- [x] **Step 3: 运行类型检查和构建**

运行：`npm run typecheck` 和 `npm run build`

预期：两个命令均退出码 0；构建只允许已有的 chunk 大小提示。

### Task 4: 完整验证与视觉检查

**Files:**
- Verify: `apps/web/app/page.tsx`
- Verify: `apps/web/app/page.module.css`

- [x] **Step 1: 运行前端全量测试**

运行：`npm test -- --run`

预期：13 个测试文件、50 个测试全部通过。

- [x] **Step 2: 运行 Impeccable detector**

运行：`node C:\Users\Administrator\.codex\skills\impeccable\scripts\detect.mjs --json app/page.tsx`

预期：无新增 detector findings。

- [x] **Step 3: 检查开发页面**

打开 `http://127.0.0.1:5173/`，进入一次匹配结果，确认桌面端结果标题区明显变矮，方向/地区上下文可见，医院结果不被推离首屏；再用窄屏宽度确认标题和上下文不溢出。

- [x] **Step 4: 检查差异**

运行：`git diff --check`

预期：无空白错误或冲突标记。
