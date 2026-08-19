import asyncio
import json
import logging
import sqlite3
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

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


def test_health_reports_loaded_hospital_data(client, monkeypatch):
    monkeypatch.setattr(main, 'tertiary_rows', lambda: [{}, {}])
    monkeypatch.setattr(main, 'tertiary_database_path', lambda: Path('F:/hospital-database/db/hospital_database.db'))

    assert client.get('/health').json() == {
        'status': 'ok',
        'hospital_data': {
            'loaded': True,
            'hospital_count': 2,
            'database_path': 'F:/hospital-database/db/hospital_database.db',
        },
    }


def test_health_reports_degraded_when_no_hospitals_are_loaded(client, monkeypatch):
    monkeypatch.setattr(main, 'tertiary_rows', lambda: [])
    monkeypatch.setattr(main, 'tertiary_database_path', lambda: Path('F:/hospital-compass-data/tertiary-a.sqlite3'))

    assert client.get('/health').json() == {
        'status': 'degraded',
        'hospital_data': {
            'loaded': False,
            'hospital_count': 0,
            'database_path': 'F:/hospital-compass-data/tertiary-a.sqlite3',
        },
    }


def test_hospital_directory_returns_comprehensive_ranked_page(client, monkeypatch):
    monkeypatch.setattr(main, '_build_directory_results', lambda: [
        {'id': 'h2', 'name': '乙医院', 'city': '上海市', 'score': 81.0, 'score_breakdown': {'hospital_strength': 81}},
        {'id': 'h1', 'name': '甲医院', 'city': '北京市', 'score': 94.0, 'score_breakdown': {'hospital_strength': 94}},
    ])

    response = client.get('/v1/hospital-directory?page=1&page_size=1')

    assert response.status_code == 200
    assert response.json() == {
        'status': 'OK',
        'page': 1,
        'page_size': 1,
        'total': 2,
        'fetched_at': None,
        'results': [
            {'id': 'h1', 'name': '甲医院', 'city': '北京市', 'score': 94.0, 'score_breakdown': {'hospital_strength': 94}},
        ],
    }


def test_hospital_directory_sort_key_uses_hospital_strength_only():
    results = [
        {'name': '综合总分更高但实力较低', 'score': 96.0, 'score_breakdown': {'public_capability': 82.0}},
        {'name': '医院实力更高', 'score': 88.0, 'score_breakdown': {'public_capability': 97.0}},
    ]

    ordered = sorted(results, key=main._directory_sort_key)

    assert [item['name'] for item in ordered] == ['医院实力更高', '综合总分更高但实力较低']


def test_ranking_enrichment_collects_evidence_from_duplicate_hospital_records(monkeypatch):
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='北海市中医医院', official_full_name='北海市中医医院', city='北海市',
        province='广西壮族自治区', district='海城区', address='广西北海市海城区新建路1号',
        sources=[SearchDocument(title='北海市中医医院', url='https://directory.example/current', snippet='', fetched_at=fetched_at)],
    )
    rows = [
        {
            'id': 'current', 'canonical_name': '北海市中医医院', 'official_full_name': '北海市中医医院',
            'city': '北海市', 'province': '广西壮族自治区', 'district': '海城区',
            'address': '广西北海市海城区新建路1号', 'official_domain': 'www.bhszyyy.com',
        },
        {
            'id': 'legacy', 'canonical_name': '北海市中医院', 'official_full_name': '北海市中医医院',
            'city': '北海市', 'province': '广西壮族自治区', 'district': '海城区',
            'address': '广西北海市海城区新建路1号', 'official_domain': 'www.bhszyyy.com',
        },
    ]
    monkeypatch.setattr(main, 'tertiary_rows', lambda: rows)
    monkeypatch.setattr(main, 'ranking_records_for_hospitals', lambda hospitals, *, path: {
        hospital: [{'hospital': hospital, 'city': '北海市', 'specialty': '', 'rank': 1}]
        for hospital in hospitals
    })
    monkeypatch.setattr(main, 'credential_records_for_hospitals', lambda hospital_ids, specialties, *, path: {
        hospital_id: [{
            'hospital_id': hospital_id, 'specialty': specialties[0], 'credential_name': f'{hospital_id}资质',
            'credential_level': '省级', 'evidence_url': 'https://example.org/evidence', 'issue_year': 2024,
        }]
        for hospital_id in hospital_ids
    })

    enriched = main._attach_ranking_evidence([candidate], ['儿科'])

    assert {item['hospital'] for item in enriched[0].ranking_evidence} == {'北海市中医医院', '北海市中医院'}
    assert {item['credential_name'] for item in enriched[0].capability_evidence} == {'current资质', 'legacy资质'}


