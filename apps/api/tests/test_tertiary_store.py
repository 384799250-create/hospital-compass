import sqlite3

from app.hospital_store import initialize, upsert_hospital
from app.tertiary_store import build_tertiary_database, tertiary_database_path, tertiary_rows


def test_build_tertiary_database_copies_only_tertiary_a_rows(tmp_path):
    source = tmp_path / 'source.sqlite3'
    target = tmp_path / 'tertiary-a.sqlite3'
    initialize(source)
    upsert_hospital({'id': 'a', 'name': '三甲医院', 'tier': '三级甲等', 'province': '广东省', 'city': '广州市'}, path=source)
    upsert_hospital({'id': 'b', 'name': '二甲医院', 'tier': '二级甲等', 'province': '广东省', 'city': '广州市'}, path=source)

    report = build_tertiary_database(source, target)

    assert report.copied_rows == 1
    assert [row['canonical_name'] for row in tertiary_rows(path=target)] == ['三甲医院']


def test_tertiary_database_path_is_on_f_drive_by_default(monkeypatch):
    monkeypatch.delenv('HOSPITAL_COMPASS_DATA_DIR', raising=False)
    assert tertiary_database_path() == __import__('pathlib').Path(r'F:\hospital-compass-data\tertiary-a.sqlite3')


def test_tertiary_rows_exposes_hospital_bound_capability_evidence(tmp_path):
    database = tmp_path / 'hospital.db'
    connection = sqlite3.connect(database)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, province TEXT, city TEXT,
            district TEXT, address TEXT, tier TEXT, grade TEXT, operating_status TEXT,
            updated_at TEXT
        );
        CREATE TABLE departments (department_id TEXT PRIMARY KEY, standard_name TEXT);
        CREATE TABLE department_capabilities (
            hospital_id TEXT, department_id TEXT, diagnosis_scope TEXT,
            specialty_strength_level TEXT, evidence_summary TEXT,
            evidence_url TEXT, verification_status TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1','医院甲','广东省','广州市','越秀区','广东省广州市越秀区甲路1号','三级','甲等','在营','2026-08-09')")
    connection.execute("INSERT INTO departments VALUES ('D1','心血管内科')")
    connection.execute(
        "INSERT INTO department_capabilities VALUES "
        "('H1','D1','冠心病介入诊疗','国家级重点','官网原文',"
        "'https://hospital.example/cardio','官网自动核验')"
    )
    connection.execute(
        "INSERT INTO department_capabilities VALUES "
        "('H1','D1','过期依据','市级重点','过期原文',"
        "'https://hospital.example/stale','待复核')"
    )
    connection.commit()
    connection.close()

    row = tertiary_rows(path=database)[0]
    assert row['specialty_capabilities'] == [{
        'department': '心血管内科',
        'diagnosis_scope': '冠心病介入诊疗',
        'strength_level': '国家级重点',
        'evidence_summary': '官网原文',
        'evidence_url': 'https://hospital.example/cardio',
        'verification_status': '官网自动核验',
    }]


def test_tertiary_rows_filters_unsafe_registration_urls(tmp_path):
    database = tmp_path / 'hospital.db'
    connection = sqlite3.connect(database)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, province TEXT, city TEXT,
            district TEXT, address TEXT, tier TEXT, grade TEXT, operating_status TEXT,
            official_domain TEXT, official_registration_url TEXT, updated_at TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1','医院甲','广东省','广州市','越秀区','地址','三级','甲等','在营','https://hospital.example','javascript:alert(1)','2026-08-09')")
    connection.commit()
    connection.close()

    row = tertiary_rows(path=database)[0]
    assert row['official_domain'] == 'https://hospital.example'
    assert row['registration_url'] is None


def test_tertiary_rows_exposes_database_introduction(tmp_path):
    database = tmp_path / 'hospital.db'
    connection = sqlite3.connect(database)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, province TEXT, city TEXT,
            district TEXT, address TEXT, tier TEXT, grade TEXT, operating_status TEXT,
            introduction TEXT, updated_at TEXT
        );
    ''')
    connection.execute(
        "INSERT INTO hospitals VALUES ('H1','Hospital One','Guangdong','Guangzhou','Yuexiu',"
        "'Address','三级','甲等','在营','Database hospital introduction','2026-08-13')"
    )
    connection.commit()
    connection.close()

    row = tertiary_rows(path=database)[0]

    assert row['introduction'] == 'Database hospital introduction'


def test_tertiary_rows_ignores_hospital_contacts(tmp_path):
    database = tmp_path / 'hospital.db'
    connection = sqlite3.connect(database)
    connection.executescript('''
        CREATE TABLE hospitals (
            hospital_id TEXT PRIMARY KEY, canonical_name TEXT, province TEXT, city TEXT,
            district TEXT, address TEXT, tier TEXT, grade TEXT, operating_status TEXT,
            official_domain TEXT, official_registration_url TEXT, updated_at TEXT
        );
        CREATE TABLE hospital_contacts (
            id INTEGER PRIMARY KEY, hospital_id TEXT, contact_type TEXT,
            contact_value TEXT, is_official INTEGER, valid_to TEXT,
            last_verified_at TEXT
        );
    ''')
    connection.execute("INSERT INTO hospitals VALUES ('H1','Hospital One','Guangdong','Guangzhou','Yuexiu','Address','三级','甲等','在营','','', '2026-08-13')")
    connection.execute("INSERT INTO hospital_contacts VALUES (1,'H1','website','https://official.example.com/',1,NULL,'2026-08-14')")
    connection.commit()
    connection.close()

    row = tertiary_rows(path=database)[0]

    assert row['official_domain'] is None
