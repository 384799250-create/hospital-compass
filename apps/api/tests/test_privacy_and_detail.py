import logging
from dataclasses import replace
from datetime import date, timedelta

from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.data import DEMO_HOSPITALS

AS_OF = date(2026, 8, 5)


@pytest.fixture(autouse=True)
def fixed_clock():
    main.app.dependency_overrides[main.current_date] = lambda: AS_OF
    yield
    main.app.dependency_overrides.clear()


def test_unpublished_hospital_detail_returns_not_found():
    client = TestClient(main.app)

    response = client.get('/v1/hospitals/demo-private')

    assert response.status_code == 404


def test_detail_uses_an_overrideable_clock_for_source_expiry():
    main.app.dependency_overrides[main.current_date] = lambda: date(2027, 1, 23)
    client = TestClient(main.app)

    try:
        response = client.get('/v1/hospitals/demo-1')
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.parametrize('record', [
    replace(DEMO_HOSPITALS[0], id='demo-unverified', verified=False),
    replace(DEMO_HOSPITALS[0], id='demo-missing-source', source_date=None),
    replace(DEMO_HOSPITALS[0], id='demo-stale-source', source_date=AS_OF - timedelta(days=181)),
])
def test_detail_returns_not_found_for_records_not_eligible_for_public_matching(monkeypatch, record):
    monkeypatch.setattr(main, 'DEMO_HOSPITALS', (record,))
    client = TestClient(main.app)

    response = client.get(f'/v1/hospitals/{record.id}')

    assert response.status_code == 404


def test_published_hospital_detail_contains_only_public_source_backed_fields():
    client = TestClient(main.app)

    response = client.get('/v1/hospitals/demo-1')

    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {'id', 'name', 'city', 'specialties', 'source'}
    assert detail['id'] == 'demo-1'
    assert set(detail['source']) == {'label', 'date'}
    assert detail['source']['label'] == 'DEMO DATA'


def test_symptom_query_is_not_written_to_request_logs(caplog):
    client = TestClient(main.app)
    symptom_query = 'sudden chest pain'

    with caplog.at_level(logging.INFO, logger='app.main'):
        response = client.post('/v1/matches', json={
            'query': symptom_query,
            'priority': 'overall',
        })

    assert response.status_code == 200
    assert 'request method=POST path=/v1/matches status=200 request_id=' in caplog.text
    assert symptom_query not in caplog.text
