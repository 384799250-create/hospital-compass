import json
import sqlite3

from app.specialty_ranking_store import credential_records, credential_records_for_hospitals, import_ranking_records, ranking_records, ranking_records_for_hospitals, initialize_ranking_store


def test_import_persists_and_deduplicates_ranking_records(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    initialize_ranking_store(db)
    rows = [
        {'hospital': '医院 A', 'city': '广州', 'specialty': '心血管内科', 'rank': '1', 'year': '2025', 'source': 'https://example.org/a'},
        {'hospital': '医院 A', 'city': '广州', 'specialty': '心血管内科', 'rank': '1', 'year': '2025', 'source': 'https://example.org/a'},
    ]
    assert import_ranking_records(rows, db) == 1
    records = ranking_records(hospital='医院 A', city='广州', specialty='心血管内科', path=db)
    assert len(records) == 1
    assert records[0]['verification_status'] == '待核验'
    assert records[0]['year'] == 2025


def test_import_accepts_json_payload(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    payload = json.dumps([{'hospital': '医院 B', 'city': '深圳', 'specialty': '肿瘤科', 'tier': '重点专科', 'year': 2024, 'source': 'https://example.org/b'}], ensure_ascii=False)
    assert import_ranking_records(json.loads(payload), db) == 1
    assert ranking_records(hospital='医院 B', path=db)[0]['tier'] == '重点专科'


def test_batch_ranking_records_reads_multiple_legacy_hospitals(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    initialize_ranking_store(db)
    import_ranking_records([
        {'hospital': '医院 A', 'city': '广州', 'specialty': '神经内科', 'rank': 1, 'year': 2025, 'source': 'https://example.org/a'},
        {'hospital': '医院 B', 'city': '深圳', 'specialty': '神经内科', 'rank': 2, 'year': 2025, 'source': 'https://example.org/b'},
    ], db)

    records = ranking_records_for_hospitals(['医院 A', '医院 B'], path=db)

    assert {name: rows[0]['rank'] for name, rows in records.items()} == {'医院 A': 1, '医院 B': 2}


def test_batch_ranking_records_supports_a_national_sized_hospital_set(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    initialize_ranking_store(db)
    import_ranking_records([
        {'hospital': '医院 A', 'city': '广州', 'specialty': '神经内科', 'rank': 1, 'year': 2025, 'source': 'https://example.org/a'},
    ], db)

    records = ranking_records_for_hospitals(['医院 A', *(f'医院 {index}' for index in range(1, 2685))], path=db)

    assert records['医院 A'][0]['rank'] == 1


def test_ranking_records_expose_source_name_and_publisher(tmp_path):
    db = tmp_path / 'authoritative-rankings.sqlite3'
    connection = sqlite3.connect(db)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, city TEXT, verification_status TEXT
        );
        CREATE TABLE departments (department_id TEXT PRIMARY KEY, standard_name TEXT);
        CREATE TABLE ranking_sources (
            ranking_source_id INTEGER PRIMARY KEY, name TEXT, publisher TEXT, edition_year INTEGER,
            scope TEXT, source_url TEXT
        );
        CREATE TABLE hospital_rankings (
            id INTEGER PRIMARY KEY, hospital_id TEXT, ranking_source_id INTEGER, specialty_id TEXT,
            rank INTEGER, rating REAL, award_level TEXT, rank_year INTEGER, rank_level TEXT,
            rank_scope TEXT, ranking_name TEXT, publisher TEXT, evidence_url TEXT, verification_status TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1', '测试医院', '广州市', '已通过')")
    connection.execute("INSERT INTO departments VALUES ('DEP-000004', '儿科')")
    connection.execute(
        "INSERT INTO ranking_sources VALUES (1, '2024年度华南地区中医儿科专科声誉排行榜', '复旦大学医院管理研究所', 2024, '华南地区', 'https://rank.cn-healthcare.com/')"
    )
    connection.execute(
        "INSERT INTO hospital_rankings VALUES (1, 'H1', 1, 'DEP-000004', 15, NULL, 'A++', 2024, '大区级', '专科', '儿科', '', 'https://rank.cn-healthcare.com/', '已通过')"
    )
    connection.commit()
    connection.close()

    record = ranking_records(hospital='测试医院', specialty='儿科', path=db)[0]

    assert record['ranking_source_name'] == '2024年度华南地区中医儿科专科声誉排行榜'
    assert record['ranking_publisher'] == '复旦大学医院管理研究所'
    assert record['ranking_source_scope'] == '华南地区'


def test_ranking_records_compute_max_rank_before_hospital_filter(tmp_path):
    db = tmp_path / 'ranking-max.sqlite3'
    connection = sqlite3.connect(db)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, city TEXT, verification_status TEXT
        );
        CREATE TABLE departments (department_id TEXT PRIMARY KEY, standard_name TEXT);
        CREATE TABLE ranking_sources (
            ranking_source_id INTEGER PRIMARY KEY, name TEXT, publisher TEXT, edition_year INTEGER,
            scope TEXT, source_url TEXT
        );
        CREATE TABLE hospital_rankings (
            id INTEGER PRIMARY KEY, hospital_id TEXT, ranking_source_id INTEGER, specialty_id TEXT,
            rank INTEGER, rating REAL, award_level TEXT, rank_year INTEGER, rank_level TEXT,
            rank_scope TEXT, ranking_name TEXT, publisher TEXT, evidence_url TEXT, verification_status TEXT
        );
    ''')
    connection.executemany(
        "INSERT INTO hospitals VALUES (?, ?, ?, ?)",
        [('H580', '排名580医院', '北海市', '已通过'), ('H2448', '榜单末位医院', '北海市', '已通过')],
    )
    connection.execute(
        "INSERT INTO ranking_sources VALUES (1, '2024年度全国三甲医院综合实力排名', '公开榜单', 2024, '全国', 'https://example.org/ranking')"
    )
    connection.executemany(
        "INSERT INTO hospital_rankings VALUES (?, ?, 1, '', ?, NULL, '', 2024, '综合', '全国综合排名', '', '', 'https://example.org/ranking', '已通过')",
        [(1, 'H580', 580), (2, 'H2448', 2448)],
    )
    connection.commit()
    connection.close()

    record = ranking_records(hospital='排名580医院', path=db)[0]

    assert record['rank'] == 580
    assert record['ranking_max_rank'] == 2448


def test_ranking_records_normalize_legacy_fudan_specialty_url(tmp_path):
    db = tmp_path / 'legacy-fudan.sqlite3'
    connection = sqlite3.connect(db)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, city TEXT, verification_status TEXT
        );
        CREATE TABLE departments (department_id TEXT PRIMARY KEY, standard_name TEXT);
        CREATE TABLE ranking_sources (
            ranking_source_id INTEGER PRIMARY KEY, name TEXT, publisher TEXT, edition_year INTEGER,
            scope TEXT, source_url TEXT
        );
        CREATE TABLE hospital_rankings (
            id INTEGER PRIMARY KEY, hospital_id TEXT, ranking_source_id INTEGER, specialty_id TEXT,
            rank INTEGER, rating REAL, award_level TEXT, rank_year INTEGER, rank_level TEXT,
            rank_scope TEXT, ranking_name TEXT, publisher TEXT, evidence_url TEXT, verification_status TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1', '广州医科大学附属第一医院', '广州市', '已通过')")
    connection.execute("INSERT INTO departments VALUES ('DEP-000102', '呼吸内科')")
    legacy_url = 'https://rank.cn-healthcare.com/fudan/national-specialty/year/2023'
    connection.execute(
        "INSERT INTO ranking_sources VALUES (1, '复旦版2023年度中国医院专科声誉排行榜', '复旦大学医院管理研究所', 2023, '全国', ?)",
        (legacy_url,),
    )
    connection.execute(
        "INSERT INTO hospital_rankings VALUES (1, 'H1', 1, 'DEP-000102', 1, NULL, 'A++++', 2023, '全国级', '全国专科声誉排名', '呼吸内科', '', ?, '已通过')",
        (legacy_url,),
    )
    general_url = 'https://rank.cn-healthcare.com/fudan/national-general/year/2023'
    connection.execute(
        "INSERT INTO ranking_sources VALUES (2, '复旦版2023年度中国医院综合排行榜', '复旦大学医院管理研究所', 2023, '全国', ?)",
        (general_url,),
    )
    connection.execute(
        "INSERT INTO hospital_rankings VALUES (2, 'H1', 2, NULL, 37, NULL, 'A+++', 2023, '全国级', '全国综合排名', '', '', ?, '已通过')",
        (general_url,),
    )
    connection.commit()
    connection.close()

    record = ranking_records(hospital='广州医科大学附属第一医院', specialty='呼吸内科', path=db)[0]

    assert record['source'] == 'https://rank.cn-healthcare.com/fudan/specialty-reputation'
    all_records = ranking_records(hospital='广州医科大学附属第一医院', path=db)
    general = next(item for item in all_records if not item['specialty'])
    assert general['source'] == 'https://rank.cn-healthcare.com/fudan/national-general'


def test_credential_records_reads_real_schema_and_filters_unverified(tmp_path):
    db = tmp_path / 'credentials.sqlite3'
    connection = sqlite3.connect(db)
    connection.executescript('''
        CREATE TABLE hospitals (hospital_id TEXT PRIMARY KEY, canonical_name TEXT);
        CREATE TABLE departments (department_id INTEGER PRIMARY KEY, standard_name TEXT);
        CREATE TABLE hospital_credentials (
            credential_id INTEGER PRIMARY KEY, hospital_id TEXT, department_id INTEGER,
            credential_name TEXT, credential_level TEXT, issuing_body TEXT,
            issue_year INTEGER, evidence_url TEXT, retrieved_at TEXT, verification_status TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1', 'Test Hospital')")
    connection.execute("INSERT INTO departments VALUES (7, 'Cardiology')")
    connection.executemany("INSERT INTO hospital_credentials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (1, 'H1', 7, 'National key specialty', 'National', 'Health authority', 2025, 'https://example.org/1', '2026-01-01', 'verified'),
        (2, 'H1', 7, 'Unverified specialty', 'Province', 'Health authority', 2025, 'https://example.org/2', '2026-01-01', '待核验'),
    ])
    connection.commit()
    connection.close()

    records = credential_records(hospital_id='H1', specialty='Cardiology', path=db)
    assert [record['credential_name'] for record in records] == ['National key specialty']
    assert records[0]['data_updated_at'] == '2026-01-01'
