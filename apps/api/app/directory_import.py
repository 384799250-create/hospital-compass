"""Import public national tertiary-hospital directory snapshots."""

import csv
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path
import re

from app.hospital_store import connect, initialize

SOURCE_URL = 'https://github.com/46319943/3AHospital/blob/master/result.csv'


def import_3a_csv(csv_path: Path, *, database_path: Path | None = None) -> int:
    imported = 0
    target = database_path
    initialize(target)
    now = datetime.now(UTC).isoformat()
    connection = connect(target)
    with csv_path.open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            name = ' '.join((row.get('name') or '').split())
            address = ' '.join((row.get('address') or '').split())
            if not name or not address:
                continue
            province, city, district = split_address(address)
            hospital_id = '3a-' + sha256(f'{name}|{address}'.encode('utf-8')).hexdigest()[:20]
            connection.execute('''INSERT INTO hospitals (
                id, canonical_name, province, city, district, address, longitude, latitude,
                tier, verification_status, source_updated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET canonical_name=excluded.canonical_name,
                province=excluded.province, city=excluded.city, district=excluded.district,
                address=excluded.address, longitude=excluded.longitude, latitude=excluded.latitude,
                tier=excluded.tier, verification_status=excluded.verification_status,
                source_updated_at=excluded.source_updated_at, updated_at=excluded.updated_at''', (
                hospital_id, name, province, city, district, address,
                _number(row.get('longitude_wgs84')), _number(row.get('latitude_wgs84')),
                '三级甲等（公开名录）', '待核验', '2026-08-07', now,
            ))
            connection.execute(
                'INSERT INTO hospital_sources (hospital_id, source_url, source_type, source_title, fetched_at) VALUES (?, ?, ?, ?, ?)',
                (hospital_id, SOURCE_URL, 'GitHub公开数据集', '3AHospital 全国三甲医院名称、地址、经纬度', now),
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


def split_address(address: str) -> tuple[str, str, str]:
    province_match = re.match(r'^(北京市|上海市|天津市|重庆市|[^省]{2,8}省|[^自治区]{2,10}自治区|[^特别行政区]{2,10}特别行政区)', address)
    province = province_match.group(1) if province_match else ''
    remaining = address[len(province):] if province else address
    if province in {'北京市', '上海市', '天津市', '重庆市'}:
        city = province
    else:
        city_match = re.match(r'^([^区县,，]{2,12}市)', remaining)
        city = city_match.group(1) if city_match else ''
    district_match = re.search(r'([^市区县]{1,12}(?:区|县|旗))', remaining)
    district = district_match.group(1) if district_match else ''
    return province, city, district
