"""Conservative, reversible cleanup for the F-drive hospital directory."""

from dataclasses import dataclass
from datetime import UTC, datetime
import re
import sqlite3
from pathlib import Path

from app.hospital_store import connect, initialize

MUNICIPALITIES = {'北京市', '上海市', '天津市', '重庆市'}
PROVINCE_SUFFIXES = ('省', '自治区', '特别行政区')
DISTRICT_PATTERN = re.compile(r'([^省市县区旗]{1,12}(?:区|县|旗))')


@dataclass(frozen=True)
class CleanReport:
    scanned_rows: int
    location_updates: int
    merged_rows: int
    dry_run: bool


def _clean(value: object) -> str:
    return ' '.join(str(value or '').replace('，', ',').split()).strip()


def _province_from_address(address: str) -> str:
    for municipality in MUNICIPALITIES:
        if address.startswith(municipality):
            return municipality
    match = re.match(r'^(.+?(?:省|自治区|特别行政区))', address)
    return match.group(1) if match else ''


def _city_from_address(address: str, province: str) -> str:
    remaining = address[len(province):] if province and address.startswith(province) else address
    if province in MUNICIPALITIES:
        return province
    match = re.match(r'^(.{2,12}?市)', remaining)
    return match.group(1) if match else ''


def normalize_location(province: object, city: object, district: object, address: object) -> tuple[str, str, str]:
    """Fill only fields supported by explicit address text; never guess a district."""
    province_text, city_text, district_text, address_text = map(_clean, (province, city, district, address))
    inferred_province = _province_from_address(address_text)
    normalized_province = province_text or inferred_province
    if normalized_province in MUNICIPALITIES:
        normalized_city = normalized_province
    else:
        normalized_city = city_text or _city_from_address(address_text, normalized_province)
    inferred_district = DISTRICT_PATTERN.search(address_text)
    normalized_district = district_text or (inferred_district.group(1) if inferred_district else '')
    if normalized_district and normalized_district not in address_text and city_text:
        normalized_district = district_text
    return normalized_province, normalized_city, normalized_district


def _row_quality(row: sqlite3.Row) -> tuple[int, int, int, str]:
    fields = ('address', 'district', 'city', 'province', 'tier', 'official_domain', 'registration_url')
    populated = sum(bool(_clean(row[field])) for field in fields)
    sources = int(row['_source_count'] or 0)
    return populated, sources, len(_clean(row['address'])), str(row['id'])


def clean_database(path: Path | None = None, *, apply: bool = False) -> CleanReport:
    target = path or Path(r'F:\hospital-compass-data\hospital-compass.sqlite3')
    initialize(target)
    with connect(target) as connection:
        rows = connection.execute(
            '''SELECT h.*, (SELECT COUNT(*) FROM hospital_sources s WHERE s.hospital_id=h.id) AS _source_count
               FROM hospitals h ORDER BY h.id'''
        ).fetchall()
        updates: list[tuple[str, str, str, str]] = []
        for row in rows:
            location = normalize_location(row['province'], row['city'], row['district'], row['address'])
            if location != (row['province'], row['city'], row['district']):
                updates.append((location[0], location[1], location[2], row['id']))

        duplicate_groups = connection.execute(
            '''SELECT canonical_name,province,city,district,address,COUNT(*) AS n
               FROM hospitals GROUP BY canonical_name,province,city,district,address HAVING n > 1'''
        ).fetchall()
        merges: list[tuple[str, str]] = []
        for group in duplicate_groups:
            group_rows = connection.execute(
                '''SELECT h.*, (SELECT COUNT(*) FROM hospital_sources s WHERE s.hospital_id=h.id) AS _source_count
                   FROM hospitals h WHERE canonical_name=? AND province=? AND city=? AND district=? AND address=?''',
                tuple(group[key] for key in ('canonical_name', 'province', 'city', 'district', 'address')),
            ).fetchall()
            survivor = max(group_rows, key=_row_quality)
            merges.extend((survivor['id'], row['id']) for row in group_rows if row['id'] != survivor['id'])

        if apply:
            now = datetime.now(UTC).isoformat()
            for province, city, district, hospital_id in updates:
                connection.execute(
                    'UPDATE hospitals SET province=?,city=?,district=?,updated_at=? WHERE id=?',
                    (province, city, district, now, hospital_id),
                )
            for survivor_id, duplicate_id in merges:
                connection.execute('UPDATE hospital_sources SET hospital_id=? WHERE hospital_id=?', (survivor_id, duplicate_id))
                connection.execute('DELETE FROM hospitals WHERE id=?', (duplicate_id,))
            connection.commit()
        return CleanReport(len(rows), len(updates), len(merges), not apply)
