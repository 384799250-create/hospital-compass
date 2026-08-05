import logging

from fastapi.testclient import TestClient

from app.main import app


def test_unpublished_hospital_detail_returns_not_found():
    client = TestClient(app)

    response = client.get('/v1/hospitals/demo-private')

    assert response.status_code == 404


def test_published_hospital_detail_contains_only_public_source_backed_fields():
    client = TestClient(app)

    response = client.get('/v1/hospitals/demo-1')

    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {'id', 'name', 'city', 'address', 'official_url', 'specialties', 'source'}
    assert detail['id'] == 'demo-1'
    assert set(detail['source']) == {'label', 'url', 'date'}
    assert detail['source']['label'] == 'DEMO DATA'


def test_symptom_query_is_not_written_to_request_logs(caplog):
    client = TestClient(app)
    symptom_query = 'sudden chest pain'

    with caplog.at_level(logging.INFO, logger='app.main'):
        response = client.post('/v1/matches', json={
            'query': symptom_query,
            'priority': 'overall',
        })

    assert response.status_code == 200
    assert symptom_query not in caplog.text
