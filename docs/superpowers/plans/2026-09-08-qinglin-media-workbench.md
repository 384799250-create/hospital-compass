# 青霖媒体工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为医院指南项目增加安全的青霖生图、生视频服务端代理和 `/media` 前端工作台。

**Architecture:** FastAPI 的 `qinglin_client.py` 封装青霖发现、余额、提交和状态轮询；`main.py` 只负责校验、HTTP 路由和错误映射。Vite/React 新增独立 `media-studio.tsx` 页面和 `media-studio.module.css`，通过 `lib/api.ts` 调用后端，密钥不进入浏览器。

**Tech Stack:** Python 3.12、FastAPI、pytest、React 19、TypeScript、Vite。

**Spec:** `docs/superpowers/specs/2026-09-08-qinglin-media-workbench-design.md`

## Global Constraints

- 青霖 Base URL 固定为 `https://api.lk888.ai/api`。
- 只接受顶层提交响应 `code === 200`，任务 ID 来自 `data.task_id`。
- 状态接口只读取顶层 `is_final`、`state`、`result_url`、`error`。
- API Key 只在服务端运行时解析，不打印、不提交、不写入前端。
- 不改变既有医院匹配与用户改动。

---

### Task 1: Add the Qinglin client

**Files:**
- Create: `apps/api/app/qinglin_client.py`
- Create: `apps/api/tests/test_qinglin_client.py`

**Interfaces:**
- `QinglinClient.list_models(media_type: Literal['image','video']) -> list[dict]`
- `QinglinClient.model_detail(model_name: str) -> dict`
- `QinglinClient.balance() -> dict`
- `QinglinClient.create_task(model: str, prompt: str, params: dict) -> str`
- `QinglinClient.task_status(task_id: str) -> dict`

- [ ] **Step 1: Write failing tests** for key resolution, `code === 200`, and top-level task-status parsing using a fake transport.
- [ ] **Step 2: Run** `python -m pytest apps/api/tests/test_qinglin_client.py -q` and confirm failures.
- [ ] **Step 3: Implement** runtime key resolution, JSON requests, timeout handling, and non-secret error messages.
- [ ] **Step 4: Run** the focused tests and confirm they pass.

### Task 2: Add FastAPI media routes

**Files:**
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_qinglin_media_routes.py`
- Modify: `apps/api/.env.example`

**Interfaces:**
- `GET /v1/media/models?type=image|video`
- `GET /v1/media/models/{model_name}`
- `GET /v1/media/balance`
- `POST /v1/media/tasks` with `{model,prompt,params}`
- `GET /v1/media/tasks/{task_id}`

- [ ] **Step 1: Write failing route tests** for missing key (503), model discovery, balance, task creation, and task status.
- [ ] **Step 2: Run** `python -m pytest apps/api/tests/test_qinglin_media_routes.py -q` and confirm failures.
- [ ] **Step 3: Add** Pydantic request validation, a shared client factory, balance gate before generation, and safe upstream error mapping.
- [ ] **Step 4: Add** `QINGLIN_API_KEY=` to `.env.example`, run focused route tests, and confirm they pass.

### Task 3: Add frontend API types and media studio

**Files:**
- Modify: `apps/web/lib/api.ts`
- Create: `apps/web/app/media-studio.tsx`
- Create: `apps/web/app/media-studio.module.css`
- Modify: `apps/web/app/page.tsx`
- Create: `apps/web/tests/media-studio.test.tsx`

**Interfaces:**
- `getMediaModels(type)`
- `getMediaModelDetail(model)`
- `getMediaBalance()`
- `createMediaTask(input)`
- `getMediaTaskStatus(taskId)`

- [ ] **Step 1: Write failing component tests** for type switching, submit state, and final result rendering.
- [ ] **Step 2: Run** `npm test -- --run apps/web/tests/media-studio.test.tsx` and confirm failures.
- [ ] **Step 3: Implement** the page with model/parameter loading, balance display, 5-second polling cleanup, image/video result preview, and accessible error states.
- [ ] **Step 4: Route** `/media` from `Page` without changing the existing landing flow.
- [ ] **Step 5: Run** the focused test, `npm run typecheck`, and `npm run build`.

### Task 4: Verify integration

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document** `QINGLIN_API_KEY` setup and local `/media` URL without including any secret.
- [ ] **Step 2: Run** API tests, web tests, typecheck, and build.
- [ ] **Step 3: Inspect** git diff to ensure only media feature files and documentation changed; leave existing user modifications untouched.
