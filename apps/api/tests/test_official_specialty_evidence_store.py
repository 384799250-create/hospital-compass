from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from app.official_specialty_evidence_store import (
    OfficialSpecialtyEvidence,
    expire_stale_official_capabilities,
    persist_official_capabilities,
)


def _create_official_database(tmp_path):
    database = tmp_path / 'official-hospital.db'
    with sqlite3.connect(database) as connection:
        connection.executescript('''
            CREATE TABLE hospitals (
                hospital_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                official_domain TEXT NOT NULL
            );
            CREATE TABLE departments (
                department_id TEXT PRIMARY KEY,
                standard_name TEXT NOT NULL
            );
            CREATE TABLE sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                url TEXT,
                title TEXT,
                retrieved_at TEXT,
                content_hash TEXT,
                is_official INTEGER DEFAULT 0
            );
            CREATE TABLE evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                field_name TEXT,
                source_id INTEGER,
                quoted_text TEXT,
                confidence REAL DEFAULT 0.5,
                review_status TEXT DEFAULT '待核验'
            );
            CREATE TABLE department_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id TEXT NOT NULL,
                department_id TEXT NOT NULL,
                diagnosis_scope TEXT,
                specialty_strength_level TEXT,
                evidence_id INTEGER,
                evidence_summary TEXT,
                evidence_url TEXT,
                verification_status TEXT
            );
        ''')
        connection.execute(
            'INSERT INTO hospitals (hospital_id, canonical_name, official_domain) VALUES (?, ?, ?)',
            ('H1', '合浦县人民医院', 'hospital.example.org'),
        )
        connection.execute(
            'INSERT INTO departments (department_id, standard_name) VALUES (?, ?)',
            ('D1', '神经内科'),
        )
    return database


def _official_evidence() -> OfficialSpecialtyEvidence:
    return OfficialSpecialtyEvidence(
        hospital_id='H1',
        department='神经内科',
        strength_level='广西医疗卫生重点学科（县级）',
        quoted_text='神经内科为广西医疗卫生重点学科（县级）',
        evidence_url='https://hospital.example.org/about',
        source_title='医院简介',
        fetched_at='2026-08-17T00:00:00+00:00',
    )


def test_persist_official_capability_writes_source_evidence_and_capability(tmp_path):
    database = _create_official_database(tmp_path)

    report = persist_official_capabilities([_official_evidence()], path=database)

    assert report.inserted == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT is_official FROM sources').fetchone()[0] == 1
        assert connection.execute('SELECT quoted_text, review_status FROM evidence').fetchone() == (
            '神经内科为广西医疗卫生重点学科（县级）',
            '官网自动核验',
        )
        assert connection.execute(
            'SELECT specialty_strength_level, evidence_summary, evidence_url, verification_status '
            'FROM department_capabilities'
        ).fetchone() == (
            '广西医疗卫生重点学科（县级）',
            '神经内科为广西医疗卫生重点学科（县级）',
            'https://hospital.example.org/about',
            '官网自动核验',
        )


def test_expire_stale_official_capability_excludes_only_automatic_records(tmp_path):
    database = _create_official_database(tmp_path)
    persist_official_capabilities([_official_evidence()], path=database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE department_capabilities SET last_verified_at = ? WHERE verification_status = '官网自动核验'",
            ('2026-02-01T00:00:00+00:00',),
        )
        connection.execute(
            '''INSERT INTO department_capabilities (
                   hospital_id, department_id, specialty_strength_level, verification_status
               ) VALUES (?, ?, ?, ?)''',
            ('H1', 'D1', '国家级重点', '已核验'),
        )

    expired = expire_stale_official_capabilities(
        path=database,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert expired == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT verification_status FROM department_capabilities WHERE specialty_strength_level = '广西医疗卫生重点学科（县级）'"
        ).fetchone()[0] == '待复核'
        assert connection.execute(
            "SELECT verification_status FROM department_capabilities WHERE specialty_strength_level = '国家级重点'"
        ).fetchone()[0] == '已核验'


