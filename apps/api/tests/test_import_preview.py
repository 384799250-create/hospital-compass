from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_import_preview_returns_errors_without_publishing():
    response = client.post('/admin/import-preview', content='hospital_id,name,city\n')

    assert response.status_code == 200
    assert response.json()['accepted_count'] == 0
    assert response.json()['errors']


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


def test_import_preview_rejects_csv_larger_than_one_megabyte():
    response = client.post('/admin/import-preview', content='a' * (1024 * 1024 + 1))

    assert response.status_code == 400
