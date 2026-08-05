from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok(client):
    assert client.get('/health').json() == {'status': 'ok'}


def test_blank_query_returns_invalid_request(client):
    response = client.post('/v1/matches', json={'query': ' ', 'priority': 'overall'})

    assert response.status_code == 400
    assert response.json()['code'] == 'INVALID_REQUEST'
