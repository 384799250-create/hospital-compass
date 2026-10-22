# 医途医院指南项目对接文档（公开版）

原交接日期：2026-09-17；公开整理及复核日期：2026-10-22。

本文件由本机交接材料整理。域名、IP、实例 ID 和个人项目目录已替换为示例；HTTP 状态和数量记录属于原实例，不代表占位地址可访问。2026-10-22 重新检查的原实例健康状态为 `ok`、医院数 2684，目录接口总数 2613。首次复刻请先阅读 [REPLICATION_GUIDE.md](REPLICATION_GUIDE.md)，它补充了端口、路径和配置读取的实际要求。

## 文档用途

这份文档用于把已经上线的医途医院指南项目交接给后续优化对话。新对话开始前，应先阅读本文件、项目根目录的 `README.md`、`PRODUCT.md` 和 `PROJECT_HANDOFF.md`，再检查当前工作区、数据库和线上部署状态。

本文档只记录当前源码和线上探测中已经核实的内容。密码、令牌、API Key 和 SSH 私钥不写入仓库；部署平台登录仍通过用户自己的腾讯云账号完成。

## 线上入口和运维后台

以下地址已于 2026-10-11 进行 HTTP 探测并确认可用：

| 用途 | 正式地址 | 当前状态 |
| --- | --- | --- |
| 网站首页 | `https://app.example.com/` | HTTP 200 |
| 用户反馈管理后台 | `https://app.example.com/feedback-admin` | HTTP 200，需要管理员令牌登录 |
| 健康检查 | `https://app.example.com/health` | HTTP 200，医院数据已加载 |
| 同域 API 健康检查 | `https://app.example.com/api/health` | HTTP 200，反向代理可用 |
| 医院目录 API 示例 | `https://app.example.com/v1/hospital-directory?page=1&page_size=1` | HTTP 200 |

线上健康接口当时返回：`status=ok`、`hospital_count=2684`、数据库路径 `/data/hospital_database.db`。目录接口当时返回 `total=2613`；这两个数量口径不同，后续优化或数据更新时不要把它们误认为同一统计指标。

腾讯云资源信息：

- 云服务商：腾讯云轻量应用服务器（Lighthouse）
- 实例 ID：`lhins-your-instance`
- 地域：广州 `ap-guangzhou`
- 系统：Ubuntu 24.04
- 服务器公网 IP：`203.0.113.10`
- 当前 API 直连健康检查：`http://203.0.113.10:8000/health`，已验证 HTTP 200
- 腾讯云管理后台：登录腾讯云控制台后进入轻量应用服务器，在广州地域查找上述实例 ID；不要把登录密码或 API 密钥写入本文档

线上反馈后台不是服务器控制台。它的访问地址是 `https://app.example.com/feedback-admin`，输入服务器环境变量 `FEEDBACK_ADMIN_TOKEN` 的值后可查看、筛选和标记用户反馈。

## 项目定位

医途是一个医院信息导航和就医方向整理工具。用户用通俗语言描述症状或疾病后，系统可通过问题卡片补充信息，整理疾病方向和建议科室，再结合地区、范围和就医偏好展示医院公开信息。

项目不提供疾病诊断、治疗方案、疗效承诺或绝对的“最佳医院”结论。页面和接口应继续保留健康信息整理免责声明；紧急情况应优先急诊或联系 120。

## 项目位置

```text
C:\Projects\hospital-compass
```

主要目录：

- `apps/web`：React + Vite 前端
- `apps/api`：FastAPI 后端
- `apps/api/app/data`：随代码管理的公开医院数据文件
- `docs`：需求、设计和实施计划
- `backups`：历史前端或数据备份
- `render.yaml`：Render 后端部署配置

代码仓库：`https://github.com/384799250-create/hospital-compass.git`

主要开发分支：`feature/hospital-compass-mvp`

## 已上线架构

### 前端

- 技术栈：React 19、TypeScript、Vite
- 本地开发地址：`http://127.0.0.1:5173`
- 前端通过同源路径访问 `/v1/*`、`/admin/*` 和 `/health`
- 生产前端部署配置：`apps/web/vercel.json`
- 正式生产域名：`https://app.example.com/`
- 用户反馈后台：`https://app.example.com/feedback-admin`

