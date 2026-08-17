"""Persist explicit specialty-strength evidence from registered hospital websites."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3
from urllib.parse import urlparse


AUTOMATIC_VERIFICATION_STATUS = '官网自动核验'


@dataclass(frozen=True)
class OfficialSpecialtyEvidence:
    hospital_id: str
    department: str
    strength_level: str
    quoted_text: str
    evidence_url: str
    source_title: str
    fetched_at: str


@dataclass(frozen=True)
class PersistReport:
    inserted: int
    refreshed: int
    rejected: int


def persist_official_capabilities(
    items: Iterable[OfficialSpecialtyEvidence], *, path: Path,
) -> PersistReport:
    """Persist valid official-site evidence without modifying existing manual rows."""
    inserted = refreshed = rejected = 0
    with _connect(path) as connection:
        _ensure_schema(connection)
        for item in items:
            hospital = connection.execute(
                'SELECT official_domain FROM hospitals WHERE hospital_id = ?',
                (item.hospital_id,),
            ).fetchone()
            department = connection.execute(
                'SELECT department_id FROM departments WHERE standard_name = ?',
                (item.department,),
            ).fetchone()
            if (
                hospital is None
                or department is None
                or not _matches_official_domain(item.evidence_url, hospital['official_domain'])
                or not _is_recognized_strength_level(item.strength_level)
                or not item.quoted_text.strip()
            ):
                rejected += 1
                continue

            fingerprint = hashlib.sha256(item.quoted_text.strip().encode('utf-8')).hexdigest()
            source_id = _upsert_source(connection, item, fingerprint)
            existing = connection.execute(
                '''SELECT id FROM department_capabilities
                   WHERE hospital_id = ? AND department_id = ? AND evidence_url = ?
                     AND evidence_fingerprint = ? AND verification_status = ?''',
                (
                    item.hospital_id,
                    department['department_id'],
                    item.evidence_url,
                    fingerprint,
                    AUTOMATIC_VERIFICATION_STATUS,
                ),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    'UPDATE department_capabilities SET last_verified_at = ? WHERE id = ?',
                    (_timestamp(item.fetched_at), existing['id']),
                )
                refreshed += 1
                continue

            cursor = connection.execute(
                '''INSERT INTO evidence (
                       entity_type, entity_id, field_name, source_id, quoted_text, confidence, review_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (
                    'department',
                    f"{item.hospital_id}:{department['department_id']}",
                    'specialty_strength_level',
                    source_id,
                    item.quoted_text.strip(),
                    1.0,
                    AUTOMATIC_VERIFICATION_STATUS,
                ),
            )
            connection.execute(
                '''INSERT INTO department_capabilities (
                       hospital_id, department_id, diagnosis_scope, specialty_strength_level, evidence_id,
                       evidence_summary, evidence_url, verification_status, evidence_fingerprint, last_verified_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    item.hospital_id,
                    department['department_id'],
                    item.quoted_text.strip(),
                    item.strength_level.strip(),
                    cursor.lastrowid,
                    item.quoted_text.strip(),
                    item.evidence_url.strip(),
                    AUTOMATIC_VERIFICATION_STATUS,
                    fingerprint,
                    _timestamp(item.fetched_at),
                ),
            )
            inserted += 1
    return PersistReport(inserted=inserted, refreshed=refreshed, rejected=rejected)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    columns = {row['name'] for row in connection.execute('PRAGMA table_info(department_capabilities)')}
    for name, definition in (
        ('evidence_fingerprint', 'TEXT'),
        ('last_verified_at', 'TEXT'),
    ):
        if name not in columns:
            connection.execute(f'ALTER TABLE department_capabilities ADD COLUMN {name} {definition}')
    connection.execute(
        '''CREATE UNIQUE INDEX IF NOT EXISTS idx_auto_capability_fingerprint
           ON department_capabilities(hospital_id, department_id, evidence_url, evidence_fingerprint)
           WHERE verification_status = '官网自动核验' '''
    )


def _upsert_source(
    connection: sqlite3.Connection,
    item: OfficialSpecialtyEvidence,
    fingerprint: str,
) -> int:
    existing = connection.execute(
        'SELECT source_id FROM sources WHERE url = ? AND content_hash = ?',
        (item.evidence_url.strip(), fingerprint),
    ).fetchone()
    if existing is not None:
        connection.execute(
            'UPDATE sources SET retrieved_at = ? WHERE source_id = ?',
            (_timestamp(item.fetched_at), existing['source_id']),
        )
        return int(existing['source_id'])
    cursor = connection.execute(
        '''INSERT INTO sources (source_type, url, title, retrieved_at, content_hash, is_official)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            '医院官网',
            item.evidence_url.strip(),
            item.source_title.strip(),
            _timestamp(item.fetched_at),
            fingerprint,
            1,
        ),
    )
    return int(cursor.lastrowid)


def _matches_official_domain(url: str, official_domain: object) -> bool:
    source = urlparse(str(url or '').strip())
    registered_text = str(official_domain or '').strip()
    registered = urlparse(
        registered_text if '://' in registered_text else f'https://{registered_text}'
    )
    host = (source.hostname or '').casefold()
    domain = (registered.hostname or '').casefold()
    return source.scheme == 'https' and bool(domain) and (host == domain or host.endswith(f'.{domain}'))


def _is_recognized_strength_level(value: str) -> bool:
    text = value.casefold()
    if any(marker in text for marker in ('国家临床重点专科', '国家重点专科', '国家级重点', '国家医学中心', '国家区域医疗中心')):
        return True
    if any(marker in text for marker in ('省级区域医疗中心', '省级重点专科', '省重点专科', '省级重点学科')):
        return True
    if '县级' in text and any(marker in text for marker in ('重点学科', '重点专科')):
        return True
    return any(marker in text for marker in ('市级重点学科', '市重点学科', '市级重点专科', '市重点专科', '院内临床重点专科'))


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
