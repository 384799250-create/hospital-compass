import asyncio
import json
import logging
from datetime import date
from functools import partial

from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.ai_matcher import ai_match
from app.matcher import SPECIALTY_KEYWORDS


class FakeAIResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


@pytest.fixture
def client():
    main.app.dependency_overrides[main.current_date] = lambda: date(2026, 8, 6)
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


def test_health_returns_ok(client):
    assert client.get('/health').json() == {'status': 'ok'}


def test_blank_query_returns_invalid_request(client):
    response = client.post('/v1/matches', json={'query': ' ', 'priority': 'overall'})

    assert response.status_code == 400
    assert response.json()['code'] == 'INVALID_REQUEST'


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/v1/matches', {'query': 'eye pain'}),
        ('/v1/ai-matches', {'query': 'eye pain', 'ai_consent': True}),
    ],
)
def test_match_endpoints_reject_city_longer_than_pending_candidate_limit(client, path, payload):
    response = client.post(path, json={**payload, 'city': 'x' * 41})

    assert response.status_code == 400
    assert response.json() == {'code': 'INVALID_REQUEST'}


@pytest.mark.parametrize(
    ('path', 'payload'),
    [
        ('/v1/matches', {'query': 'eye pain'}),
        ('/v1/ai-matches', {'query': 'eye pain', 'ai_consent': True}),
    ],
)
def test_match_endpoints_allow_an_omitted_city(client, monkeypatch, path, payload):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)

    response = client.post(path, json=payload)

    assert response.status_code == 200


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
    assert payload['pending_candidates'] == []


def test_ai_match_returns_placeholders_for_ai_directions_with_a_max_length_city(client, monkeypatch):
    city = 'x' * 40
    direction = next(iter(SPECIALTY_KEYWORDS.values()))
    monkeypatch.setattr(main, 'PUBLIC_HOSPITALS', ())

    def transport(request, timeout):
        return FakeAIResponse({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': 'Specialty direction identified',
                        'directions': [direction],
                    }),
                },
            }],
        })

    monkeypatch.setattr(
        main,
        'ai_match',
        partial(ai_match, environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport),
    )

    response = client.post('/v1/ai-matches', json={
        'query': 'eye pain',
        'city': city,
        'priority': 'overall',
        'ai_consent': True,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload['ai']['used'] is True
    assert payload['results'] == []
    assert payload['pending_candidates'][0]['city'] == city
    assert payload['pending_candidates'][0]['direction'] == direction
    assert payload['pending_candidates'][0]['placeholder'] is True


@pytest.mark.parametrize('coerced_consent', ['true', 'false', '1', '0', 1, 0, 1.0, 0.0])
def test_ai_match_rejects_non_boolean_consent(client, monkeypatch, coerced_consent):
    def unexpected_transport(request, timeout):
        pytest.fail('non-boolean consent reached the external AI transport')

    monkeypatch.setattr(
        main,
        'ai_match',
        partial(
            ai_match,
            environ={'DEEPSEEK_API_KEY': 'must-not-be-sent'},
            transport=unexpected_transport,
        ),
    )

    response = client.post('/v1/ai-matches', json={
        'query': '眼睛疼',
        'city': 'Beijing',
        'priority': 'overall',
        'ai_consent': coerced_consent,
    })

    assert response.status_code == 400
    assert response.json() == {'code': 'INVALID_REQUEST'}


def test_ai_match_success_runs_transport_off_event_loop_and_keeps_secrets_out_of_logs(
    client,
    monkeypatch,
    caplog,
):
    symptom_query = 'private symptom token'
    api_key = 'private-deepseek-key'

    def transport(request, timeout):
        with pytest.raises(RuntimeError, match='no running event loop'):
            asyncio.get_running_loop()
        return FakeAIResponse({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': '建议眼科评估',
                        'directions': ['眼科'],
                    }, ensure_ascii=False),
                },
            }],
        })

    monkeypatch.setattr(
        main,
        'ai_match',
        partial(ai_match, environ={'DEEPSEEK_API_KEY': api_key}, transport=transport),
    )

    with caplog.at_level(logging.INFO, logger='app.main'):
        response = client.post('/v1/ai-matches', json={
            'query': symptom_query,
            'city': 'Beijing',
            'priority': 'overall',
            'ai_consent': True,
        })

    assert response.status_code == 200
    assert response.json()['ai'] == {
        'used': True,
        'summary': '建议眼科评估',
        'directions': ['眼科'],
        'fallback': False,
    }
    assert response.json()['pending_candidates'] == []
    assert [result['id'] for result in response.json()['results']] == ['beijing-tongren']
    assert symptom_query not in caplog.text
    assert api_key not in caplog.text


def test_ai_match_openapi_declares_ai_metadata_response(client):
    openapi = client.get('/openapi.json').json()

    response_schema = openapi['paths']['/v1/ai-matches']['post']['responses']['200'][
        'content'
    ]['application/json']['schema']
    assert response_schema == {'$ref': '#/components/schemas/AIMatchResponse'}

    schemas = openapi['components']['schemas']
    assert schemas['AIMatchResponse']['properties']['ai'] == {
        '$ref': '#/components/schemas/AIMetadata',
    }
    assert schemas['AIMatchResponse']['properties']['pending_candidates'] == {
        'items': {'$ref': '#/components/schemas/PendingCandidate'},
        'title': 'Pending Candidates',
        'type': 'array',
    }
    assert 'pending_candidates' in schemas['AIMatchResponse']['required']
    assert set(schemas['PendingCandidate']['properties']) == {
        'name',
        'city',
        'direction',
        'reason',
        'placeholder',
    }
    assert set(schemas['PendingCandidate']['required']) == {
        'name',
        'city',
        'direction',
        'reason',
    }
    assert set(schemas['AIMetadata']['properties']) == {
        'used',
        'summary',
        'directions',
        'fallback',
    }
    assert set(schemas['AIMetadata']['required']) == {
        'used',
        'summary',
        'directions',
        'fallback',
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