def test_database_identity_enrichment_allows_external_alias_to_merge_with_local_candidate():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    local = HospitalCandidate(
        name='北海市中医医院', official_full_name='北海市中医医院', city='北海市',
        sources=[SearchDocument(title='北海市中医医院', url='https://directory.example/current', snippet='', fetched_at=fetched_at)],
    )
    external_alias = HospitalCandidate(
        name='北海市中医院', city='北海市',
        sources=[SearchDocument(title='北海市中医院', url='https://search.example/legacy', snippet='', fetched_at=fetched_at)],
    )
    database_rows = [{
        'canonical_name': '北海市中医院', 'official_full_name': '北海市中医医院', 'city': '北海市',
    }]

    external_with_identity = main._apply_database_identity([external_alias], database_rows)
    merged = main.merge_hospital_candidates([local, *external_with_identity])

    assert len(merged) == 1
    assert merged[0].name == '北海市中医医院'


def test_official_specialty_evidence_items_only_accept_registered_official_domains():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='合浦县人民医院', city='北海市',
        sources=[SearchDocument(
            title='医院简介 - 合浦县人民医院',
            url='https://hospital.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。',
            fetched_at=fetched_at,
        )],
    )
    rows = [{
        'id': 'H1', 'canonical_name': '合浦县人民医院', 'city': '北海市',
        'official_domain': 'hospital.example.org',
    }]

    items = main._official_specialty_evidence_items([candidate], ['神经内科'], rows)

    assert len(items) == 1
    assert items[0].hospital_id == 'H1'
    assert items[0].department == '神经内科'
    assert items[0].quoted_text == '神经内科为广西医疗卫生重点学科（县级）'
    third_party = HospitalCandidate(
        name='合浦县人民医院', city='北海市',
        sources=[SearchDocument(
            title='转载页面', url='https://third-party.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。', fetched_at=fetched_at,
        )],
    )
    assert main._official_specialty_evidence_items([third_party], ['神经内科'], rows) == []