def test_current_official_evidence_reactivates_a_matching_stale_record(tmp_path):
    database = _create_official_database(tmp_path)
    persist_official_capabilities([_official_evidence()], path=database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE department_capabilities SET last_verified_at = '2026-02-01T00:00:00+00:00'"
        )
    expire_stale_official_capabilities(
        path=database,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    report = persist_official_capabilities([_official_evidence()], path=database)

    assert report.refreshed == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM department_capabilities').fetchone()[0] == 1
        assert connection.execute(
            'SELECT verification_status FROM department_capabilities'
        ).fetchone()[0] == '官网自动核验'


def test_persist_expires_old_automatic_evidence_before_processing_new_items(tmp_path):
    database = _create_official_database(tmp_path)
    persist_official_capabilities([_official_evidence()], path=database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE department_capabilities SET last_verified_at = '2000-01-01T00:00:00+00:00'"
        )

    persist_official_capabilities([], path=database)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            'SELECT verification_status FROM department_capabilities'
        ).fetchone()[0] == '待复核'


@pytest.mark.parametrize(
    ('hospital_id', 'department', 'level', 'quote', 'url'),
    [
        ('H1', '神经内科', '县级重点学科', '神经内科为县级重点学科', 'http://hospital.example.org/about'),
        ('H1', '神经内科', '县级重点学科', '神经内科为县级重点学科', 'https://third-party.example.org/about'),
        ('MISSING', '神经内科', '县级重点学科', '神经内科为县级重点学科', 'https://hospital.example.org/about'),
        ('H1', '不存在科室', '县级重点学科', '不存在科室为县级重点学科', 'https://hospital.example.org/about'),
        ('H1', '神经内科', '特色专科介绍', '神经内科特色专科介绍', 'https://hospital.example.org/about'),
        ('H1', '神经内科', '县级重点学科', '', 'https://hospital.example.org/about'),
    ],
)
def test_persist_rejects_non_official_or_non_qualifying_evidence(
    tmp_path, hospital_id, department, level, quote, url,
):
    database = _create_official_database(tmp_path)
    item = OfficialSpecialtyEvidence(
        hospital_id=hospital_id,
        department=department,
        strength_level=level,
        quoted_text=quote,
        evidence_url=url,
        source_title='医院简介',
        fetched_at='2026-08-17T00:00:00+00:00',
    )

    report = persist_official_capabilities([item], path=database)

    assert (report.inserted, report.refreshed, report.rejected) == (0, 0, 1)
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM department_capabilities').fetchone()[0] == 0


def test_persist_deduplicates_matching_official_evidence(tmp_path):
    database = _create_official_database(tmp_path)
    persist_official_capabilities([_official_evidence()], path=database)

    report = persist_official_capabilities([_official_evidence()], path=database)

    assert (report.inserted, report.refreshed, report.rejected) == (0, 1, 0)
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM department_capabilities').fetchone()[0] == 1


def test_persist_does_not_modify_human_verified_capability(tmp_path):
    database = _create_official_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            '''INSERT INTO department_capabilities (
                   hospital_id, department_id, specialty_strength_level, verification_status
               ) VALUES (?, ?, ?, ?)''',
            ('H1', 'D1', '国家级重点', '已核验'),
        )

    persist_official_capabilities([_official_evidence()], path=database)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT specialty_strength_level, verification_status FROM department_capabilities "
            "WHERE verification_status = '已核验'"
        ).fetchone() == ('国家级重点', '已核验')


def test_persist_migrates_legacy_capability_columns_before_writing(tmp_path):
    database = _create_official_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE department_capabilities')
        connection.execute('''
            CREATE TABLE department_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id TEXT NOT NULL, department_id TEXT NOT NULL,
                diagnosis_scope TEXT, specialty_strength_level TEXT, evidence_id INTEGER
            )
        ''')

    report = persist_official_capabilities([_official_evidence()], path=database)

    assert report.inserted == 1
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(department_capabilities)')}
        assert {'evidence_summary', 'evidence_url', 'verification_status'}.issubset(columns)
