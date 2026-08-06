import csv
from datetime import date, timedelta
from pathlib import Path

from app.data import PILOT_DRAFT_CSV_PATH
from app.importer import load_verified_beijing_rows, validate_import
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
        'specialties': '心血管内科',
        'disease_tags': '冠心病',
        'verified': 'true',
        'published': 'true',
    }
    value.update(overrides)
    return value


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(row()))
        writer.writeheader()
        writer.writerows(rows)


def test_load_verified_beijing_rows_rejects_shanghai_row(tmp_path):
    path = tmp_path / 'publish.csv'
    write_rows(path, [row(city='Shanghai')])

    with pytest.raises(ValueError, match='Beijing'):
        load_verified_beijing_rows(path, date(2026, 8, 6))


def test_load_verified_beijing_rows_rejects_unpublished_row(tmp_path):
    path = tmp_path / 'publish.csv'
    write_rows(path, [row(published='false')])

    with pytest.raises(ValueError, match='published'):
        load_verified_beijing_rows(path, date(2026, 8, 6))


@pytest.mark.parametrize(('field', 'value'), [
    ('specialties', '|'),
    ('disease_tags', '|'),
    ('specialties', 'unknown-specialty'),
    ('disease_tags', 'unknown-disease'),
])
def test_load_verified_beijing_rows_rejects_invalid_publish_tokens(tmp_path, field, value):
    path = tmp_path / 'publish.csv'
    write_rows(path, [row(**{field: value})])

    with pytest.raises(ValueError, match=field):
        load_verified_beijing_rows(path, date(2026, 8, 6))


def test_load_verified_beijing_rows_rejects_empty_list(tmp_path):
    path = tmp_path / 'publish.csv'
    write_rows(path, [])

    with pytest.raises(ValueError, match='empty'):
        load_verified_beijing_rows(path, date(2026, 8, 6))


def test_load_verified_beijing_rows_rejects_row_with_surplus_column(tmp_path):
    path = tmp_path / 'publish.csv'
    path.write_text(
        ','.join(row()) + '\n' + ','.join(row().values()) + ',unexpected\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='exactly the required columns'):
        load_verified_beijing_rows(path, date(2026, 8, 6))


@pytest.mark.parametrize(('age_days', 'raises'), [(180, False), (181, True)])
def test_load_verified_beijing_rows_enforces_180_day_source_age(tmp_path, age_days, raises):
    path = tmp_path / 'publish.csv'
    today = date(2026, 8, 6)
    source_date = (today - timedelta(days=age_days)).isoformat()
    write_rows(path, [row(source_date=source_date)])

    if raises:
        with pytest.raises(ValueError, match='source_date'):
            load_verified_beijing_rows(path, today)
    else:
        assert load_verified_beijing_rows(path, today) == [row(source_date=source_date)]


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
            source_date='2026-02-06',
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
