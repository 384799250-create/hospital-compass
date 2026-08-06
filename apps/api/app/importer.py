import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


PILOT_CITIES = frozenset({'Beijing', 'Shanghai', 'Guangzhou'})
VALID_TIERS = frozenset({'primary', 'secondary', 'tertiary'})
MAX_SOURCE_AGE = timedelta(days=180)
IMPORT_COLUMNS = (
    'id', 'name', 'city', 'tier', 'source_url', 'source_date',
    'specialties', 'disease_tags', 'verified', 'published',
)


@dataclass(frozen=True)
class ImportError:
    row_number: int
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ImportReport:
    accepted: list[dict[str, str]]
    errors: list[ImportError]


def load_verified_beijing_rows(path: Path, today: date) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError('publish list is empty')
        if set(reader.fieldnames) != set(IMPORT_COLUMNS) or len(reader.fieldnames) != len(IMPORT_COLUMNS):
            raise ValueError('publish list headers must contain exactly the required columns')
        rows = list(reader)

    if not rows:
        raise ValueError('publish list is empty')
    if any(None in row for row in rows):
        raise ValueError('publish list rows must contain exactly the required columns')
    if any(row.get('city') != 'Beijing' for row in rows):
        raise ValueError('publish list contains a non-Beijing row')

    report = validate_import(rows, today)
    if report.errors:
        invalid_fields = sorted({field for error in report.errors for field in error.fields})
        raise ValueError(f'publish list contains invalid rows: {", ".join(invalid_fields)}')
    return report.accepted


def validate_import(rows: list[dict[str, str]], today: date) -> ImportReport:
    accepted: list[dict[str, str]] = []
    errors: list[ImportError] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=1):
        invalid_fields: list[str] = []
        hospital_id = row.get('id', '')
        if not hospital_id or hospital_id in seen_ids:
            invalid_fields.append('id')
        seen_ids.add(hospital_id)
        name = row.get('name', '')
        if not isinstance(name, str) or not name.strip():
            invalid_fields.append('name')
        if row.get('city') not in PILOT_CITIES:
            invalid_fields.append('city')
        if row.get('tier') not in VALID_TIERS:
            invalid_fields.append('tier')
        source_url_value = row.get('source_url', '')
        try:
            source_url = urlparse(source_url_value) if isinstance(source_url_value, str) else None
            has_https_hostname = source_url is not None and source_url.scheme == 'https' and bool(source_url.hostname)
        except ValueError:
            has_https_hostname = False
        if not has_https_hostname:
            invalid_fields.append('source_url')
        try:
            source_date_value = row.get('source_date', '')
            source_date = date.fromisoformat(source_date_value) if isinstance(source_date_value, str) else None
        except (TypeError, ValueError):
            invalid_fields.append('source_date')
        else:
            if source_date is None or source_date > today or today - source_date > MAX_SOURCE_AGE:
                invalid_fields.append('source_date')
        for field in ('specialties', 'disease_tags'):
            value = row.get(field, '')
            if not isinstance(value, str) or not value.strip():
                invalid_fields.append(field)
        for field in ('verified', 'published'):
            if row.get(field) != 'true':
                invalid_fields.append(field)
        if invalid_fields:
            errors.append(ImportError(row_number, tuple(invalid_fields)))
        else:
            accepted.append(row)
    return ImportReport(accepted, errors)
