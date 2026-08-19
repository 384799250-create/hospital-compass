"""Import OpenStreetMap hospital features into the F-drive directory."""

import json
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path

from app.hospital_store import connect, initialize


def import_osm_hospitals(path: Path, *, province: str, database_path: Path | None = None) -> int:
    payload = json.loads(path.read_text(encoding='utf-8'))
    imported = 0
    initialize(database_path)
    connection = connect(database_path)
    now = datetime.now(UTC).isoformat()
    for element in payload.get('elements', []):
        tags = element.get('tags') or {}
        name = ' '.join(str(tags.get('name') or '').split())
        if not name:
            continue
        element_type = str(element.get('type') or 'node')
        element_id = str(element.get('id') or '')
        if not element_id:
            continue
        address = ' '.join(filter(None, [
            str(tags.get('addr:street') or '').strip(),
            str(tags.get('addr:housenumber') or '').strip(),
        ])).strip()
        city = str(tags.get('addr:city') or tags.get('addr:town') or tags.get('is_in:city') or '').strip()
        district = str(tags.get('addr:district') or tags.get('addr:county') or tags.get('is_in:district') or '').strip()
        coordinates = element.get('center') or element
        hospital_id = 'osm-' + sha256(f'{element_type}|{element_id}'.encode()).hexdigest()[:20]
        connection.execute('''INSERT INTO hospitals (
            id, canonical_name, province, city, district, address, longitude, latitude,
            tier, nature, verification_status, source_updated_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET canonical_name=excluded.canonical_name,
            province=excluded.province, city=excluded.city, district=excluded.district,
            address=excluded.address, longitude=excluded.longitude, latitude=excluded.latitude,
            tier=excluded.tier, nature=excluded.nature,
            verification_status=excluded.verification_status,
            source_updated_at=excluded.source_updated_at, updated_at=excluded.updated_at''', (
            hospital_id, name, province, city, district, address,
            _number(coordinates.get('lon')), _number(coordinates.get('lat')),
            str(tags.get('healthcare:speciality') or ''), str(tags.get('operator:type') or ''),
            '待核验', str(payload.get('osm3s', {}).get('timestamp_osm_base') or ''), now,
        ))
        connection.execute(
            'INSERT INTO hospital_sources (hospital_id, source_url, source_type, source_title, fetched_at) VALUES (?, ?, ?, ?, ?)',
            (hospital_id, f'https://www.openstreetmap.org/{element_type}/{element_id}', 'OpenStreetMap（ODbL）', name, now),
        )
        imported += 1
    connection.commit()
    connection.close()
    return imported


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None
