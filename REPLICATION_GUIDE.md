# 医途项目复刻指南：需要自行调整和补充什么

核对日期：2026-10-22。

本指南对应 `384799250-create/hospital-compass` 的 `feature/hospital-compass-mvp` 分支。项目包含 React/Vite 前端、FastAPI 后端、医院信息检索与评分、AI 问题卡片、收藏和反馈管理，以及可选的青霖媒体工作台。

**克隆仓库可以取得项目源码；完整复刻运行效果，还需要自行准备医院数据库、第三方服务账号、环境变量和部署环境。** 原作者的 API 额度、服务器、域名和用户反馈数据不随源码提供。

## 1. 复刻前先确定目标

| 目标 | 可以得到什么 | 还需要准备什么 |
| --- | --- | --- |
| 验证源码、查看页面、运行测试 | 前端界面、构建产物和自动测试 | Python、Node.js；API 的数据路径必须指向可写目录 |
| 本机运行医院目录与匹配 | 使用自己数据的医院目录、筛选与评分 | 与代码兼容的 SQLite 医院库及实际医院记录 |
| 复刻完整 AI 引导流程 | 动态问题、疾病方向和结果整理 | 医院库，以及可用且有额度的 DeepSeek 账号 |
| 补充联网医院资料 | AnySearch 搜索及可选博查回退 | 对应的独立 API Key、网络连通性和额度 |
| 开放反馈后台 | 提交、查看和处理反馈 | 自己的管理员令牌和独立反馈数据库 |
| 使用 `/media` | 图片、视频模型与异步生成任务 | 青霖 API Key、额度，以及公网开放前的访问控制 |
| 正式上线 | 自己域名下的前后端服务 | 云服务器或托管平台、HTTPS、反向代理、持久化数据和备份 |

没有 DeepSeek 配置时，部分接口会回退或返回服务不可用，不能据此认为完整 AI 流程已经复刻。空医院库可以用于服务检查，但不能提供完整医院搜索结果。

## 2. 必须调整的配置

| 配置或资源 | 用户应如何调整 | 不调整的后果 |
| --- | --- | --- |
| 项目目录 | 使用自己克隆后的目录，替换历史交接文档中的绝对路径 | 启动命令找不到项目 |
| `HOSPITAL_COMPASS_DATABASE_PATH` | 指向自己的医院 SQLite 文件 | 默认尝试历史 F 盘位置，或读到空库 |
| `HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH` | 通常指向同一个完整医院库；若单独维护三甲库则填对应文件 | 目录和匹配可能没有医院 |
| `HOSPITAL_COMPASS_DATA_DIR` | 指定可写的数据目录，避免依赖 F 盘默认值 | 在没有 F 盘的机器上可能无法初始化 |
| `FEEDBACK_DATABASE_PATH` | 指向自己可持久化的反馈库；首次使用会自动建表 | 反馈可能写入临时容器目录或随重部署丢失 |
| `DEEPSEEK_API_KEY` | 使用自己申请的密钥 | AI 功能不可用或进入降级流程 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-chat`；确认账号支持该模型 | 上游请求可能失败 |
| `ANYSEARCH_API_KEY` | 如需联网补充，配置自己的 AnySearch 密钥 | 主搜索服务不可用 |
| `BOCHA_API_KEY` | 可选的博查搜索回退密钥 | 主搜索不可用时少一个回退渠道 |
| `FEEDBACK_ADMIN_TOKEN` | 生成自己的随机管理员令牌 | 反馈后台无法登录；不能沿用示例值 |
| `QINGLIN_API_KEY` | 仅使用媒体工作台时配置自己的密钥 | `/media` 上游请求不可用 |
| `FRONTEND_ORIGIN` | 跨域部署时填自己的前端源，如 `https://app.example.com`，多个源以逗号分隔 | 浏览器可能阻止跨域请求；它本身不是接口鉴权 |
| `VITE_API_BASE_URL` | 同域部署和本地代理可留空；前后端分域时填自己的 API 基地址 | 请求会发往错误地址；修改后必须重新构建前端 |
| 域名、云资源和反向代理 | 使用自己的资源，不复制原作者的实例信息 | 不能形成自己的可控部署 |

**配置读取方式：** 除青霖客户端会自行读取 `apps/api/.env` 外，其他后端配置主要从进程环境变量读取。复制 `.env.example` 并填写文件，并不代表所有配置已经生效。下文使用 PowerShell 的 `$env:` 显式设置；Linux 使用服务环境变量或容器 `--env-file`。前端的 `.env.local` 由 Vite 读取，所有 `VITE_*` 值都可能进入浏览器产物，不能放密钥。

