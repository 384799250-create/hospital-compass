import asyncio
import json
import logging
from datetime import UTC, date, datetime
from functools import partial

from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.ai_matcher import ai_match
from app.bocha_search import SearchDocument, SearchResult
from app.matcher import SPECIALTY_KEYWORDS
from app.realtime_search import HospitalCandidate
from app.symptom_clarification import ClarificationUnavailableError


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


@pytest.fixture(autouse=True)
def reset_search_controls():
    main.REALTIME_SEARCH_CACHE._values.clear()
    main.REALTIME_SEARCH_BUDGET._calls.clear()


def test_health_returns_ok(client):
    assert client.get('/health').json() == {'status': 'ok'}


def test_clarification_endpoint_returns_503_when_ai_is_unavailable(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ClarificationUnavailableError()

    monkeypatch.setattr(main, 'clarify_symptoms', unavailable)
    response = client.post('/v1/symptom-clarification', json={
        'query': '不舒服', 'answers': [], 'ai_consent': True,
    })
    assert response.status_code == 503
    assert response.json()['detail'] == 'AI clarification is temporarily unavailable'


def test_directory_fallback_does_not_treat_pending_capability_as_specialty_strength(client, monkeypatch):
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': '待核验医院', 'province': '广东省', 'city': '广州市', 'district': '越秀区',
        'address': '广东省广州市越秀区甲路1号', 'tier': '三级甲等',
        'specialty_capabilities': [{
            'department': '心血管内科', 'diagnosis_scope': '相关疾病', 'strength_level': '待核验',
        }],
    }])
    candidates = main._directory_fallback_candidates(__import__('app.schemas', fromlist=['RealtimeSearchRequest']).RealtimeSearchRequest(
        query='冠心病', location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city', ai_consent=False,
    ))
    assert candidates[0].specialties == ()
    assert candidates[0].capability_evidence == ()


def test_directory_fallback_does_not_treat_generic_capability_scope_as_specialty_evidence(client, monkeypatch):
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': '通用医院', 'province': '广东省', 'city': '广州市', 'district': '越秀区',
        'address': '广东省广州市越秀区甲路1号', 'tier': '三级甲等',
        'specialty_capabilities': [{
            'department': '心血管内科', 'diagnosis_scope': '相关疾病的诊断与治疗', 'strength_level': '国家级重点',
        }],
    }])
    request = __import__('app.schemas', fromlist=['RealtimeSearchRequest']).RealtimeSearchRequest(
        query='冠心病', location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city', ai_consent=False,
    )
    candidates = main._directory_fallback_candidates(request)
    assert candidates[0].capability_evidence == ()


def _realtime_payload(**overrides):
    return {
        'query': 'cardiology',
        'location': {'province': 'Guangdong', 'city': 'Shenzhen', 'district': 'Nanshan'},
        'ai_consent': False,
        **overrides,
    }


def test_realtime_emergency_does_not_call_bocha_or_ai(client, monkeypatch):
    monkeypatch.setattr(main, 'AnySearchClient', lambda: pytest.fail('AnySearch must not run'))
    monkeypatch.setattr(main, 'ai_match', lambda *args, **kwargs: pytest.fail('AI must not run'))
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload(query='突发胸痛'))
    assert response.status_code == 200
    assert response.json()['status'] == 'EMERGENCY'
    assert response.json()['results'] == []


def test_realtime_without_consent_skips_ai_and_reports_unavailable(client, monkeypatch):
    monkeypatch.delenv('BOCHA_API_KEY', raising=False)
    monkeypatch.setattr(main, 'ai_match', lambda *args, **kwargs: pytest.fail('AI must not run'))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(False, []),
    })())
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    assert response.status_code == 200
    assert response.json()['status'] == 'SEARCH_UNAVAILABLE'


def test_realtime_filters_scope_caps_ten_and_orders_by_weight(client, monkeypatch):
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    documents = [
        SearchDocument(title=f'Hospital {index}', url=f'https://example.org/{index}',
                       snippet='public 三甲 cardiology', fetched_at=fetched_at)
        for index in range(11)
    ]
    documents.append(SearchDocument(title='Outside City', url='https://example.org/outside',
                                    snippet='public 三甲 cardiology', fetched_at=fetched_at))
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name=document.title,
        city='Guangzhou' if document.title == 'Outside City' else 'Shenzhen',
        province='Guangdong', district='Nanshan', sources=[document],
        specialties=('cardiology',),
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, documents),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{'canonical_name': document.title} for document in documents])
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'OK'
    assert len(payload['results']) == 10
    assert all(result['city'] == 'Shenzhen' for result in payload['results'])
    assert payload['results'][0]['score'] >= payload['results'][-1]['score']


def test_realtime_search_with_no_documents_reports_no_results(client, monkeypatch):
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, []),
    })())
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    assert response.status_code == 200
    assert response.json()['status'] == 'NO_RESULTS'


def test_realtime_search_rejects_non_tertiary_hospital_tier(client):
    response = client.post('/v1/realtime-hospital-search', json={**_realtime_payload(), 'hospital_tiers': ['secondary']})
    assert response.status_code == 400


def test_realtime_search_uses_bocha_only_when_anysearch_is_unavailable(client, monkeypatch):
    document = SearchDocument(
        title='Fallback Shenzhen Hospital', url='https://fallback.example.org',
        snippet='Shenzhen cardiology department', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    calls = {'bocha': 0}

    monkeypatch.setenv('BOCHA_API_KEY', 'test-bocha-key')
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(False, []),
    })())

    class FallbackClient:
        def search(self, query, count=10):
            calls['bocha'] += 1
            return SearchResult(True, [document])

    monkeypatch.setattr(main, 'BochaSearchClient', FallbackClient)
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{'canonical_name': document.title}])
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name=document.title, city='Shenzhen', province='Guangdong', district='Nanshan',
        sources=[document], specialties=('cardiology',),
    ))

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())

    assert response.status_code == 200
    assert response.json()['status'] == 'OK'
    assert calls['bocha'] == 2


