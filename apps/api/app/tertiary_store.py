"""Dedicated read-only source for confirmed tertiary-A hospital candidates."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

from app.hospital_store import DEFAULT_DATA_DIR, connect, initialize

TERTIARY_DATABASE_FILENAME = 'tertiary-a.sqlite3'
TERTIARY_TIER = '\u4e09\u7ea7'
TERTIARY_GRADE = '\u7532\u7b49'
ACTIVE_STATUSES = ('\u5728\u8425', '\u8fd0\u8425\u4e2d', '\u6b63\u5e38', '\u6b63\u5e38\u8fd0\u8425')


@dataclass(frozen=True)
class TertiaryBuildReport:
    source_rows: int
    copied_rows: int
    copied_sources: int


def tertiary_database_path() -> Path:
    configured_path = os.environ.get('HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH', '').strip()
    if configured_path:
        return Path(configured_path)
    configured_database = os.environ.get('HOSPITAL_COMPASS_DATABASE_PATH', '').strip()
    if configured_database:
        return Path(configured_database)
    configured = os.environ.get('HOSPITAL_COMPASS_DATA_DIR', '').strip()
    return (Path(configured) if configured else DEFAULT_DATA_DIR) / TERTIARY_DATABASE_FILENAME


def build_tertiary_database(source: Path, target: Path | None = None) -> TertiaryBuildReport:
    """Rebuild target from rows explicitly labelled 三级甲等; no fuzzy tier matching."""
    target = target or tertiary_database_path()
    initialize(target)
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as source_connection, connect(target) as target_connection:
        source_connection.row_factory = sqlite3.Row
        source_rows = source_connection.execute('SELECT * FROM hospitals').fetchall()
        target_connection.execute('DELETE FROM hospital_sources')
        target_connection.execute('DELETE FROM hospitals')
        selected = [row for row in source_rows if '三级甲等' in str(row['tier'] or '')]
        columns = ('id', 'canonical_name', 'province', 'city', 'district', 'address', 'longitude', 'latitude', 'tier', 'nature', 'specialties_json', 'diseases_json', 'aliases_json', 'official_domain', 'registration_url', 'verification_status', 'source_updated_at', 'updated_at')
        values = [tuple(row[column] for column in columns) for row in selected]
        target_connection.executemany(
            f"INSERT INTO hospitals ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            values,
        )
        ids = {row['id'] for row in selected}
        sources = source_connection.execute('SELECT hospital_id,source_url,source_type,source_title,fetched_at FROM hospital_sources').fetchall()
        source_values = [tuple(row) for row in sources if row['hospital_id'] in ids]
        target_connection.executemany(
            'INSERT INTO hospital_sources (hospital_id,source_url,source_type,source_title,fetched_at) VALUES (?,?,?,?,?)',
            source_values,
        )
        target_connection.commit()
        return TertiaryBuildReport(len(source_rows), len(selected), len(source_values))


def tertiary_rows(*, province: str = '', city: str = '', district: str = '', path: Path | None = None) -> list[dict[str, object]]:
    target = path or tertiary_database_path()
    if target.exists():
        with sqlite3.connect(f'file:{target}?mode=ro', uri=True) as connection:
            # Read-only databases on Windows may not be able to create SQLite's
            # temporary sort files beside the database. Keep temporary query
            # data in memory so directory listings and ORDER BY remain usable.
            connection.execute('PRAGMA temp_store = MEMORY')
            connection.row_factory = sqlite3.Row
            columns = {row[1] for row in connection.execute('PRAGMA table_info(hospitals)')}
            if {'hospital_id', 'grade', 'operating_status'} <= columns:
                clauses = ["tier = '三级'", "grade = '甲等'", "operating_status IN ('在营', '运营中', '正常', '正常运营')"]
                official_domain = 'official_domain' if 'official_domain' in columns else "'' AS official_domain"
                registration_url = 'official_registration_url' if 'official_registration_url' in columns else "''"
                introduction = 'introduction' if 'introduction' in columns else "'' AS introduction"
                official_full_name = 'official_full_name' if 'official_full_name' in columns else 'canonical_name AS official_full_name'
                active_placeholders = ', '.join('?' for _ in ACTIVE_STATUSES)
                clauses = [
                    'tier = ?',
                    'grade = ?',
                    f'operating_status IN ({active_placeholders})',
                ]
                eligibility_params: list[str] = [TERTIARY_TIER, TERTIARY_GRADE, *ACTIVE_STATUSES]
                params: list[str] = []
                for field, value in (('province', province), ('city', city), ('district', district)):
                    if value:
                        clauses.append(f'{field} = ?')
                        params.append(value)
                params = [*eligibility_params, *params]
                rows = connection.execute(
                    f'''SELECT hospital_id AS id, canonical_name, {official_full_name}, province, city, district,
                               address, tier || grade AS tier, {introduction}, '[]' AS specialties_json,
                                {official_domain}, {registration_url} AS registration_url,
                               updated_at AS source_updated_at, updated_at
                        FROM hospitals WHERE {' AND '.join(clauses)} ORDER BY canonical_name''',
                    params,
                ).fetchall()
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                capability_columns = {
                    row[1] for row in connection.execute('PRAGMA table_info(department_capabilities)')
                } if 'department_capabilities' in tables else set()
                summary = 'dc.evidence_summary' if 'evidence_summary' in capability_columns else "''"
                evidence_url = 'dc.evidence_url' if 'evidence_url' in capability_columns else "''"
                verification_status = (
                    "COALESCE(dc.verification_status, '已核验')"
                    if 'verification_status' in capability_columns else "'已核验'"
                )
                capability_rows = connection.execute(
                    f'''SELECT dc.hospital_id, d.standard_name AS department,
                              dc.diagnosis_scope, dc.specialty_strength_level,
                              {summary} AS evidence_summary, {evidence_url} AS evidence_url,
                              {verification_status} AS verification_status
                       FROM department_capabilities dc
                       JOIN departments d ON d.department_id = dc.department_id
                       WHERE dc.hospital_id IN (SELECT hospital_id FROM hospitals WHERE tier = '三级' AND grade = '甲等' AND operating_status IN ('在营', '运营中', '正常', '正常运营'))'''
                ).fetchall() if {'department_capabilities', 'departments'} <= tables else []
                capabilities: dict[str, list[dict[str, str]]] = {}
                for capability in capability_rows:
                    status = str(capability['verification_status'] or '').strip()
                    if status in {'待复核', '来源不可访问', '失效'}:
                        continue
                    capabilities.setdefault(capability['hospital_id'], []).append({
                        'department': capability['department'] or '',
                        'diagnosis_scope': capability['diagnosis_scope'] or '',
                        'strength_level': capability['specialty_strength_level'] or '',
                        'evidence_summary': capability['evidence_summary'] or '',
                        'evidence_url': capability['evidence_url'] or '',
                        'verification_status': status,
                    })
                output = []
                for row in rows:
                    item = dict(row)
                    item['official_domain'] = _safe_url(item.get('official_domain'))
                    item['registration_url'] = _safe_url(item.get('registration_url'))
                    item['specialty_capabilities'] = capabilities.get(item['id'], [])
                    output.append(item)
                return output
    initialize(target)
    clauses = ["tier LIKE '%三级甲等%'"]
    params: list[str] = []
    for field, value in (('province', province), ('city', city), ('district', district)):
        if value:
            clauses.append(f'{field} = ?')
            params.append(value)
    with connect(target) as connection:
        rows = connection.execute(f"SELECT * FROM hospitals WHERE {' AND '.join(clauses)} ORDER BY canonical_name", params).fetchall()
        return [dict(row) for row in rows]


def _safe_url(value: object) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    if '://' not in text and text.startswith('www.'):
        text = f'https://{text}'
    parsed = urlparse(text)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return text