## 3. 医院数据需要自己补充

### 3.1 仓库数据与完整运行数据库的区别

- `apps/api/app/data/verified_beijing_hospitals.csv`：当前有 2 条公开样例，供基础匹配接口使用，不是全国医院数据库，也不会自动填充医院目录库。
- `apps/api/app/data/pilot_hospitals.csv`：未核验、未发布的导入测试数据，不应直接用于正式推荐。
- `apps/api/app/data/fudan_2024_specialty_rankings.csv`：专科排名相关资料，不能代替医院主库，也不会自动恢复原作者数据库。
- 完整运行环境使用仓库之外的 SQLite 医院库。本次核对的本机文件约 260 MiB，含 2684 家医院、283700 条排名、21872 条专科能力和 23813 条资质记录；这些数量是原环境的状态，不是克隆后的预置数据。
- 仓库不包含完整医院库、原作者密钥、服务器环境文件、真实反馈及附件。

完整数据库超过 GitHub 普通 Git 单文件 100 MiB 限制。若后续提供数据分发，应单独安排版本化下载、校验和与使用说明；本指南不提供原库下载地址。

### 3.2 数据准备有两条路径

**路径 A：使用自己已经取得且可使用的兼容数据库。** 将它复制到自己的持久化目录，并设置两个医院数据库路径。先检查 SQLite 完整性、表字段、数据来源和核验状态，避免把无关数据库仅改文件名后直接使用。

**路径 B：从空库开始建立自己的数据集。** 本次同步增加了 [数据库表和索引结构](docs/database-schema.sql)，由本机运行库只读导出，不含医院记录、排名内容、反馈或任何密钥。它是结构快照，不会自动采集、导入或核验资料，也不包含旧数据库管理工具的视图与触发器。

以下命令在**仓库根目录**执行，只创建一个尚不存在的数据库：

```powershell
$env:HOSPITAL_COMPASS_DATABASE_PATH = Join-Path $PWD 'runtime-data/hospital_database.db'
@'
import os, sqlite3
from pathlib import Path

target = Path(os.environ['HOSPITAL_COMPASS_DATABASE_PATH'])
if target.exists():
    raise SystemExit('Database already exists; back it up and review it instead of overwriting it.')
target.parent.mkdir(parents=True, exist_ok=True)
schema = Path('docs/database-schema.sql').read_text(encoding='utf-8')
with sqlite3.connect(target) as db:
    db.executescript(schema)
    print(db.execute('PRAGMA integrity_check').fetchone()[0])
'@ | .\.venv\Scripts\python.exe -
```

创建空表后仍需导入自己的医院、科室、排名来源、专科能力、资质和证据。代码没有一条可以从零重建原作者全部数据的命令；现有采集、Excel 导入脚本只能作为适配工具，执行前应检查输入格式、目标库和脚本中的路径。尤其不要混用针对旧轻量 `hospitals.id` 结构的导入器与本结构快照中的 `hospitals.hospital_id` 表。

完整结构中至少关注以下关联：

| 表 | 需要补充的内容 |
| --- | --- |
| `hospitals` | 稳定 ID、医院名称、地区、地址、等级、运营状态、官网和更新时间 |
| `departments` | 科室 ID、标准名称和别名 |
| `department_capabilities` | 医院与科室关联、诊疗范围、专科实力、证据和核验状态 |
| `ranking_sources`、`hospital_rankings` | 排名发布方、年份、范围、医院/科室关联、名次和证据 |
| `hospital_credentials` | 医院及科室资质、级别、发证单位、年份和核验依据 |
| 来源与证据相关表 | 可追溯的资料 URL、获取日期和审核记录 |

当前三甲目录读取完整结构时要求 `tier='三级'`、`grade='甲等'`，并且运营状态属于 `在营`、`运营中`、`正常`、`正常运营`。地区字段需要与页面选择值对应。没有符合条件的医院，目录会为空；缺少地址、排名或专科证据也会影响展示与评分。

不要把待核验资料批量改成“已核验”来凑齐展示。基础匹配 CSV 还有 180 天来源时效校验；应持续核实来源并更新资料，过期发布清单可能导致 API 启动失败。

更多数据要求见 [医院数据库需求](docs/hospital-database-requirements.md) 和 [数据修改标准](docs/hospital-database-modification-standards.md)。其中出现的 F 盘路径属于原环境示例，复刻时应替换。