### 后端

- 技术栈：Python 3.12、FastAPI、Uvicorn
- 本地开发地址：`http://127.0.0.1:8000`
- 启动脚本目前使用 `127.0.0.1:8001` 启动后端，前端开发服务器仍为 `5173`
- 健康检查：`GET /health`
- Render 服务配置：`hospital-compass-api`
- 容器端口：使用环境变量 `PORT`，默认 `8000`
- 后端健康检查路径：`/health`

### 数据库

- 默认生产数据库路径：`/data/hospital_database.db`
- 本机历史数据库路径：`F:\hospital-database\db\hospital_database.db`
- 反馈数据库生产路径：`/data/feedback.sqlite3`
- 本地启动时通过 `HOSPITAL_COMPASS_DATABASE_PATH` 和 `HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH` 指向数据库
- 任何数据库写入前必须先备份，并在写入后运行完整性检查

## 核心用户流程

1. 用户输入症状或疾病描述。
2. 系统在需要时生成一张问题卡片，支持单选、多选、不确定、自定义回答和返回上一步。
3. 系统整理疾病方向、推荐科室和风险提示。
4. 用户选择就医偏好：综合信息、专科方向或就近便利。
5. 用户填写省、市、区县，或使用当前位置后手动修正。
6. 系统按范围展示医院、评分、匹配理由、核心优势、医院详情和公开资料来源。
7. 用户可在结果页提交信息反馈，管理员在反馈后台查看并标记处理。

## 当前主要接口

### 基础与匹配

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 检查服务和医院数据库是否加载 |
| `POST` | `/v1/matches` | 基于本地资料进行医院匹配 |
| `POST` | `/v1/ai-matches` | 在用户同意后使用 AI 辅助匹配 |
| `POST` | `/v1/triage` | 整理疾病方向、科室和风险提示 |
| `POST` | `/v1/symptom-clarification` | 逐步补充症状信息 |
| `POST` | `/v1/realtime-hospital-search` | 本地资料结合联网信息检索医院 |
| `GET` | `/v1/hospitals/{hospital_id}` | 查看本地医院详情 |
| `GET` | `/v1/realtime-hospitals/{hospital_id}` | 查看联网搜索结果详情 |
| `GET` | `/v1/hospital-directory` | 分页读取医院目录 |

### 用户反馈

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/v1/feedback` | 用户提交问题、改进建议或其他反馈，可附图片 |
| `POST` | `/admin/feedback/session` | 使用管理员令牌建立反馈后台会话 |
| `GET` | `/admin/feedback` | 查看反馈，可按 `new` 或 `processed` 筛选 |
| `PATCH` | `/admin/feedback/{feedback_id}` | 将反馈标记为已处理或未处理 |

反馈后台前端页面：

```text
https://你的前端域名/feedback-admin
```

本地页面：`http://127.0.0.1:5173/feedback-admin`

管理员令牌通过请求头 `X-Feedback-Admin-Token` 发送。令牌只放在服务器环境变量 `FEEDBACK_ADMIN_TOKEN` 中，不要写入前端源码、截图或提交记录。

