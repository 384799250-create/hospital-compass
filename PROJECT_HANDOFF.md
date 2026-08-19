# 医途医院推荐项目交接文档

更新时间：2026-08-13

本文件用于在本机新建对话后恢复项目上下文。新对话应先阅读本文件，再检查工作区和数据库，不要假设数据库仍是旧版本。

## 项目位置

- 工作区：`C:\Users\Administrator\Documents\Codex\2026-08-05\new-chat-2\outputs\hospital-compass\.worktrees\mvp`
- 前端：`apps/web`
- 后端：`apps/api`
- 启动脚本：`start-hospital-compass.ps1`
- 当前数据库：`F:\hospital-database\db\hospital_database.db`
- 前端：http://127.0.0.1:5173/
- 后端：http://127.0.0.1:8000/
- 健康检查：http://127.0.0.1:8000/health

## 项目功能

这是一个三甲医院智能检索与分级推荐系统：用户输入症状/疾病、省市区县并选择排名范围；智能体先整理疾病方向和建议科室；用户确认后，系统从三甲医院数据库、专科排名、专科能力、资质、医院服务和地理信息中生成前 10 家推荐，并展示核心优势、匹配理由、评分详情、医院详情和来源。

## 已完成逻辑

- 客户端只读取三甲：`tier = '三级'`、`grade = '甲等'`。
- 运营状态兼容：`在营`、`运营中`、`正常`、`正常运营`；代码在 `apps/api/app/tertiary_store.py`。
- 使用 `HOSPITAL_COMPASS_DATABASE_PATH` 和 `HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH` 指向 F 盘数据库。
- 专科排名：精确专科优先，其次大类，再其次相关专科。
- 专科排名范围权重：全国 1.00、省级 0.90、市级 0.80、区/县级 0.70。
- 综合榜单用于综合实力；中医、妇幼等专门榜单不能直接当综合医院榜单。
- 地理评分：同最小地域 100、同上一级 80、同上两级 60；跨省按距离衰减。
- 综合评分权重：专科实力 35%、医院综合实力 25%、地理位置 20%、资料完整度 10%、官方服务信息 10%。
- 官方服务：明确挂号/预约链接 100 分，只有官网 70 分，无链接 0 分。
- 核心优势和匹配理由必须使用数据库证据生成，不应展示模型思考过程。
- 无对应专科证据时显示医院综合实力证据或简介，并提示专科证据不足。
- 专科实力 0 分显示“暂无排名”；医院信息/官方服务 0 分显示“暂无信息”。
- 医院详情在医院卡片下展开；排名范围切换保留旧结果并缓存；“市区级”已改成“区/县级”，内部值仍为 `district`。

## 最近数据库状态

数据库：`F:\hospital-database\db\hospital_database.db`

- 最近检查更新时间：2026-08-12 18:03（用户再次更新后必须重新检查）
- 完整性：`PRAGMA integrity_check` 返回 `ok`
- 医院：2684 家
- 官网：2684 家有 `official_domain`
- 官方挂号链接：0 条 `official_registration_url`
- 医院排名：283700 条
- 专科能力：21872 条
- 医院资质：23813 条
- 联系方式：21170 条
- 仍有约 352 条地址偏短，详细地址覆盖不完整。

番禺区三甲医院 5 家：广东省妇幼保健院、广东祈福医院、广州市番禺区中医院、广州市番禺区中心医院、广州市番禺区何贤纪念医院。

## 已知问题

1. `official_registration_url` 为空，官方服务维度通常只能按官网 70 分。
2. 部分地址只到省、市或区县级。
3. 大量排名、资质、专科能力记录仍需核验，不能把待核验数据当最高权威证据。
4. `hospital_sources` 表为空，来源主要保存在排名/资质/能力记录的 URL 字段。
5. `db_metadata` 统计值可能落后于实际表行数，审核时以实际查询为准。
6. PowerShell 可能禁止执行 `.ps1`，启动时使用 `-ExecutionPolicy Bypass`，不要修改系统策略。

## 启动

后端：

```powershell
Set-Location 'C:\Users\Administrator\Documents\Codex\2026-08-05\new-chat-2\outputs\hospital-compass\.worktrees\mvp\apps\api'
$env:HOSPITAL_COMPASS_DATABASE_PATH='F:\hospital-database\db\hospital_database.db'
$env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH='F:\hospital-database\db\hospital_database.db'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
Set-Location 'C:\Users\Administrator\Documents\Codex\2026-08-05\new-chat-2\outputs\hospital-compass\.worktrees\mvp\apps\web'
npm.cmd run dev
```

反馈后台：

启动后端前设置管理员令牌（不要提交到代码仓库）：

```powershell
$env:FEEDBACK_ADMIN_TOKEN='请替换为长度足够的随机令牌'
$env:FEEDBACK_DATABASE_PATH='F:\hospital-compass-data\feedback.sqlite3'
```

用户在结果页顶部点击“信息反馈”提交内容；管理员访问 `http://127.0.0.1:5173/feedback-admin`，输入同一个令牌查看和标记反馈。`FEEDBACK_MAX_PER_MINUTE` 可调整单个来源每分钟提交上限，默认 5。

检查：`Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing`

## 验证

```powershell
Set-Location 'C:\Users\Administrator\Documents\Codex\2026-08-05\new-chat-2\outputs\hospital-compass\.worktrees\mvp\apps\api'
python -m pytest -q
```

```powershell
Set-Location 'C:\Users\Administrator\Documents\Codex\2026-08-05\new-chat-2\outputs\hospital-compass\.worktrees\mvp\apps\web'
npm.cmd run typecheck
```

最近验证：后端 266 passed，三甲存储测试 3 passed，前端类型检查通过。

## 新对话接续流程

1. 阅读本文件和 `README.md`。
2. 检查 `git status`，保留用户已有修改。
3. 检查数据库更新时间、大小和完整性。
4. 确认 API 使用 F 盘数据库。
5. 任何数据库写入前先备份。
6. 分别验证前端显示、API 筛选、评分逻辑和数据库实际数据。
7. 完成前检查端口、健康接口并运行相关测试。

## 建议下一步

- 补充和核验医院详细地址。
- 从医院官网提取明确预约/挂号页面，填充 `official_registration_url`。
- 统一排名、资质、专科能力的核验状态和来源约束。
- 更新 `db_metadata`，使统计值与实际表行数一致。
- 做行政区覆盖审计，避免区县字段缺失导致区域搜索漏检。
