from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_import_preview_returns_errors_without_publishing():
    response = client.post('/admin/import-preview', content='hospital_id,name,city\n')

    assert response.status_code == 400
    assert response.json()['accepted_count'] == 0
    assert {'row': 1, 'fields': ['hospital_id'], 'error': 'Unknown CSV header'} in response.json()['errors']


def test_import_preview_rejects_a_missing_documented_name_header():
    response = client.post(
        '/admin/import-preview',
        content='id,city,tier,source_url,source_date,specialties,disease_tags,verified,published\n',
    )

    assert response.status_code == 400
    assert response.json() == {
        'accepted_count': 0,
        'errors': [{'row': 1, 'fields': ['name'], 'error': 'Missing documented CSV header'}],
    }


def test_import_preview_rejects_unknown_csv_headers():
    response = client.post(
        '/admin/import-preview',
        content='id,name,city,tier,source_url,source_date,specialties,disease_tags,verified,published,unknown\n',
    )

    assert response.status_code == 400
    assert response.json() == {
        'accepted_count': 0,
        'errors': [{'row': 1, 'fields': ['unknown'], 'error': 'Unknown CSV header'}],
    }


def test_import_preview_returns_row_field_and_error_for_invalid_csv_row():
    response = client.post(
        '/admin/import-preview',
        content='id,name,city,tier,source_url,source_date,specialties,disease_tags,verified,published\n'
        'pilot-1,Draft Hospital,Wuhan,unknown,http://source.test,not-a-date,,,false,false\n',
    )

    assert response.status_code == 200
    assert response.json() == {
        'accepted_count': 0,
        'errors': [{
            'row': 2,
            'fields': ['city', 'tier', 'source_url', 'source_date', 'specialties', 'disease_tags', 'verified', 'published'],
            'error': 'Validation failed',
        }],
    }


def test_import_preview_rejects_a_blank_hospital_name():
    response = client.post(
        '/admin/import-preview',
        content='id,name,city,tier,source_url,source_date,specialties,disease_tags,verified,published\n'
        'pilot-1,,Beijing,tertiary,https://source.test/pilot-1,2026-08-01,cardiology,chest-pain,true,true\n',
    )

    assert response.status_code == 200
    assert response.json() == {
        'accepted_count': 0,
        'errors': [{'row': 2, 'fields': ['name'], 'error': 'Validation failed'}],
    }


def test_import_preview_rejects_csv_larger_than_one_megabyte():
    response = client.post('/admin/import-preview', content='a' * (1024 * 1024 + 1))

    assert response.status_code == 400