### 媒体工作台

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/v1/media/models?type=image` | 查询图片模型 |
| `GET` | `/v1/media/models?type=video` | 查询视频模型 |
| `GET` | `/v1/media/models/{model_name}` | 查询模型参数 |
| `GET` | `/v1/media/balance` | 查询青霖余额 |
| `POST` | `/v1/media/tasks` | 创建异步媒体任务 |
| `GET` | `/v1/media/tasks/{task_id}` | 查询媒体任务状态 |

媒体工作台前端页面：`/media`

## 关键环境变量

后端生产环境至少需要根据功能配置：

```text
FRONTEND_ORIGIN=https://你的前端域名
DEEPSEEK_API_KEY=服务器环境变量
DEEPSEEK_MODEL=deepseek-chat
ANYSEARCH_API_KEY=服务器环境变量
BOCHA_API_KEY=服务器环境变量
FEEDBACK_ADMIN_TOKEN=服务器环境变量
QINGLIN_API_KEY=服务器环境变量
HOSPITAL_COMPASS_DATABASE_PATH=/data/hospital_database.db
HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH=/data/hospital_database.db
FEEDBACK_DATABASE_PATH=/data/feedback.sqlite3
```

密钥不能提交到 Git、不能打包进前端、不能出现在日志或聊天截图中。前端只使用 `VITE_API_BASE_URL`，本地开发可留空，由 Vite 代理请求。

## 本地启动

历史启动脚本如下；它依赖原机器 F 盘路径且后端端口与当前 Vite 代理不一致。新环境请优先使用复刻指南的手动启动步骤；若使用脚本，需要先修改路径和端口：

```powershell
Set-Location 'C:\Projects\hospital-compass'
powershell -ExecutionPolicy Bypass -File .\start-hospital-compass.ps1
```

手动启动后端：

```powershell
Set-Location 'C:\Projects\hospital-compass\apps\api'
$env:HOSPITAL_COMPASS_DATABASE_PATH='F:\hospital-database\db\hospital_database.db'
$env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH='F:\hospital-database\db\hospital_database.db'
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

手动启动前端：

```powershell
Set-Location 'C:\Projects\hospital-compass\apps\web'
npm.cmd ci
npm.cmd run dev
```

## 部署与发布检查

1. 确认生产前端域名已写入 `FRONTEND_ORIGIN`。
2. 确认后端数据库挂载到持久化磁盘，不要使用临时容器文件系统。
3. 确认 `FEEDBACK_ADMIN_TOKEN` 已配置且不是示例值。
4. 访问 `/health`，确认返回 `status: ok` 且医院数量大于 0。
5. 验证症状整理、问题卡片、医院搜索、医院详情和反馈提交。
6. 进入 `/feedback-admin`，确认管理员令牌可登录并能标记反馈。
7. 前端运行 `npm.cmd run build`、`npm.cmd run typecheck` 和 `npm.cmd test -- --run`。
8. 后端运行 `python -m pytest -q`。
9. 发布前保留数据库备份和上一个可回滚版本。

## 当前已知限制

- `official_registration_url` 目前基本为空，官方服务评分通常只能依赖医院官网信息。
- 部分医院地址详细程度不足。
- 排名、资质和专科能力数据需要持续核验，不能把待核验资料当作最高权威证据。
- `hospital_sources` 表为空，来源主要来自排名、资质和专科能力记录中的 URL 字段。
- 当前代码中没有自动记录服务器部署时间或镜像版本号。更新前应通过服务器上的 Docker 容器和镜像标签确认当前运行版本。
- 任何医疗相关文案和推荐逻辑调整，都必须避免变成诊断或治疗承诺。

## 新优化对话的启动提示

把以下内容作为新聊天的第一条消息，或直接说明“先阅读项目交接文档再开始”：

```text
请先阅读：
C:\Projects\hospital-compass\PROJECT_HANDOFF_PUBLIC.md

这是已经上线的医途医院指南项目。

线上网站：https://app.example.com/
用户反馈后台：https://app.example.com/feedback-admin
线上健康检查：https://app.example.com/health
腾讯云轻量服务器：实例 lhins-your-instance，地域 ap-guangzhou，公网 IP 203.0.113.10。

后续优化必须：
1. 先检查 git status、当前分支、数据库路径和 /health；
2. 保留用户已有修改，不要重置或覆盖无关改动；
3. 医疗信息只做方向整理和公开资料导航，不做诊断或治疗承诺；
4. 涉及数据库写入先备份，涉及前端改动先说明影响范围；
5. 完成后运行相关测试，并说明线上发布还需要执行什么。
```

## 建议的下一轮优化顺序

1. 补齐医院官网中的明确挂号或预约入口，并统一来源核验规则。
2. 补齐医院详细地址和行政区字段，减少区域筛选漏检。
3. 增加反馈后台的分页、导出和备注能力，但继续保持管理员接口鉴权。
4. 对实时搜索、AI 调用和医院评分增加耗时、失败率和来源质量监控。
5. 以真实移动端访问为基准继续优化输入流程、结果页信息密度和可读性。
