import csv
from datetime import date
from pathlib import Path

from app.data import PILOT_DRAFT_CSV_PATH
from app.importer import validate_import
import pytest


def row(**overrides: str) -> dict[str, str]:
    """A complete, independently valid import row."""
    value = {
        'id': 'pilot-1',
        'name': 'Draft Pilot Hospital',
        'city': 'Beijing',
        'tier': 'tertiary',
        'source_url': 'https://source.test/pilot-1',
        'source_date': '2026-08-01',
        'specialties': 'cardiology',
        'disease_tags': 'chest-pain',
        'verified': 'true',
        'published': 'true',
    }
    value.update(overrides)
    return value


def test_rejects_non_https_source_and_non_pilot_city():
    report = validate_import([row(source_url='http://bad.test', city='Wuhan')], date(2026, 8, 6))

    assert report.accepted == []
    assert {'source_url', 'city'} <= set(report.errors[0].fields)


def test_rejects_https_url_without_a_host():
    report = validate_import([row(source_url='https://')], date(2026, 8, 6))

    assert report.accepted == []
    assert report.errors[0].fields == ('source_url',)


@pytest.mark.parametrize('source_url', ['https://user@', 'https://:443'])
def test_rejects_https_urls_without_a_hostname(source_url):
    report = validate_import([row(source_url=source_url)], date(2026, 8, 6))

    assert report.accepted == []
    assert report.errors[0].fields == ('source_url',)


@pytest.mark.parametrize('field', ['source_date', 'specialties', 'disease_tags'])
def test_none_required_source_or_tag_fields_return_row_errors(field):
    report = validate_import([row(**{field: None})], date(2026, 8, 6))

    assert report.accepted == []
    assert field in report.errors[0].fields


def test_reports_every_required_field_error_without_accepting_invalid_rows():
    report = validate_import([
        row(
            id='',
            tier='unknown',
            source_date='2026-05-17',
            specialties='',
            disease_tags='',
            verified='True',
            published='false',
        ),
    ], date(2026, 8, 6))

    assert report.accepted == []
    assert {
        'id', 'tier', 'source_date', 'specialties', 'disease_tags', 'verified', 'published',
    } <= set(report.errors[0].fields)


def test_rejects_duplicate_ids_and_future_or_malformed_source_dates():
    report = validate_import([
        row(id='duplicate', source_date='not-a-date'),
        row(id='duplicate', source_date='2026-08-07'),
    ], date(2026, 8, 6))

    assert report.accepted == []
    assert report.errors[0].fields == ('source_date',)
    assert set(report.errors[1].fields) == {'id', 'source_date'}


def test_pilot_csv_contains_thirty_unpublished_unverified_draft_rows():
    csv_path = Path(__file__).parents[1] / PILOT_DRAFT_CSV_PATH
    with csv_path.open(encoding='utf-8', newline='') as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 30
    assert {city: sum(row['city'] == city for row in rows) for city in ('Beijing', 'Shanghai', 'Guangzhou')} == {
        'Beijing': 10,
        'Shanghai': 10,
        'Guangzhou': 10,
    }
    assert {(row['published'], row['verified']) for row in rows} == {('false', 'false')}
