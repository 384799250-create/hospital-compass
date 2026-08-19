"""Disk-backed hospital directory storage.

The database lives outside the source tree so a growing national directory
does not consume the system disk or get bundled into deployments.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

DEFAULT_DATA_DIR = Path(r'F:\hospital-compass-data')
DATABASE_FILENAME = 'hospital-compass.sqlite3'


def data_dir() -> Path:
    configured = os.environ.get('HOSPITAL_COMPASS_DATA_DIR', '').strip()
    return Path(configured) if configured else DEFAULT_DATA_DIR


def database_path() -> Path:
    configured_path = os.environ.get('HOSPITAL_COMPASS_DATABASE_PATH', '').strip()
    if configured_path:
        return Path(configured_path)
    return data_dir() / DATABASE_FILENAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize(path: Path | None = None) -> Path:
    target = path or database_path()
    with connect(target) as connection:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS hospitals (
                id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                province TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                district TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                longitude REAL,
                latitude REAL,
                tier TEXT NOT NULL DEFAULT '',
                nature TEXT NOT NULL DEFAULT '',
                specialties_json TEXT NOT NULL DEFAULT '[]',
                diseases_json TEXT NOT NULL DEFAULT '[]',
                aliases_json TEXT NOT NULL DEFAULT '[]',
                official_domain TEXT NOT NULL DEFAULT '',
                registration_url TEXT NOT NULL DEFAULT '',
                verification_status TEXT NOT NULL DEFAULT '待核验',
                source_updated_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hospital_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id TEXT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT '公开资料',
                source_title TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hospitals_location
                ON hospitals(province, city, district);
            CREATE INDEX IF NOT EXISTS idx_hospital_sources_hospital
                ON hospital_sources(hospital_id);
            '''
        )
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(hospitals)')}
        for name, definition in (('longitude', 'REAL'), ('latitude', 'REAL')):
            if name not in columns:
                connection.execute(f'ALTER TABLE hospitals ADD COLUMN {name} {definition}')
    return target


def upsert_hospital(
    record: Mapping[str, object],
    sources: Iterable[Mapping[str, object]] = (),
    path: Path | None = None,
) -> None:
    target = path or database_path()
    if not target.exists():
        initialize(target)
    hospital_id = _text(record.get('id'))
    name = _text(record.get('canonical_name') or record.get('name'))
    if not hospital_id or not name:
        raise ValueError('hospital id and name are required')
    now = datetime.now(UTC).isoformat()
    with connect(target) as connection:
        connection.execute(
            '''INSERT INTO hospitals (
                id, canonical_name, province, city, district, address, longitude, latitude, tier, nature,
                specialties_json, diseases_json, aliases_json, official_domain,
                registration_url, verification_status, source_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                canonical_name=excluded.canonical_name, province=excluded.province,
                city=excluded.city, district=excluded.district, address=excluded.address,
                longitude=excluded.longitude, latitude=excluded.latitude,
                tier=excluded.tier, nature=excluded.nature,
                specialties_json=excluded.specialties_json, diseases_json=excluded.diseases_json,
                aliases_json=excluded.aliases_json, official_domain=excluded.official_domain,
                registration_url=excluded.registration_url,
                verification_status=excluded.verification_status,
                source_updated_at=excluded.source_updated_at, updated_at=excluded.updated_at''',
            (
                hospital_id, name, _text(record.get('province')), _text(record.get('city')),
                _text(record.get('district')), _text(record.get('address')),
                _float(record.get('longitude')), _float(record.get('latitude')),
                _text(record.get('tier')),
                _text(record.get('nature')), _json_list(record.get('specialties')),
                _json_list(record.get('diseases') or record.get('disease_tags')),
                _json_list(record.get('aliases')), _text(record.get('official_domain')),
                _text(record.get('registration_url')), _text(record.get('verification_status') or '待核验'),
                _text(record.get('source_updated_at')), now,
            ),
        )
        for source in sources:
            url = _text(source.get('source_url') or source.get('url'))
            if not url or urlparse(url).scheme not in {'http', 'https', 'file'}:
                continue
            connection.execute(
                'INSERT INTO hospital_sources (hospital_id, source_url, source_type, source_title, fetched_at) VALUES (?, ?, ?, ?, ?)',
                (hospital_id, url, _text(source.get('source_type') or '公开资料'), _text(source.get('title')), _text(source.get('fetched_at') or now)),
            )


def upsert_hospitals_bulk(
    items: Iterable[tuple[Mapping[str, object], Iterable[Mapping[str, object]]]],
    path: Path | None = None,
) -> int:
    target = path or database_path()
    initialize(target)
    count = 0
    with connect(target) as connection:
        for record, sources in items:
            hospital_id = _text(record.get('id'))
            name = _text(record.get('canonical_name') or record.get('name'))
            if not hospital_id or not name:
                continue
            now = datetime.now(UTC).isoformat()
            connection.execute(
                '''INSERT INTO hospitals (
                    id, canonical_name, province, city, district, address, longitude, latitude, tier, nature,
                    specialties_json, diseases_json, aliases_json, official_domain,
                    registration_url, verification_status, source_updated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET canonical_name=excluded.canonical_name,
                    province=excluded.province, city=excluded.city, district=excluded.district,
                    address=excluded.address, longitude=excluded.longitude, latitude=excluded.latitude,
                    tier=excluded.tier, nature=excluded.nature,
                    specialties_json=excluded.specialties_json, diseases_json=excluded.diseases_json,
                    aliases_json=excluded.aliases_json, official_domain=excluded.official_domain,
                    registration_url=excluded.registration_url, verification_status=excluded.verification_status,
                    source_updated_at=excluded.source_updated_at, updated_at=excluded.updated_at''',
                (
                    hospital_id, name, _text(record.get('province')), _text(record.get('city')),
                    _text(record.get('district')), _text(record.get('address')),
                    _float(record.get('longitude')), _float(record.get('latitude')), _text(record.get('tier')),
                    _text(record.get('nature')), _json_list(record.get('specialties')),
                    _json_list(record.get('diseases') or record.get('disease_tags')),
                    _json_list(record.get('aliases')), _text(record.get('official_domain')),
                    _text(record.get('registration_url')), _text(record.get('verification_status') or '待核验'),
                    _text(record.get('source_updated_at')), now,
                ),
            )
            for source in sources:
                url = _text(source.get('source_url') or source.get('url'))
                if not url or urlparse(url).scheme not in {'http', 'https', 'file'}:
                    continue
                connection.execute(
                    'INSERT INTO hospital_sources (hospital_id, source_url, source_type, source_title, fetched_at) VALUES (?, ?, ?, ?, ?)',
                    (hospital_id, url, _text(source.get('source_type') or '鍏紑璧勬枡'), _text(source.get('title')), _text(source.get('fetched_at') or now)),
                )
            count += 1
    return count


def _text(value: object) -> str:
    return ' '.join(str(value or '').split())


def _json_list(value: object) -> str:
    if isinstance(value, str):
        values = [part.strip() for part in value.split('|') if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        values = [_text(part) for part in value if _text(part)]
    else:
        values = []
    return json.dumps(list(dict.fromkeys(values)), ensure_ascii=False)


def _float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def directory_rows(*, province: str = '', city: str = '', district: str = '') -> list[dict[str, object]]:
    """Read imported directory rows for recall fallback, without ranking them."""
    initialize()
    clauses: list[str] = []
    params: list[str] = []
    for field, value in (('province', province), ('city', city), ('district', district)):
        if value:
            clauses.append(f'{field} = ?')
            params.append(value)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    with connect() as connection:
        rows = connection.execute(
            f'SELECT * FROM hospitals{where} ORDER BY canonical_name', params,
        ).fetchall()
        return [dict(row) for row in rows]
