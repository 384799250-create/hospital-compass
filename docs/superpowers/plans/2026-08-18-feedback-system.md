# 联网反馈与后台查看实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在导航栏提供用户反馈入口，将反馈安全保存到后端，并通过受保护的后台页面查看和标记处理状态。

**Architecture:** 前端使用同源弹窗提交分类、正文和可选联系方式；后端新增反馈存储模块和公开提交接口。管理员页面使用服务端配置的 `FEEDBACK_ADMIN_TOKEN` 登录，浏览器只保存短期会话令牌，列表接口返回分页数据并支持状态筛选与更新。单实例阶段使用 SQLite，存储模块保持独立，后续可替换为 PostgreSQL。

**Tech Stack:** React + TypeScript + CSS Modules、FastAPI + Pydantic、SQLite、pytest、Vitest。

---

### Task 1: 反馈存储与 API 契约

**Files:**
- Create: `apps/api/app/feedback_store.py`
- Modify: `apps/api/app/schemas.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_feedback.py`

- [ ] **Step 1: Write failing storage/API tests**

覆盖空白正文拒绝、正常提交、管理员令牌缺失时拒绝查询、列表分页和状态更新。

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `pytest apps/api/tests/test_feedback.py -q`
Expected: FAIL because the feedback module and routes do not exist.

- [ ] **Step 3: Implement the storage boundary**

在 `feedback_store.py` 初始化 SQLite 表 `feedback(id, category, message, contact, status, created_at, updated_at)`；提供 `create_feedback`, `list_feedback`, `update_feedback_status`，所有字符串在写入前去除首尾空白并限制长度。

- [ ] **Step 4: Add validated public and protected routes**

在 `schemas.py` 增加反馈提交、状态更新和列表响应模型；在 `main.py` 增加 `POST /v1/feedback`、`POST /admin/feedback/session`、`GET /admin/feedback`、`PATCH /admin/feedback/{id}`。提交接口只接受允许的分类和 10-2000 字正文，管理员会话令牌与 `FEEDBACK_ADMIN_TOKEN` 比较，使用常量时间比较并返回 401/503，而不是泄露配置状态。

- [ ] **Step 5: Run focused tests and verify they pass**

Run: `pytest apps/api/tests/test_feedback.py -q`
Expected: all feedback tests pass.

### Task 2: 用户反馈入口

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Test: `apps/web/tests/feedback.test.tsx`

- [ ] **Step 1: Write failing component tests**

验证导航栏出现“信息反馈”、弹窗可打开、必填校验、提交成功后关闭并显示结果、提交失败保留输入内容。

- [ ] **Step 2: Run focused test and verify it fails**

Run: `npm test -- --run tests/feedback.test.tsx`
Expected: FAIL because no feedback control or API client exists.

- [ ] **Step 3: Implement API client and modal**

在 `api.ts` 增加 `submitFeedback`；在 `page.tsx` 增加反馈弹窗状态、分类选择、正文和联系方式输入，导航栏按钮放在现有导航链接旁边。成功后清空正文并显示“反馈已提交”，失败时保留内容并显示错误。输入框设置最大长度和 `aria` 标签，弹窗支持 ESC 和取消关闭。

- [ ] **Step 4: Style the control and modal**

沿用当前导航栏和面板颜色、间距、圆角与焦点样式，移动端让表单控件占满可用宽度，不改变现有导航布局。

- [ ] **Step 5: Run focused tests and verify they pass**

Run: `npm test -- --run tests/feedback.test.tsx`
Expected: all feedback component tests pass.

### Task 3: 管理员反馈页面

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/page.module.css`
- Test: `apps/web/tests/feedback-admin.test.tsx`

- [ ] **Step 1: Write failing admin page tests**

验证管理员输入令牌后加载列表、按状态筛选、标记已处理、错误令牌显示错误且不渲染消息内容。

- [ ] **Step 2: Run focused test and verify it fails**

Run: `npm test -- --run tests/feedback-admin.test.tsx`
Expected: FAIL because the admin view and API helpers do not exist.

- [ ] **Step 3: Implement protected admin view**

增加管理员视图状态和 API helpers；页面显示登录表单、反馈列表、分类/状态/时间、状态更新按钮和退出按钮。令牌只保存在内存状态，不写入 localStorage；登出后清除列表和令牌。

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `npm test -- --run tests/feedback-admin.test.tsx`
Expected: all admin tests pass.

### Task 4: 全量验证与部署配置

**Files:**
- Modify: `.env.example` or deployment documentation if present
- Modify: `README.md` or `PROJECT_HANDOFF.md` with `FEEDBACK_ADMIN_TOKEN` setup and admin route instructions

- [ ] **Step 1: Run backend test suite**

Run: `pytest -q`
Expected: all API tests pass.

- [ ] **Step 2: Run frontend test, typecheck, and build**

Run: `npm test -- --run`, `npm run typecheck`, `npm run build`
Expected: all tests pass, TypeScript reports no errors, and Vite build exits 0.

- [ ] **Step 3: Verify online safety defaults**

Confirm the server refuses admin login when `FEEDBACK_ADMIN_TOKEN` is unset, public submission enforces length limits, and no client bundle contains the configured token.