## 4. 推荐的本机复刻步骤（Windows PowerShell）

### 4.1 安装运行环境与依赖

需要 Python 3.12+，以及满足 `apps/web/package.json` 的 Node.js 版本：`^22.22.2 || ^24.15.0 || >=26.0.0`。

```powershell
git clone --branch feature/hospital-compass-mvp https://github.com/384799250-create/hospital-compass.git
Set-Location hospital-compass
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './apps/api[dev]'
Push-Location apps/web
npm.cmd ci
Pop-Location
```

### 4.2 配置数据与服务

在仓库根目录执行。`runtime-data/hospital_database.db` 必须是已准备的数据库；也可以按上一节先创建空结构用于服务检查。

```powershell
$env:HOSPITAL_COMPASS_DATA_DIR = Join-Path $PWD 'runtime-data'
$env:HOSPITAL_COMPASS_DATABASE_PATH = Join-Path $PWD 'runtime-data/hospital_database.db'
$env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH = $env:HOSPITAL_COMPASS_DATABASE_PATH
$env:FEEDBACK_DATABASE_PATH = Join-Path $PWD 'runtime-data/feedback.sqlite3'
$env:DEEPSEEK_MODEL = 'deepseek-chat'

# 需要哪些功能，就在当前进程环境中配置哪些自己的密钥。
# 不要把填写后的真实值保存进受 Git 跟踪的文件。
# $env:DEEPSEEK_API_KEY = '你的 DeepSeek Key'
# $env:ANYSEARCH_API_KEY = '你的 AnySearch Key'
# $env:BOCHA_API_KEY = '你的博查 Key'
# $env:QINGLIN_API_KEY = '你的青霖 Key'

# 为自己的反馈后台生成令牌，并在密码管理器中保存。
$env:FEEDBACK_ADMIN_TOKEN = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

`$env:` 只影响当前终端及其子进程；服务重启后需要再次设置，正式部署应配置持久化的服务环境。管理员登录使用本次生成的令牌，后端重启时也需使用同一个保存值。

### 4.3 启动前端

第二个终端进入本仓库的 `apps/web`：

```powershell
npm.cmd run dev
```

打开 `http://127.0.0.1:5173/`。开发代理把 `/v1`、`/admin`、`/health` 转发到 `127.0.0.1:8000`。

**旧启动脚本注意事项：** `start-hospital-compass.ps1` 仍硬编码 F 盘数据库，并把后端启动到 `8001`；`apps/web/vite.config.ts` 当前代理到 `8000`。新机器推荐使用上述手动步骤。若要使用旧脚本，必须替换数据库路径、确保所用 Python 已安装依赖，并让后端端口与前端代理保持一致。原环境已有代理或进程不能代替新环境的配置。

## 5. 部署到自己的服务器时要补什么

### 5.1 同域部署

前端使用 `npm.cmd run build` 生成 `apps/web/dist`，由 Web 服务器提供静态文件。将 `/v1/`、`/admin/` 和 `/health` 转发到后端，其他页面路径回退到 `index.html`，以支持 `/feedback-admin`、`/media` 等直接访问。API 路由应优先于 SPA 回退。

Vite 的开发代理不会自动进入构建产物。`apps/web/vercel.json` 只处理 SPA 路由回退，没有替你配置后端转发；不能只上传 `dist` 就期待 API 自动可用。

### 5.2 前后端分域部署

构建前在 `apps/web/.env.local` 设置：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

在后端环境设置 `FRONTEND_ORIGIN=https://app.example.com`。两处都替换为自己的域名，使用 HTTPS；更新 `VITE_API_BASE_URL` 后重新构建并部署。

### 5.3 容器与 Render

仓库中有 Dockerfile 和 `render.yaml`，但医院数据库不会被打包进镜像。需要自行把数据库放进持久卷并配置：

```dotenv
HOSPITAL_COMPASS_DATABASE_PATH=/data/hospital_database.db
HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH=/data/hospital_database.db
FEEDBACK_DATABASE_PATH=/data/feedback.sqlite3
```

数据目录必须允许服务写入：反馈保存和部分官方证据更新都可能写数据库。使用独立环境文件时可通过容器的 `--env-file` 加载，不要把文件提交到仓库。`render.yaml` 还需根据自己的账号、域名和密钥调整；若启用青霖，要自行添加 `QINGLIN_API_KEY`，当前模板没有此项。

### 5.4 对公网开放前的实际缺口

