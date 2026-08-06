# 实时医院检索与四级排名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以博查公开网页检索为资料来源，提供四级地域过滤、前 10 名排序和医院详情。

**Architecture:** FastAPI 新增独立的博查适配器、页面结果规范化器与实时排名服务；React 搜索表单扩展为位置和范围选择，并渲染排名及详情抽屉。DeepSeek 仅用于已有的就医方向整理，不直接生成医院资料。

**Tech Stack:** FastAPI、Pydantic、Python 标准库 HTTP、Vitest、React、TypeScript、博查 Web Search API。

## Global Constraints

- 博查密钥仅从 `BOCHA_API_KEY` 环境变量读取，禁止写入代码、日志、测试快照或前端。
- 仅将医院官网或官方授权域名标记为挂号链接。
- 每次最多返回 10 条结果；默认地域范围为 `district`。
- 无 AI 授权不得发送症状文本给 DeepSeek；紧急症状不得发起实时检索。

---

### Task 1: 实时检索请求与地域模型

**Files:**
- Modify: `apps/api/app/schemas.py`
- Create: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_realtime_search.py`

**Interfaces:**
- Produces `RealtimeSearchRequest(query, location, scope, ai_consent)` and `Location(province, city, district)`.
- Produces `parse_location()` and `scope_matches()`.

- [ ] 写失败测试：默认 `district`、四种合法范围、空位置/超长位置返回 400；省、市、区县边界过滤正确。
- [ ] 运行 `python -m pytest -q apps/api/tests/test_realtime_search.py -k location`，确认失败。
- [ ] 实现严格 Pydantic 请求模型及 `scope_matches`，全国直接通过、省市区县逐层精确匹配。
- [ ] 再运行同一测试，确认通过。
- [ ] 提交：`feat(api): add realtime search location scopes`。

### Task 2: 博查检索适配器与公开来源规范化

**Files:**
- Create: `apps/api/app/bocha_search.py`
- Modify: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_bocha_search.py`

**Interfaces:**
- Consumes `BOCHA_API_KEY`、查询词和每页条数。
- Produces `SearchDocument(title, url, snippet, fetched_at)`；`HospitalCandidate` 含名称、地址层级、科室、介绍、医生、官方链接、来源。

- [ ] 写失败测试：无密钥时返回安全的服务不可用结果；请求带 Bearer 鉴权但日志不含密钥；非官方域名不得成为挂号链接。
- [ ] 运行 `python -m pytest -q apps/api/tests/test_bocha_search.py`，确认失败。
- [ ] 实现 `BochaSearchClient`，10 秒超时、JSON 校验、搜索结果规范化；使用医院官网/卫健委/官方挂号域名白名单判定链接类型。
- [ ] 增加测试：重复医院按标准化名称和市级地域合并，保留来源更新时间更近的记录。
- [ ] 运行适配器测试，确认通过。
- [ ] 提交：`feat(api): add Bocha public hospital search adapter`。

### Task 3: 前 10 名实时排名接口

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_contracts.py`

**Interfaces:**
- Produces `POST /v1/realtime-hospital-search`，响应 `directions`、`scope`、`results[:10]`、`sources`、`fetched_at`。

- [ ] 写失败测试：紧急输入不调用博查；未同意 AI 时不调用 DeepSeek；范围不足 10 条不跨范围补齐；结果按 35/25/20/10/10 排序。
- [ ] 运行 `python -m pytest -q apps/api/tests/test_contracts.py -k realtime`，确认失败。
- [ ] 实现请求编排：复用紧急识别和 AI 方向，生成官方来源查询、筛选地域、计算分数、按来源时间与完整度打破平局。
- [ ] 返回明确的 `SEARCH_UNAVAILABLE`、`NO_RESULTS` 和 `EMERGENCY` 状态，绝不伪造医院。
- [ ] 运行 API 全量测试，确认通过。
- [ ] 提交：`feat(api): add realtime hospital ranking endpoint`。

### Task 4: 医院详情接口

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/realtime_search.py`
- Test: `apps/api/tests/test_contracts.py`

**Interfaces:**
- Produces `GET /v1/realtime-hospitals/{result_id}?query_context=...`。

- [ ] 写失败测试：结果 ID 无效返回 404；详情只返回相关科室；医生和挂号链接必须带来源；非官方链接不得显示为挂号。
- [ ] 实现短期内存结果会话（15 分钟 TTL）和详情聚合；过期 ID 返回明确错误。
- [ ] 运行相关 API 测试，确认通过。
- [ ] 提交：`feat(api): add realtime hospital details`。

### Task 5: 前端地域筛选、前十排名与详情抽屉

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Test: `apps/web/tests/page.test.tsx`

- [ ] 写失败测试：默认市区级、四级范围传参、最多渲染 10 张卡、详情按钮加载并展示科室/医生/官方挂号链接。
- [ ] 运行 `npm.cmd test -- --run`，确认失败。
- [ ] 增加省市区字段、范围下拉、实时搜索状态；结果卡显示名次、综合分、理由、来源与抓取时间。
- [ ] 实现详情抽屉；外部挂号链接添加“官方渠道”标签和新窗口安全属性。
- [ ] 实现无授权、紧急、无结果、检索服务异常的可读反馈。
- [ ] 运行前端测试、`npm.cmd run typecheck`、`npm.cmd run build`，确认通过。
- [ ] 提交：`feat(web): add realtime hospital ranking experience`。

### Task 6: 端到端验证与文档

**Files:**
- Modify: `work/docs/hospital-ranking-search-requirements.md`
- Modify: `work/docs/superpowers/specs/2026-08-06-realtime-hospital-search-design.md`

- [ ] 配置本地 `BOCHA_API_KEY` 后，验证市区、市、省、全国四种范围各一次。
- [ ] 验证前 10 上限、详情来源、挂号链接域名、紧急输入和缺失密钥路径。
- [ ] 更新文档的运行配置与验收记录，不包含任何密钥。
- [ ] 运行 API、前端测试及生产构建。
- [ ] 提交：`docs: document realtime hospital search verification`。

## Self-review

- 需求中的四级地域、前 10、详情、公开来源、AI 授权、紧急提示和失败状态均被 Task 1–6 覆盖。
- 所有环境密钥约束集中在 Global Constraints 与 Task 2。
- 每项任务均包含失败测试、最小实现、通过测试和独立提交。
