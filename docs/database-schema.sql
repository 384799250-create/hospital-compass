-- Hospital Compass database table/index schema snapshot, 2026-10-22.
-- Exported read-only from the local project database; contains no records.
-- Views and triggers from historical database-management tools are omitted.
-- Supply your own hospital, department, ranking, credential, and evidence data.
-- Apply only to a new empty database; this is not a migration script.

CREATE TABLE administrative_regions (
    region_id         TEXT PRIMARY KEY,       -- 标准行政区划代码
    parent_region_id  TEXT,                   -- 父级区划代码
    level             INTEGER NOT NULL,       -- 1=省 2=市 3=区县 4=街道
    name              TEXT NOT NULL,          -- 标准名称
    standard_code     TEXT,                   -- 国标代码
    valid_from        TEXT,                   -- 生效日期
    valid_to          TEXT,                   -- 失效日期（NULL表示当前有效）
    aliases           TEXT,                   -- 别名JSON数组
    sort_order        INTEGER DEFAULT 0,
    created_at        TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at        TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE db_metadata (
    meta_key      TEXT PRIMARY KEY,
    meta_value    TEXT,
    updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE department_capabilities (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id             TEXT NOT NULL,
    department_id           TEXT NOT NULL,
    disease_tags            TEXT,           -- 擅长疾病标签JSON
    technology_tags         TEXT,           -- 技术特色标签JSON
    diagnosis_scope         TEXT,           -- 诊疗范围
    key_doctors             TEXT,           -- 知名专家JSON
    specialty_strength_level TEXT,          -- 专科实力等级
    evidence_id             INTEGER,
    created_at              TEXT DEFAULT (datetime('now', 'localtime')), disease_id TEXT, standard_disease_name TEXT, treatment_capabilities TEXT, technology_name TEXT, capability_level TEXT, evidence_summary TEXT, evidence_url TEXT, verification_status TEXT,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE departments (
    department_id       TEXT PRIMARY KEY,   -- DEP-XXXXXX
    standard_name       TEXT NOT NULL,      -- 标准名称
    parent_department_id TEXT,              -- 父级科室
    specialty_category  TEXT,               -- 专科分类
    aliases             TEXT,               -- 别名JSON
    sort_order          INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE disease_department_mapping (
        mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
        disease_name TEXT NOT NULL,
        disease_aliases TEXT,
        symptom_keywords TEXT,
        department_id TEXT NOT NULL,
        mapping_priority INTEGER DEFAULT 1,
        confidence REAL DEFAULT 0.8,
        evidence_source TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );

CREATE TABLE evidence (
    evidence_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,  -- hospital/department/qualification/ranking/...
    entity_id           TEXT NOT NULL,  -- 对应实体ID
    field_name          TEXT,           -- 对应字段名
    source_id           INTEGER,
    quoted_text         TEXT,           -- 引用原文
    confidence          REAL DEFAULT 0.5, -- 置信度 0-1
    review_status       TEXT DEFAULT '待审核', -- 待审核/已通过/已驳回/存疑
    reviewer            TEXT,
    reviewed_at         TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);

CREATE TABLE hospital_aliases (
    alias_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id     TEXT NOT NULL,
    alias_name      TEXT NOT NULL,
    alias_type      TEXT,               -- 简称/历史名称/品牌名/常见写法
    source_id       INTEGER,
    verified        INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE hospital_change_log (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            change_type TEXT NOT NULL,
            source_id INTEGER,
            changed_by TEXT,
            change_reason TEXT,
            is_verified INTEGER DEFAULT 0,
            verified_by TEXT,
            verified_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

CREATE TABLE hospital_contacts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    contact_type        TEXT NOT NULL,  -- 官网/门诊电话/急诊电话/挂号链接/公众号/小程序/...
    contact_value       TEXT NOT NULL,
    is_official         INTEGER DEFAULT 0,
    valid_from          TEXT,
    valid_to            TEXT,
    source_id           INTEGER,
    last_verified_at    TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE hospital_credentials (
        credential_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id TEXT NOT NULL,
        department_id TEXT,
        credential_name TEXT NOT NULL,
        credential_level TEXT,
        issuing_body TEXT,
        region_scope TEXT,
        description TEXT,
        issue_year INTEGER,
        evidence_url TEXT,
        published_at TEXT,
        retrieved_at TEXT,
        valid_until TEXT,
        verification_status TEXT DEFAULT '待核验',
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    );

CREATE TABLE hospital_departments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    department_id       TEXT NOT NULL,
    service_type        TEXT,               -- 门诊/住院/急诊/...
    is_key_department   INTEGER DEFAULT 0,  -- 是否重点专科
    is_current          INTEGER DEFAULT 1,  -- 当前是否开设
    source_id           INTEGER,
    verified_at         TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')), department_standard_name TEXT, department_aliases TEXT, verification_status TEXT, evidence_updated_at TEXT,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE hospital_qualifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    qualification_type  TEXT NOT NULL,  -- 等级评定/医保定点/教学医院/...
    tier                TEXT,           -- 一级/二级/三级
    grade               TEXT,           -- 甲等/乙等/丙等
    issuing_authority   TEXT,           -- 评定机构
    issued_at           TEXT,           -- 评定日期
    expires_at          TEXT,           -- 有效期至
    status              TEXT,           -- 有效/过期/撤销
    source_id           INTEGER,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE hospital_rankings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    ranking_source_id   INTEGER NOT NULL,
    specialty_id        TEXT,           -- 专科排名时关联科室
    rank                INTEGER,        -- 名次
    rating              REAL,           -- 评分
    award_level         TEXT,           -- 奖项等级
    raw_value           TEXT,           -- 原始值
    evidence_id         INTEGER,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')), rank_year INTEGER, rank_level TEXT, rank_scope TEXT, ranking_name TEXT, publisher TEXT, evidence_url TEXT, published_at TEXT, retrieved_at TEXT, verification_status TEXT, valid_until TEXT,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (ranking_source_id) REFERENCES ranking_sources(ranking_source_id)
);

CREATE TABLE hospital_relationships (
            relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT NOT NULL,
            related_hospital_id TEXT,
            relationship_type TEXT NOT NULL,
            relationship_name TEXT,
            notes TEXT,
            effective_from TEXT,
            effective_to TEXT,
            source_id INTEGER,
            verified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
            FOREIGN KEY (related_hospital_id) REFERENCES hospitals(hospital_id),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

CREATE TABLE hospital_scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    rule_id             INTEGER NOT NULL,
    total_score         REAL,
    dimension_scores    TEXT,           -- 各维度得分JSON
    calculated_at       TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (rule_id) REFERENCES scoring_rules(rule_id)
);

CREATE TABLE hospital_services (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id         TEXT NOT NULL,
    service_type        TEXT NOT NULL,  -- 急诊/专科急诊/预约挂号/互联网医院/异地医保/住院/ICU/手术/...
    is_available        INTEGER DEFAULT 1,
    valid_from          TEXT,
    valid_to            TEXT,
    source_id           INTEGER,
    verified_at         TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE hospital_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT NOT NULL REFERENCES hospitals(hospital_id),
            source_url TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT '????',
            source_title TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL
        );

CREATE TABLE hospital_specialty_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    rule_id INTEGER NOT NULL,
    total_score REAL NOT NULL,
    ranking_score REAL DEFAULT 0,
    capability_score REAL DEFAULT 0,
    service_score REAL DEFAULT 0,
    evidence_score REAL DEFAULT 0,
    dimension_scores TEXT NOT NULL,
    match_reasons TEXT NOT NULL,
    data_status TEXT NOT NULL DEFAULT '待核验',
    calculated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (department_id) REFERENCES departments(department_id),
    FOREIGN KEY (rule_id) REFERENCES scoring_rules(rule_id),
    UNIQUE (hospital_id, department_id, rule_id)
);

CREATE TABLE hospitals (
    hospital_id           TEXT PRIMARY KEY,   -- 全局唯一稳定ID (HOS-XXXXXX)
    canonical_name        TEXT NOT NULL,      -- 官方标准名称
    official_full_name    TEXT,               -- 官方全称
    hospital_type         TEXT,               -- 综合医院/专科医院/中医院/妇幼保健院/...
    nature                TEXT,               -- 公立/民营/其他
    operating_status      TEXT DEFAULT '在营', -- 在营/暂停/撤销/合并/待核验
    parent_hospital_id    TEXT,               -- 分院/院区所属总院ID
    province              TEXT,               -- 省
    city                  TEXT,               -- 市
    district              TEXT,               -- 区县
    address               TEXT,               -- 详细地址
    postal_code           TEXT,               -- 邮政编码
    longitude             REAL,               -- 经度
    latitude              REAL,               -- 纬度
    coordinate_system     TEXT,               -- 坐标系 (GCJ-02/WGS-84/BD-09)
    tier                  TEXT,               -- 一级/二级/三级
    grade                 TEXT,               -- 甲等/乙等/丙等
    medical_insurance     TEXT,               -- 医保类型
    official_domain       TEXT,               -- 官网域名
    official_registration_url TEXT,           -- 官方挂号入口
    created_at            TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at            TEXT DEFAULT (datetime('now', 'localtime')),
    last_verified_at      TEXT,               -- 最近核验时间
    verification_status   TEXT DEFAULT '待核验', introduction TEXT, -- 待核验/已核验/来源冲突/已失效
    FOREIGN KEY (parent_hospital_id) REFERENCES hospitals(hospital_id)
);

CREATE TABLE import_batches (
    batch_id            TEXT PRIMARY KEY,
    batch_name          TEXT,
    source_type         TEXT,
    total_records       INTEGER DEFAULT 0,
    success_count       INTEGER DEFAULT 0,
    skipped_count       INTEGER DEFAULT 0,
    conflict_count      INTEGER DEFAULT 0,
    pending_count       INTEGER DEFAULT 0,
    status              TEXT DEFAULT '进行中', -- 进行中/已完成/已回滚
    started_at          TEXT DEFAULT (datetime('now', 'localtime')),
    finished_at         TEXT,
    operator            TEXT,
    notes               TEXT
);

CREATE TABLE quality_checks (
    check_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    check_type          TEXT NOT NULL,  -- 重复ID/名称重复/地址冲突/区划不一致/等级非法/...
    entity_type         TEXT,
    entity_id           TEXT,
    severity            TEXT,           -- 严重/警告/提示
    description         TEXT,
    batch_id            TEXT,
    resolved            INTEGER DEFAULT 0,
    resolved_at         TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE ranking_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT NOT NULL,
            ranking_source_id INTEGER,
            specialty_id TEXT,
            year INTEGER NOT NULL,
            rank INTEGER,
            rating REAL,
            award_level TEXT,
            raw_value TEXT,
            source_id INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
            FOREIGN KEY (ranking_source_id) REFERENCES ranking_sources(ranking_source_id),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

CREATE TABLE ranking_sources (
    ranking_source_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    publisher           TEXT,
    edition_year        INTEGER,
    scope               TEXT,           -- 全国/区域/专科
    source_url          TEXT,
    published_at        TEXT,
    retrieved_at        TEXT DEFAULT (datetime('now', 'localtime')),
    license_or_usage_note TEXT,
    created_at          TEXT DEFAULT (datetime('now', 'localtime'))
, rank_level TEXT, rank_scope TEXT, valid_until TEXT);

CREATE TABLE raw_sources (
    raw_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type       TEXT NOT NULL,          -- webpage / api / pdf / excel / image
    source_url        TEXT,
    source_title      TEXT,
    publisher         TEXT,
    published_at      TEXT,
    retrieved_at      TEXT DEFAULT (datetime('now', 'localtime')),
    content_hash      TEXT,                   -- 内容哈希，用于去重
    raw_content       TEXT,                   -- 原始文本/JSON
    raw_snapshot_path TEXT,                   -- 原始文件快照路径
    is_official       INTEGER DEFAULT 0,      -- 是否官方来源
    license_note      TEXT,
    batch_id          TEXT,                   -- 导入批次ID
    created_at        TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE review_actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            action_by TEXT,
            action_notes TEXT,
            old_status TEXT,
            new_status TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (task_id) REFERENCES review_tasks(task_id)
        );

CREATE TABLE review_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT,
            current_value TEXT,
            suggested_value TEXT,
            source_id INTEGER,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            assigned_to TEXT,
            completed_by TEXT,
            completed_at TEXT,
            review_notes TEXT,
            batch_id TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

CREATE TABLE scoring_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name           TEXT NOT NULL,
    rule_version        TEXT NOT NULL,
    rule_description    TEXT,
    rule_config         TEXT,           -- JSON配置
    is_active           INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE source_expiry_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            alert_level TEXT DEFAULT 'warning',
            message TEXT,
            last_checked_at TEXT,
            is_resolved INTEGER DEFAULT 0,
            resolved_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

CREATE TABLE sources (
    source_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type         TEXT NOT NULL,  -- 官网/卫健委/医保目录/排行榜/新闻/...
    url                 TEXT,
    title               TEXT,
    publisher           TEXT,
    published_at        TEXT,
    retrieved_at        TEXT DEFAULT (datetime('now', 'localtime')),
    content_hash        TEXT,
    raw_snapshot_path   TEXT,
    is_official         INTEGER DEFAULT 0,
    license_note        TEXT,
    trust_level         INTEGER DEFAULT 0, -- 可信度 0-10
    created_at          TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX idx_aliases_hospital ON hospital_aliases(hospital_id);

CREATE INDEX idx_aliases_name ON hospital_aliases(alias_name);

CREATE INDEX idx_capabilities_department ON department_capabilities (department_id);

CREATE INDEX idx_capabilities_hospital ON department_capabilities (hospital_id);

CREATE INDEX idx_capabilities_hospital_dept ON department_capabilities (hospital_id, department_id);

CREATE INDEX idx_capabilities_level ON department_capabilities (specialty_strength_level);

CREATE INDEX idx_change_log_field ON hospital_change_log(field_name)
    ;

CREATE INDEX idx_change_log_hospital ON hospital_change_log(hospital_id)
    ;

CREATE INDEX idx_contacts_hospital ON hospital_contacts(hospital_id);

CREATE INDEX idx_contacts_type ON hospital_contacts(contact_type);

CREATE INDEX idx_credentials_department ON hospital_credentials (department_id);

CREATE INDEX idx_credentials_hospital ON hospital_credentials (hospital_id);

CREATE INDEX idx_credentials_hospital_dept ON hospital_credentials (hospital_id, department_id);

CREATE INDEX idx_credentials_level ON hospital_credentials (credential_level);

CREATE INDEX idx_depts_name ON departments(standard_name);

CREATE INDEX idx_depts_parent ON departments(parent_department_id);

CREATE INDEX idx_disease_mapping_dept ON disease_department_mapping (department_id);

CREATE INDEX idx_evidence_entity ON evidence(entity_type, entity_id);

CREATE INDEX idx_evidence_entity_field
ON evidence(entity_type, entity_id, field_name, review_status)
;

CREATE INDEX idx_evidence_review ON evidence(review_status);

CREATE INDEX idx_evidence_source ON evidence(source_id);

CREATE INDEX idx_evidence_status ON evidence (review_status);

CREATE INDEX idx_hosp_depts_department ON hospital_departments (department_id);

CREATE INDEX idx_hosp_depts_dept ON hospital_departments(department_id);

CREATE INDEX idx_hosp_depts_hospital ON hospital_departments(hospital_id);

CREATE INDEX idx_hosp_depts_key ON hospital_departments(is_key_department);

CREATE INDEX idx_hosp_scores_hospital ON hospital_scores (hospital_id);

CREATE INDEX idx_hosp_scores_rule ON hospital_scores (rule_id);

CREATE INDEX idx_hosp_scores_total ON hospital_scores (total_score);

CREATE INDEX idx_hospital_sources_hospital
                ON hospital_sources(hospital_id);

CREATE INDEX idx_hospitals_city ON hospitals(city);

CREATE INDEX idx_hospitals_city_district ON hospitals (city, district);

CREATE INDEX idx_hospitals_district ON hospitals(district);

CREATE INDEX idx_hospitals_hospital_type ON hospitals (hospital_type);

CREATE INDEX idx_hospitals_location
                ON hospitals(province, city, district);

CREATE INDEX idx_hospitals_name ON hospitals(canonical_name);

CREATE INDEX idx_hospitals_parent ON hospitals(parent_hospital_id);

CREATE INDEX idx_hospitals_province ON hospitals(province);

CREATE INDEX idx_hospitals_province_city ON hospitals (province, city);

CREATE INDEX idx_hospitals_status ON hospitals(verification_status);

CREATE INDEX idx_hospitals_tier ON hospitals (tier);

CREATE INDEX idx_hospitals_tier_grade ON hospitals(tier, grade);

CREATE INDEX idx_hr_specialty_source
ON hospital_rankings(specialty_id, ranking_source_id, rank)
;

CREATE INDEX idx_hss_department_score
ON hospital_specialty_scores(department_id, total_score DESC)
;

CREATE INDEX idx_qc_batch ON quality_checks(batch_id);

CREATE INDEX idx_qc_resolved ON quality_checks(resolved);

CREATE INDEX idx_qc_type ON quality_checks(check_type);

CREATE INDEX idx_qual_hospital ON hospital_qualifications(hospital_id);

CREATE INDEX idx_qual_type ON hospital_qualifications(qualification_type);

CREATE INDEX idx_ranking_history_hospital ON ranking_history(hospital_id)
    ;

CREATE INDEX idx_ranking_history_year ON ranking_history(year)
    ;

CREATE INDEX idx_rankings_hospital ON hospital_rankings(hospital_id);

CREATE INDEX idx_rankings_hospital_specialty ON hospital_rankings (hospital_id, specialty_id);

CREATE INDEX idx_rankings_level ON hospital_rankings (rank_level);

CREATE INDEX idx_rankings_level_scope ON hospital_rankings (rank_level, rank_scope);

CREATE INDEX idx_rankings_scope ON hospital_rankings (rank_scope);

CREATE INDEX idx_rankings_source ON hospital_rankings(ranking_source_id);

CREATE INDEX idx_rankings_specialty ON hospital_rankings (specialty_id);

CREATE INDEX idx_raw_sources_batch ON raw_sources(batch_id);

CREATE INDEX idx_raw_sources_hash ON raw_sources(content_hash);

CREATE INDEX idx_regions_level ON administrative_regions(level);

CREATE INDEX idx_regions_name ON administrative_regions(name);

CREATE INDEX idx_regions_parent ON administrative_regions(parent_region_id);

CREATE INDEX idx_review_tasks_entity ON review_tasks(entity_type, entity_id)
    ;

CREATE INDEX idx_review_tasks_status ON review_tasks(status)
    ;

CREATE INDEX idx_scores_department ON hospital_specialty_scores (department_id);

CREATE INDEX idx_scores_hospital ON hospital_scores(hospital_id);

CREATE INDEX idx_scores_hospital_dept ON hospital_specialty_scores (hospital_id, department_id);

CREATE INDEX idx_scores_rule ON hospital_scores(rule_id);

CREATE INDEX idx_services_hospital ON hospital_services(hospital_id);

CREATE INDEX idx_services_type ON hospital_services(service_type);

CREATE INDEX idx_sources_hash ON sources(content_hash);

CREATE INDEX idx_sources_publisher ON sources(publisher);

CREATE INDEX idx_sources_url ON sources(url);
