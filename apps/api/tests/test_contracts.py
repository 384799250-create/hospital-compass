from datetime import date

from fastapi.testclient import TestClient
import pytest

from app.main import app, current_date


@pytest.fixture
def client():
    app.dependency_overrides[current_date] = lambda: date(2026, 8, 6)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_returns_ok(client):
    assert client.get('/health').json() == {'status': 'ok'}


def test_blank_query_returns_invalid_request(client):
    response = client.post('/v1/matches', json={'query': ' ', 'priority': 'overall'})

    assert response.status_code == 400
    assert response.json()['code'] == 'INVALID_REQUEST'


def test_ai_match_without_api_key_falls_back_to_local_match(client, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)

    response = client.post('/v1/ai-matches', json={
        'query': '冠心病',
        'city': 'Beijing',
        'priority': 'overall',
        'ai_consent': True,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload['directions'] == ['心血管内科']
    assert [result['id'] for result in payload['results']] == ['beijing-pumch']
    assert payload['ai'] == {
        'used': False,
        'summary': None,
        'directions': [],
        'fallback': True,
    }


def test_verified_beijing_publish_list_is_the_only_public_api_dataset(client):
    response = client.post('/v1/matches', json={
        'query': '冠心病',
        'city': 'Beijing',
        'priority': 'overall',
    })

    assert response.status_code == 200
    assert response.json()['results'] == [{
        'id': 'beijing-pumch',
        'name': '北京协和医院',
        'city': 'Beijing',
        'demo_label': '已核验公开信息',
        'score': 10.0,
        'specialties': ['心血管内科'],
        'score_reasons': ['来源信息在有效期内'],
        'source_date': '2026-08-06',
    }]

    detail = client.get('/v1/hospitals/beijing-pumch')

    assert detail.status_code == 200
    assert detail.json()['id'] == 'beijing-pumch'


@pytest.mark.parametrize('query', ['眼睛疼', '鼻塞'])
def test_tongren_is_returned_for_its_verified_disease_tags(client, query):
    response = client.post('/v1/matches', json={
        'query': query,
        'city': 'Beijing',
        'priority': 'overall',
    })

    assert response.status_code == 200
    assert response.json()['results'] == [{
        'id': 'beijing-tongren',
        'name': '首都医科大学附属北京同仁医院',
        'city': 'Beijing',
        'demo_label': '已核验公开信息',
        'score': 10.0,
        'specialties': ['眼科', '耳鼻咽喉头颈外科'],
        'score_reasons': ['来源信息在有效期内'],
        'source_date': '2026-08-06',
    }]
