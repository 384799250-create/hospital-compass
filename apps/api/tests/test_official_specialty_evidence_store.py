from __future__ import annotations

import sqlite3

from app.official_specialty_evidence_store import (
    OfficialSpecialtyEvidence,
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