def test_realtime_search_schedules_official_specialty_evidence_without_waiting(client, monkeypatch):
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    document = SearchDocument(
        title='医院简介 - 合浦县人民医院',
        url='https://hospital.example.org/about',
        snippet='神经内科为广西医疗卫生重点学科（县级）。',
        fetched_at=fetched_at,
    )
    row = {
        'id': 'H1', 'canonical_name': '合浦县人民医院', 'city': '北海市',
        'province': '广西壮族自治区', 'district': '合浦县',
        'address': '北海市合浦县定海路1号', 'tier': '三级甲等',
        'official_domain': 'hospital.example.org', 'specialty_capabilities': [],
    }
    scheduled = []
    monkeypatch.setattr(main, '_build_local_results', lambda *args: ([], []))
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [row])
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, **kwargs: HospitalCandidate(
        name='合浦县人民医院', city='北海市', province='广西壮族自治区', district='合浦县',
        address='北海市合浦县定海路1号', tier='三级甲等', sources=[document],
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(
        main,
        '_persist_official_specialty_evidence_safely',
        lambda items, path: scheduled.extend(items),
    )

    response = client.post('/v1/realtime-hospital-search', json={
        'query': '持续头痛',
        'location': {'province': '广西壮族自治区', 'city': '北海市', 'district': '合浦县'},
        'scope': 'district', 'confirmed_direction': '神经内科', 'ai_consent': False,
    })

    assert response.status_code == 200
    assert response.json()['status'] == 'OK'
    assert [(item.hospital_id, item.department) for item in scheduled] == [('H1', '神经内科')]


def test_official_specialty_persistence_failure_is_isolated(monkeypatch, tmp_path):
    item = main.OfficialSpecialtyEvidence(
        hospital_id='H1', department='神经内科', strength_level='县级重点学科',
        quoted_text='神经内科为县级重点学科', evidence_url='https://hospital.example.org/about',
        source_title='医院简介', fetched_at='2026-08-17T00:00:00+00:00',
    )
    monkeypatch.setattr(
        main,
        'persist_official_capabilities',
        lambda items, *, path: (_ for _ in ()).throw(sqlite3.Error('database busy')),
    )

    main._persist_official_specialty_evidence_safely([item], tmp_path / 'hospital.db')


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


def test_attach_ranking_evidence_batches_database_lookups(monkeypatch):
    rows = [
        {'id': 'H1', 'canonical_name': '医院甲', 'official_full_name': '医院甲', 'province': '广东省', 'city': '广州市', 'district': '越秀区', 'address': '甲路1号'},
        {'id': 'H2', 'canonical_name': '医院乙', 'official_full_name': '医院乙', 'province': '广东省', 'city': '广州市', 'district': '天河区', 'address': '乙路1号'},
    ]
    fetched_at = datetime(2026, 8, 18, tzinfo=UTC)
    candidates = [
        HospitalCandidate(name='医院甲', city='广州市', sources=[SearchDocument(title='医院甲', url='https://example.org/a', snippet='', fetched_at=fetched_at)]),
        HospitalCandidate(name='医院乙', city='广州市', sources=[SearchDocument(title='医院乙', url='https://example.org/b', snippet='', fetched_at=fetched_at)]),
    ]
    monkeypatch.setattr(main, 'tertiary_rows', lambda: rows)
    monkeypatch.setattr(main, 'ranking_records', lambda **kwargs: pytest.fail('must not query rankings per hospital'))
    monkeypatch.setattr(main, 'credential_records', lambda **kwargs: pytest.fail('must not query credentials per hospital'))
    monkeypatch.setattr(main, 'ranking_records_for_hospitals', lambda hospitals, *, path: {
        '医院甲': [{'hospital': '医院甲', 'city': '广州市', 'specialty': '神经内科', 'rank': 1, 'ranking_scope': '全国'}],
        '医院乙': [],
    }, raising=False)
    monkeypatch.setattr(main, 'credential_records_for_hospitals', lambda hospital_ids, specialties, *, path: {
        'H2': [{'specialty': '神经内科', 'credential_name': '国家临床重点专科', 'credential_level': '国家级'}],
    }, raising=False)

    enriched = main._attach_ranking_evidence(candidates, ['神经内科'])

    assert enriched[0].ranking_evidence[0]['rank'] == 1
    assert enriched[1].capability_evidence[0]['credential_name'] == '国家临床重点专科'


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


def test_realtime_keeps_local_results_before_network_supplements(client, monkeypatch):
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    local_row = {
        'canonical_name': 'Local Priority Hospital', 'province': 'Guangdong', 'city': 'Shenzhen',
        'district': 'Nanshan', 'address': 'Local Road 1', 'tier': 'Tertiary A',
        'official_domain': 'local-priority.example.org', 'specialty_capabilities': [],
    }
    external_rows = [{
        'canonical_name': f'External Hospital {index}', 'province': 'Guangdong', 'city': 'Shenzhen',
        'district': 'Nanshan', 'address': f'External Road {index}', 'tier': 'Tertiary A',
        'specialty_capabilities': [],
    } for index in range(10)]
    documents = [
        SearchDocument(
            title=row['canonical_name'], url=f"https://search.example.org/{index}",
            snippet='Shenzhen cardiology department', fetched_at=fetched_at,
        )
        for index, row in enumerate(external_rows)
    ]

    def rows(**kwargs):
        return [local_row] if kwargs else [local_row, *external_rows]

    monkeypatch.setattr(main, 'tertiary_rows', rows)
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, documents),
    })())
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name=document.title, city='Shenzhen', province='Guangdong', district='Nanshan',
        address='Network address', sources=[document], specialties=('cardiology',),
    ))

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())

    assert response.status_code == 200
    names = [result['name'] for result in response.json()['results']]
    assert names[0] == 'Local Priority Hospital'
    assert len(names) == 10
    assert names[1:] == [f'External Hospital {index}' for index in range(9)]


