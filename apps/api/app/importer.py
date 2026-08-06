from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlparse


PILOT_CITIES = frozenset({'Beijing', 'Shanghai', 'Guangzhou'})
VALID_TIERS = frozenset({'primary', 'secondary', 'tertiary'})
MAX_SOURCE_AGE = timedelta(days=80)


@dataclass(frozen=True)
class ImportError:
    row_number: int
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ImportReport:
    accepted: list[dict[str, str]]
    errors: list[ImportError]


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
        if row.get('city') not in PILOT_CITIES:
            invalid_fields.append('city')
        if row.get('tier') not in VALID_TIERS:
            invalid_fields.append('tier')
        source_url = urlparse(row.get('source_url', ''))
        if source_url.scheme != 'https' or not source_url.netloc:
            invalid_fields.append('source_url')
        try:
            source_date = date.fromisoformat(row.get('source_date', ''))
        except ValueError:
            invalid_fields.append('source_date')
        else:
            if source_date > today or today - source_date > MAX_SOURCE_AGE:
                invalid_fields.append('source_date')
        for field in ('specialties', 'disease_tags'):
            if not row.get(field, '').strip():
                invalid_fields.append(field)
        for field in ('verified', 'published'):
            if row.get(field) != 'true':
                invalid_fields.append(field)
        if invalid_fields:
            errors.append(ImportError(row_number, tuple(invalid_fields)))
        else:
            accepted.append(row)
    return ImportReport(accepted, errors)