- `/v1/media/tasks` 当前没有内置用户鉴权或用户配额。配置了青霖密钥后，应先在网关限制媒体路由或实现身份、权限和额度控制；不用媒体功能时可在网关禁用 `/v1/media/*`。
- AI 和搜索服务使用部署者的额度；应按自己的受众设置访问限制、预算和调用监控。`BOCHA_MAX_CALLS_PER_HOUR` 可控制现有搜索预算，但不是全部接口的统一限流。
- 反馈后台当前使用管理员令牌，不是完整的 MFA/RBAC 系统；README 中的生产要求需要部署者另外落实。
- 健康接口在医院数据为零时仍返回 HTTP 200，响应正文为 `status=degraded`。监控必须同时检查正文与医院数量，不能只看 HTTP 状态码。
- 域名、证书、数据备份、故障告警、更新和回滚都需要部署者自行配置。若数据库正在写入，使用 SQLite 在线备份或停止写入后备份，避免只复制主文件而遗漏 WAL 数据。

## 6. 复刻完成的验收方式

后端测试需使用独立数据目录，不能指向生产医院库或真实反馈库。在测试终端中清除真实第三方密钥，避免测试读取到个人配置。

```powershell
# 仓库根目录，新建测试终端执行。
$env:HOSPITAL_COMPASS_DATA_DIR = Join-Path $PWD 'runtime-test-data'
$env:FEEDBACK_DATABASE_PATH = Join-Path $PWD 'runtime-test-data/feedback.sqlite3'
Remove-Item Env:HOSPITAL_COMPASS_DATABASE_PATH, Env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:DEEPSEEK_API_KEY, Env:ANYSEARCH_API_KEY, Env:BOCHA_API_KEY, Env:QINGLIN_API_KEY, Env:API_KEY -ErrorAction SilentlyContinue
Push-Location apps/api
& ../../.venv/Scripts/python.exe -m pytest -q
Pop-Location

Push-Location apps/web
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
Pop-Location
```

运行服务后再检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod 'http://127.0.0.1:8000/v1/hospital-directory?page=1&page_size=1'
```

完整数据模式应看到 `status=ok`、`hospital_data.loaded=true`、医院数大于零，并有符合筛选条件的目录结果。空结构模式的预期是 `degraded` 和空目录，它只证明服务与数据库结构能够启动。

最后用自己的账号额度手动验证问题卡片、方向确认、地区筛选、详情、反馈提交与后台处理；如启用媒体，再验证异步任务。自动测试中的模拟上游请求不能证明自己的真实密钥、网络和账户余额可用。

2026-10-22 本次检查基线：后端 399 项测试通过，前端 55 项测试通过，类型检查和构建通过。原线上实例检查为健康接口 2684 家、目录总数 2613 条；两个接口的筛选口径不同，复刻者应以自己的有效数据为准。

## 7. 常见问题与后续维护

| 现象 | 优先检查 |
| --- | --- |
| 页面能打开，接口失败 | 后端是否启动；8000/8001 是否一致；生产是否配置 API 代理 |
| 健康状态 `degraded`、目录为空 | 是否连接了正确的医院库；空表是否尚未导入数据；三甲和运营状态是否匹配 |
| AI 问题一直无法生成 | DeepSeek Key 是否进入后端进程、模型是否可用、网络及额度是否正常 |
| 搜索不补充外部结果 | AnySearch/博查配置、预算、网络，以及候选医院是否能匹配本地三甲身份 |
| 反馈后台 503 或 401 | 管理员令牌是否在后端生效、前后端输入是否一致 |
| 修改前端 API 地址后仍请求旧地址 | 是否重新构建和部署，而不是只重启静态服务器 |
| 地理定位不可用 | HTTPS、浏览器权限；仍可手动选择地区 |
| 重部署后数据消失 | 数据是否放在持久卷；路径是否一致；备份与恢复是否验证 |
| 源码公开就能直接使用全部内容吗 | 公开可见不等于授予开源许可；本次同步未新增 LICENSE，复用授权及第三方数据、素材使用权需另外确认 |

医院官网、地址、预约入口、排名年份、证据时效和核验状态都需要持续维护。若调整评分权重、地区体系或医学提示，应同步更新相应规则、说明与测试；页面继续说明它是信息导航与方向整理工具。

新版公开交接说明见 [PROJECT_HANDOFF_PUBLIC.md](PROJECT_HANDOFF_PUBLIC.md)。它由本机的 `PROJECT_HANDOFF_2026-09-17.md` 整理，原始本机文档保留。公开版中的域名、云资源和本机路径使用占位值；它是架构交接材料，首次复刻请优先按本指南执行。
