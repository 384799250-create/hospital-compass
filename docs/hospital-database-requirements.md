# 医院基础数据源库完整要求

## 1. 建设目标

医院基础数据源库是医院搜索、筛选、去重、排名和详情展示的事实基础。它必须能够：

- 覆盖全国公开医疗机构，并支持按省、市、区县查询；
- 区分总院、分院、院区和同名机构；
- 记录医院等级、性质、科室、服务能力和权威来源；
- 保留每条重要信息的来源、抓取时间、发布日期和审核状态；
- 为排名提供稳定、可复现的事实数据，但不把事实数据和评分结果混在一起。

本数据库不负责诊断疾病，也不保证医院疗效。医疗相关结论只能作为公开信息整理和就医信息参考。

## 2. 数据分层

数据库分为四层，禁止跨层覆盖原始事实：

1. **原始层**：抓取到的网页、表格、图片、API 响应和原始文本。
2. **标准化层**：清洗后的医院、地址、科室、等级和行政区划实体。
3. **证据层**：每个事实对应的来源、发布时间、抓取时间和审核记录。
4. **应用层**：排名分数、用户匹配分、推荐理由和展示缓存。

应用层数据变化不能修改原始层和标准化层事实。

## 3. 医院主表 hospitals

每家医院必须有稳定且不可复用的唯一 ID。建议字段如下：

| 字段 | 要求 |
| --- | --- |
| hospital_id | 全局唯一、永久稳定，不使用名称直接作为主键 |
| canonical_name | 官方标准名称 |
| official_full_name | 官方全称，允许与展示名不同 |
| hospital_type | 综合医院、专科医院、中医院、妇幼保健院、基层医疗机构等 |
| nature | 公立、民营、其他 |
| operating_status | 在营、暂停、撤销、合并、待核验 |
| parent_hospital_id | 分院或院区所属总院；总院为空 |
| province / city / district | 标准省、市、区县名称 |
| address | 当前有效的详细地址 |
| postal_code | 可选，格式校验 |
| longitude / latitude | 地理坐标及坐标系标识 |
| tier / grade | 一级、二级、三级及甲乙丙等 |
| medical_insurance | 是否纳入医保及医保类型 |
| official_domain | 官方网站域名 |
| official_registration_url | 官方挂号入口 |
| created_at / updated_at | 数据库记录时间 |
| last_verified_at | 最近一次人工或规则核验时间 |
| verification_status | 待核验、已核验、来源冲突、已失效 |

### 3.1 医院名称规范

- 标准名称必须来自医院官网、卫健委、医保目录或其他权威名录；
- 简称、历史名称、品牌名和搜索常见写法写入别名表，不覆盖标准名称；
- 同一医院的总院、分院、院区必须分别建实体，并通过关系字段关联；
- 不得仅凭名称相似就合并医院，合并必须同时核对地址、行政区和官方来源。

## 4. 地址与行政区划

### 4.1 行政区划表 administrative_regions

必须维护省、市、区县、街道的层级关系：region_id、parent_region_id、level、name、standard_code、valid_from、valid_to、aliases。

区划变更不能覆盖历史记录。医院查询时使用当前有效区划，同时保留历史归属。

### 4.2 地址要求

- 地址拆分为省、市、区县、街道和详细地址；
- 必须保存地址来源和更新时间；
- 地址冲突时不得静默覆盖，应标记“来源冲突”并进入复核队列；
- 总院地址和院区地址分别保存；
- 坐标必须同时保存坐标系，禁止混用 GCJ-02、WGS-84 等坐标而不标注。

## 5. 别名与实体关系

医院别名表 hospital_aliases 至少包含 alias_id、hospital_id、alias_name、alias_type、source_id、verified。

医院关系表 hospital_relationships 用于记录总院与分院、医院与院区、合并改名、撤销继承、医联体和附属医院关系。

## 6. 科室和专科能力

### departments

包含 department_id、standard_name、parent_department_id、aliases、specialty_category。

### hospital_departments

包含 hospital_id、department_id、service_type、is_key_department、is_current、source_id、verified_at。

### department_capabilities

包含 hospital_id、department_id、disease_tags、technology_tags、diagnosis_scope、key_doctors、specialty_strength_level、evidence_id。

专科能力必须有公开依据。没有资料时使用“未知”，不能默认填 100 分，也不能把未知直接等同于实力为零。

## 7. 医院等级与资质

医院资质表 hospital_qualifications 至少包含 hospital_id、qualification_type、tier、grade、issuing_authority、issued_at、expires_at、status、source_id。