def test_realtime_result_has_short_lived_detail_context(client, monkeypatch):
    document = SearchDocument(
        title='Shenzhen Heart Hospital', url='https://hospital.example.org',
        snippet='Cardiology department introduction', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Shenzhen Heart Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        sources=[document], specialties=('cardiology',),
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{'canonical_name': document.title}])
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    result_id = response.json()['results'][0]['id']
    detail = client.get(f'/v1/realtime-hospitals/{result_id}')
    assert detail.status_code == 200
    assert detail.json()['name'] == 'Shenzhen Heart Hospital'
    assert detail.json()['sources'][0]['url'] == 'https://hospital.example.org'


def test_realtime_detail_prefers_database_address_over_city_only_session(client, monkeypatch):
    document = SearchDocument(
        title='Database Address Hospital', url='https://hospital.example.org',
        snippet='Hospital information', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Database Address Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        address='Shenzhen', specialties=('cardiology',), sources=[document],
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': 'Database Address Hospital', 'city': 'Shenzhen', 'province': 'Guangdong',
        'district': 'Nanshan', 'address': 'Guangdong Shenzhen Nanshan Hospital Road 1',
        'tier': 'Tertiary A', 'specialty_capabilities': [],
    }])
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    result_id = response.json()['results'][0]['id']

    detail = client.get(f'/v1/realtime-hospitals/{result_id}')

    assert detail.status_code == 200
    assert detail.json()['address'] == 'Guangdong Shenzhen Nanshan Hospital Road 1'


def test_realtime_detail_prefers_database_introduction_over_search_snippet(client, monkeypatch):
    document = SearchDocument(
        title='Database Introduction Hospital', url='https://hospital.example.org',
        snippet='Search provider summary', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    database_introduction = 'Database verified hospital introduction.'
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Database Introduction Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        sources=[document], specialties=('cardiology',),
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': 'Database Introduction Hospital', 'city': 'Shenzhen', 'province': 'Guangdong',
        'district': 'Nanshan', 'address': 'Guangdong Shenzhen Nanshan Hospital Road 1',
        'tier': 'Tertiary A', 'introduction': database_introduction, 'specialty_capabilities': [],
    }])

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    result_id = response.json()['results'][0]['id']
    detail = client.get(f'/v1/realtime-hospitals/{result_id}')

    assert detail.status_code == 200
    assert detail.json()['introduction'] == database_introduction


def test_realtime_detail_exposes_verified_website_and_wechat_appointment_label(client, monkeypatch):
    document = SearchDocument(
        title='Website Detail Hospital', url='https://search.example.org',
        snippet='Search provider summary', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Website Detail Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        sources=[document], specialties=('cardiology',),
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': 'Website Detail Hospital', 'city': 'Shenzhen', 'province': 'Guangdong',
        'district': 'Nanshan', 'address': 'Hospital Road 1', 'official_domain': 'https://hospital.example.org',
        'introduction': 'Database introduction', 'tier': 'Tertiary A', 'specialty_capabilities': [],
    }])

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    result_id = response.json()['results'][0]['id']
    detail = client.get(f'/v1/realtime-hospitals/{result_id}')

    assert detail.status_code == 200
    assert detail.json()['official_website_url'] == 'https://hospital.example.org'
    assert detail.json()['wechat_appointment'] == 'Website Detail Hospital公众号'


def test_realtime_detail_rebuilds_after_in_memory_context_is_lost(client, monkeypatch):
    document = SearchDocument(
        title='Database Hospital', url='https://hospital.example.org',
        snippet='Guangzhou cardiology department', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Database Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        address='广东省深圳市南山区医院路1号', specialties=('心血管内科',), sources=[document],
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': 'Database Hospital', 'city': 'Shenzhen', 'province': 'Guangdong',
        'district': 'Nanshan', 'address': '广东省深圳市南山区医院路1号', 'tier': '三级甲等',
        'specialty_capabilities': [],
    }])
    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())
    result_id = response.json()['results'][0]['id']
    main.REALTIME_DETAIL_SESSIONS.clear()

    detail = client.get(f'/v1/realtime-hospitals/{result_id}')

    assert detail.status_code == 200
    assert detail.json()['name'] == 'Database Hospital'
    assert detail.json()['address'] == '广东省深圳市南山区医院路1号'


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


def test_realtime_search_runs_synthesis_off_event_loop(client, monkeypatch):
    import asyncio
    import app.main as main_module

    called = False

    def synthesis(**kwargs):
        nonlocal called
        called = True
        return kwargs['results']

    monkeypatch.setattr(main_module, 'synthesize_hospital_results', synthesis)
    monkeypatch.setattr(main_module, '_directory_fallback_candidates', lambda request: [])
    monkeypatch.setattr(main_module, '_cached_external_search', lambda *args, **kwargs: asyncio.sleep(0, result=None))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')

    response = client.post('/v1/realtime-hospital-search', json={
        'query': '胸痛',
        'location': {'province': '广东省', 'city': '广州市', 'district': '番禺区'},
        'scope': 'district',
        'ai_consent': True,
        'hospital_tiers': ['tertiary_a'],
    })

    assert response.status_code == 200
    assert called is True


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
