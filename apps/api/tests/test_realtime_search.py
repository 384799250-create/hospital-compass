import pytest
from pydantic import ValidationError

from app.schemas import RealtimeSearchRequest
from app.bocha_search import SearchDocument
from app.realtime_search import candidate_from_document, parse_location, scope_matches


def request(**overrides):
    payload = {
        'query': 'cardiology',
        'location': {
            'province': 'Guangdong',
            'city': 'Shenzhen',
            'district': 'Nanshan',
        },
        'ai_consent': True,
    }
    return RealtimeSearchRequest(**(payload | overrides))


def test_realtime_search_request_defaults_to_district_scope():
    assert request().scope == 'district'


@pytest.mark.parametrize('scope', ['district', 'city', 'province', 'national'])
def test_realtime_search_request_accepts_each_supported_scope(scope):
    assert request(scope=scope).scope == scope


@pytest.mark.parametrize(
    'location',
    [
        {'province': '', 'city': 'Shenzhen', 'district': 'Nanshan'},
        {'province': 'Guangdong', 'city': '', 'district': 'Nanshan'},
        {'province': 'Guangdong', 'city': 'Shenzhen', 'district': ''},
        {'province': 'x' * 41, 'city': 'Shenzhen', 'district': 'Nanshan'},
        {'province': 'Guangdong', 'city': 'x' * 41, 'district': 'Nanshan'},
        {'province': 'Guangdong', 'city': 'Shenzhen', 'district': 'x' * 41},
    ],
)
def test_realtime_search_request_rejects_blank_or_overlong_location_fields(location):
    with pytest.raises(ValidationError):
        request(location=location)


def test_parse_location_returns_exact_hierarchy():
    assert parse_location({
        'province': 'Guangdong',
        'city': 'Shenzhen',
        'district': 'Nanshan',
    }) == ('Guangdong', 'Shenzhen', 'Nanshan')


@pytest.mark.parametrize(
    ('scope', 'candidate', 'expected'),
    [
        ('district', ('Guangdong', 'Shenzhen', 'Nanshan'), True),
        ('district', ('Guangdong', 'Shenzhen', 'Futian'), False),
        ('city', ('Guangdong', 'Shenzhen', 'Futian'), True),
        ('city', ('Guangdong', 'Guangzhou', 'Tianhe'), False),
        ('province', ('Guangdong', 'Guangzhou', 'Tianhe'), True),
        ('province', ('Hunan', 'Changsha', 'Yuelu'), False),
        ('national', ('Hunan', 'Changsha', 'Yuelu'), True),
    ],
)
def test_scope_matches_enforces_exact_scope_boundary(scope, candidate, expected):
    request_location = parse_location({
        'province': 'Guangdong',
        'city': 'Shenzhen',
        'district': 'Nanshan',
    })

    assert scope_matches(candidate, request_location, scope) is expected


def test_candidate_accepts_english_city_evidence_from_scoped_search():
    document = SearchDocument(
        title='Cardiology - Sun Yat-Sen Memorial Hospital',
        url='https://www.gzsys.org.cn/cardiology',
        snippet='Guangzhou hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert candidate is not None


def test_candidate_rejects_non_hospital_english_search_page():
    document = SearchDocument(
        title='Cardiology research report in Guangzhou',
        url='https://example.org/report',
        snippet='A research paper about cardiovascular disease.',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert candidate is None


def test_candidate_extracts_hospital_entity_from_department_page_title():
    document = SearchDocument(
        title='Cardiology - 中山大学附属第三医院',
        url='https://www.zssy.com.cn/cardiology',
        snippet='Guangzhou hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert candidate is not None
    assert candidate.name == '中山大学附属第三医院'