等级必须记录评定机构和评定时间。三级甲等、三级乙等和三级医院不能只用一段自由文本表示。

## 8. 服务能力与就医信息

医院服务表 hospital_services 应记录是否提供急诊、专科急诊、预约挂号、互联网医院、异地医保、住院、重症监护、手术和特定检查能力，以及服务有效期和来源。

医院联系方式表 hospital_contacts 应记录官方网站、门诊电话、急诊电话、挂号链接、官方公众号或小程序，以及联系方式类型、来源和最近验证时间。

电话、门诊时间和挂号链接必须设置有效期，不能永久缓存。

## 9. 权威排行榜与专科证据

排行榜单独建表，不直接覆盖医院综合实力字段。

排名来源表 ranking_sources 至少包含 ranking_source_id、name、publisher、edition_year、scope、source_url、published_at、retrieved_at、license_or_usage_note。

医院排名表 hospital_rankings 至少包含 hospital_id、ranking_source_id、specialty_id、rank、rating、award_level、raw_value、evidence_id。

必须保留原始文件或网页链接、年份和发布机构。不同年份的排名不能直接混算，除非评分规则明确规定。

## 10. 来源与证据管理

来源表 sources 至少包含 source_id、source_type、url、title、publisher、published_at、retrieved_at、content_hash、raw_snapshot_path、is_official、license_note。

证据表 evidence 至少包含 evidence_id、entity_type、entity_id、field_name、source_id、quoted_text、confidence、review_status、reviewer、reviewed_at。

搜索摘要只能作为候选证据，医院官网、卫健委和正式排行榜优先级更高。

## 11. 数据质量与审核

每条记录必须支持：待导入、已标准化、待核验、已核验、来源冲突、已过期、已失效。

必须自动检查：

- 唯一 ID 重复；
- 标准名称重复；
- 同名医院地址冲突；
- 省、市、区层级不一致；
- 等级值非法；
- 地址为空；
- 来源 URL 不可访问；
- 过期排名仍被应用；
- 总院与分院关系循环；
- 同一来源重复导入。

## 12. 评分边界

数据库事实、权威排名、算法评分和用户匹配分必须分开保存：

医院事实数据 -> 权威证据 -> 固定评分规则 -> 用户条件匹配分 -> 展示理由

评分规则必须版本化并可复现。缺失数据标记为未知，不自动奖励或惩罚；资料完整度不能替代医院实力；地理位置只有在用户选择距离偏好时才提高权重；不得对单一测试医院硬编码加权；每个评分维度都应能追溯到事实和来源。

## 13. 导入流程

1. 保存原始文件或 API 响应；
2. 生成导入批次和校验哈希；
3. 解析字段并生成导入预览；
4. 标准化医院名称和行政区划；
5. 执行实体去重和总院/分院识别；
6. 关联来源和证据；
7. 标记待核验记录；
8. 通过质量检查后写入正式表；
9. 生成导入报告：总行数、成功数、跳过数、冲突数、待核验数；
10. 保留可回滚的批次记录。

任何批量导入都不能直接覆盖正式库，必须先经过预览和校验。

## 14. 当前阶段的最小建库范围

第一阶段只建立并确认三甲医院：

- 医院唯一 ID；
- 标准名称和别名；
- 总院、分院和院区关系；
- 省、市、区县、详细地址；
- 三级甲等资质及评定来源；
- 标准科室和重点专科；
- 至少一个权威来源；
- 数据更新时间和审核状态。

三级乙等、二级医院、专科医院和基层医院先保留数据模型，不立即开放给当前客户端筛选。

## 15. 验收标准

- 全国、省、市、区县查询均能返回正确行政区结果；
- 同一医院不会因别名或分院产生重复排名；
- 总院和分院地址不会互相覆盖；
- 三级甲等筛选结果只来自三甲医院库；
- 测试锚点医院在有有效证据时能够正常召回；
- 任一医院的名称、等级、地址、科室和排名都能查看来源；
- 失效或来源冲突记录不会直接进入正式排名；
- 导入批次可以审计、回滚和重新执行；
- 空库状态下客户端明确提示“数据库尚未导入”，而不是误报“没有医院”。

## 16. 推荐建设顺序

1. 建立行政区划和医院主表；
2. 导入并确认全国三甲医院；
3. 建立医院别名、分院和院区关系；
4. 导入标准科室和重点专科；
5. 接入权威排行榜和证据表；
6. 完善地址、联系方式和服务能力；
7. 执行去重、冲突检测和人工复核；
8. 接入固定评分规则；
9. 最后恢复搜索引擎作为资料补充，而不是唯一数据源。
