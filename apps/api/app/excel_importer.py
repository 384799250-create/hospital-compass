"""Map the user-provided medical-insurance workbook to public hospital fields."""

from hashlib import sha256
import re
from urllib.parse import urlparse


def record_from_row(row: tuple[object, ...] | list[object]) -> dict[str, object]:
    values = [str(value or '').strip() for value in row]
    province, city, name, address = (values + [''] * 4)[:4]
    tier = values[5] if len(values) > 5 else ''
    specialties = _split_specialties(values[6] if len(values) > 6 else '')
    nature = values[7] if len(values) > 7 else ''
    website = values[9] if len(values) > 9 else ''
    district = _district(address)
    identity = '|'.join((province, city, name, address))
    return {
        'id': 'medical-insurance-' + sha256(identity.encode('utf-8')).hexdigest()[:20],
        'name': name,
        'province': province,
        'city': city,
        'district': district,
        'address': address,
        'tier': tier,
        'nature': nature,
        'specialties': specialties,
        'official_domain': urlparse(website).hostname or '' if website else '',
        'registration_url': website if website.startswith(('http://', 'https://')) else '',
    }


def _split_specialties(value: str) -> list[str]:
    return [part.strip() for part in re.split(r'[、,，;；·|]+', value) if part.strip()]


def _district(address: str) -> str:
    matches = re.findall(r'(?:省|市)([^市省]{1,8}(?:区|县|旗))', address)
    if not matches:
        matches = re.findall(r'([\u4e00-\u9fff]{1,8}(?:区|县|旗))', address)
    return matches[-1] if matches else ''