def test_local_priority_orders_final_results_by_current_score():
    local_results = [
        {'id': 'hepu', 'name': '合浦县人民医院'},
        {'id': 'beihai', 'name': '北海市中医院'},
    ]
    ranked_candidates = [
        {'id': 'hepu', 'name': '合浦县人民医院', 'score': 58.4263},
        {'id': 'beihai', 'name': '北海市中医院', 'score': 58.5},
        {'id': 'supplement', 'name': '补充医院', 'score': 51.0},
    ]

    results = main._prioritize_local_results(local_results, ranked_candidates)

    assert [result['id'] for result in results] == ['beihai', 'hepu', 'supplement']


def test_local_priority_truncates_after_sorting_supplements():
    local_results = [
        {'id': f'local-{index}', 'name': f'本地医院{index}', 'score': 80 - index}
        for index in range(10)
    ]
    ranked_candidates = [
        *local_results,
        {'id': 'supplement', 'name': '高分补充医院', 'score': 99.0},
    ]

    results = main._prioritize_local_results(local_results, ranked_candidates)

    assert len(results) == 10
    assert results[0]['id'] == 'supplement'


def test_realtime_does_not_search_network_when_local_results_fill_limit(client, monkeypatch):
    rows = [{
        'canonical_name': f'Local Hospital {index}', 'province': 'Guangdong', 'city': 'Shenzhen',
        'district': 'Nanshan', 'address': f'Local Road {index}', 'tier': 'Tertiary A',
        'specialty_capabilities': [],
    } for index in range(10)]
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: rows)
    monkeypatch.setattr(main, 'AnySearchClient', lambda: pytest.fail('Network search must not run'))

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())

    assert response.status_code == 200
    assert response.json()['search_mode'] == '本地资料'
    assert len(response.json()['results']) == 10


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


def test_realtime_result_prefers_verified_database_website_over_realtime_website(client, monkeypatch):
    document = SearchDocument(
        title='Verified Website Hospital', url='https://search.example.org',
        snippet='Search provider summary', fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    monkeypatch.setattr(main, 'candidate_from_document', lambda document, *, location, **kwargs: HospitalCandidate(
        name='Verified Website Hospital', city='Shenzhen', province='Guangdong', district='Nanshan',
        official_website_url='https://stale.example.org', sources=[document], specialties=('cardiology',),
    ))
    monkeypatch.setattr(main, 'AnySearchClient', lambda: type('Client', (), {
        'search': lambda self, query, count=10: SearchResult(True, [document]),
    })())
    monkeypatch.setattr(main, 'tertiary_rows', lambda **kwargs: [{
        'canonical_name': 'Verified Website Hospital', 'city': 'Shenzhen', 'province': 'Guangdong',
        'district': 'Nanshan', 'address': 'Hospital Road 1', 'official_domain': 'https://verified.example.org',
        'tier': 'Tertiary A', 'specialty_capabilities': [],
    }])
    monkeypatch.setattr(main, 'rank_candidates', lambda *args, **kwargs: [{
        'id': 'verified-website-hospital', 'name': 'Verified Website Hospital', 'city': 'Shenzhen',
        'province': 'Guangdong', 'district': 'Nanshan', 'tier': 'Tertiary A', 'score': 90.0,
        'score_reasons': [], 'score_breakdown': {}, 'sources': [document.model_dump(mode='json')],
        'source_urls': [str(document.url)], 'fetched_at': document.fetched_at,
        'registration_url': None, 'official_website_url': 'https://stale.example.org',
        'specialties': ['cardiology'], 'address': 'Hospital Road 1',
        'core_advantages': '', 'match_reason': '',
    }])

    response = client.post('/v1/realtime-hospital-search', json=_realtime_payload())

    assert response.status_code == 200
    assert response.json()['results'][0]['official_website_url'] == 'https://verified.example.org'


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
