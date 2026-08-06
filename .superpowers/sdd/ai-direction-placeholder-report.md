# AI 方向占位降级层实现报告

## 结果

- DeepSeek 成功返回至少一个有效方向、正式匹配结果为空、且 AI 候选经安全清洗后为空时，本地生成最多 3 条方向占位。
- 占位名称为 `<方向>候选医疗机构`，城市使用请求城市或“全国”，理由固定为“AI 已整理出就医方向；此为流程占位，非真实机构名称，待补充或人工核验。”，并显式返回 `placeholder=true`。
- 占位完全由本地代码生成，不增加外部调用；AI 返回的 `placeholder` 字段会被当作越权字段丢弃，不能伪造本地占位。
- 有正式结果、无有效 AI 方向、未同意、紧急请求或模型/传输异常时不生成占位；存在安全合规的普通待核验候选时继续返回该候选并标识 `placeholder=false`。
- 前端将占位卡片标为“AI 方向占位”，固定显示“非真实机构名称”；普通候选显示“待人工核验”。卡片只渲染名称、城市、方向和理由，不渲染收藏、评分、地址、电话或链接。

## TDD 证据

RED：

- 后端新增的占位生成、全国城市回退与 OpenAPI schema 测试先运行，得到 3 个预期失败：候选数组仍为空、`placeholder` schema 字段不存在。
- 前端新增占位展示测试先运行，得到 1 个预期失败：卡片仍显示普通待人工核验标签，没有“AI 方向占位”。

GREEN：

- 最小实现后，后端 3 个定向测试通过。
- 最小实现后，前端占位展示定向测试通过。
- 完整回归中同步更新安全清洗断言：不安全 AI 候选仍被丢弃，随后只能出现不含原始不安全内容的本地占位。

## 修改文件

- `apps/api/app/ai_matcher.py`
- `apps/api/tests/test_ai_matcher.py`
- `apps/api/tests/test_contracts.py`
- `apps/web/lib/api.ts`
- `apps/web/app/page.tsx`
- `apps/web/tests/page.test.tsx`

## 最终验证

- `python -m pytest -q`（`apps/api`）：134 passed。
- `npm.cmd test -- --run`（`apps/web`）：2 files、19 tests passed。
- `npm.cmd run typecheck`（`apps/web`）：通过。
- `npm.cmd run build`（`apps/web`）：通过，Vite production build 完成。

## 提交

- 提交信息：`feat: add AI direction placeholder fallback`
- 提交范围仅包含本任务代码、测试和本报告；未纳入工作区既有的候选安全报告、视觉 CSS 与 Playwright 临时文件。
