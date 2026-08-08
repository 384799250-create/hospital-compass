import pytest
from datetime import UTC, datetime
from pydantic import ValidationError

from app.schemas import RealtimeSearchRequest
from app.bocha_search import SearchDocument
from app.realtime_search import HospitalCandidate, candidate_from_document, parse_location, rank_candidates, scope_matches


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


def test_candidate_rejects_known_english_hospital_from_other_city():
    document = SearchDocument(
        title="Cardiology Dept.-Shenzhen Luohu People's Hospital",
        url='https://www.szlh.gov.cn/hospital/cardiology',
        snippet='Shenzhen hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert candidate is None


def test_candidate_rejects_english_department_title_without_hospital_entity():
    document = SearchDocument(
        title='Cardiovascular Medicine Ward 1-英文版',
        url='https://www.sz.gov.cn/hospital/cardiovascular-medicine',
        snippet='Cardiovascular medicine department information',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '深圳市', 'district': '南山区'},
    )

    assert candidate is None


def test_candidate_rejects_unmapped_english_hospital_name():
    document = SearchDocument(
        title='Fuwai Hospital',
        url='https://www.fuwai.com/en/cardiology',
        snippet='Cardiovascular medicine hospital',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '深圳市', 'district': '南山区'},
    )

    assert candidate is None


def test_local_scope_rejects_hospital_without_requested_city_evidence():
    document = SearchDocument(
        title='Cardiology - Xiangya Hospital Central South University',
        url='https://www.xiangya.com.cn/en/cardiology',
        snippet='Cardiology department and appointment information.',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        require_location_evidence=True,
    )

    assert candidate is None


def test_local_scope_keeps_hospital_with_requested_city_evidence():
    document = SearchDocument(
        title='Cardiology - Sun Yat-Sen Memorial Hospital',
        url='https://www.gzsys.org.cn/cardiology',
        snippet='Guangzhou hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        require_location_evidence=True,
    )

    assert candidate is not None


def test_local_scope_rejects_province_only_evidence():
    document = SearchDocument(
        title='Cardiology - Sun Yat-Sen Memorial Hospital',
        url='https://example.org/guangdong-cardiology-ranking',
        snippet='Guangdong province cardiovascular hospital ranking.',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        require_location_evidence=True,
    )

    assert candidate is None


def test_national_scope_does_not_require_city_evidence():
    document = SearchDocument(
        title='Cardiology - Xiangya Hospital Central South University',
        url='https://www.xiangya.com.cn/en/cardiology',
        snippet='Cardiology department and appointment information.',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert candidate is not None


def test_candidate_extracts_hospital_entity_from_search_snippet():
    document = SearchDocument(
        title='Guangzhou cardiology hospital ranking',
        url='https://example.org/guangzhou-cardiology',
        snippet='广东省人民医院 心血管内科全国第10 广东省 广州市',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        require_location_evidence=True,
    )

    assert candidate is not None
    assert candidate.name == '广东省人民医院'


def test_doctor_profile_is_not_used_as_hospital_evidence():
    document = SearchDocument(
        title='广州医科大学附属番禺中心医院 - 心血管内科 - 医生门诊时间',
        url='https://example.org/doctor',
        snippet='本站已通过实名认证，执业证审核通过，医生门诊信息。',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        require_location_evidence=True,
    )

    assert candidate is None


def test_major_public_hospital_outranks_generic_local_hospital():
    major = candidate_from_document(
        SearchDocument(
            title='广东省人民医院 心血管内科',
            url='https://example.org/gd人民医院',
            snippet='广东省人民医院是国家心血管区域医疗中心，广州市',
            fetched_at='2026-08-07T00:00:00Z',
        ),
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )
    local = candidate_from_document(
        SearchDocument(
            title='岭南医院 心血管内科',
            url='https://example.org/lingnan',
            snippet='广州市心血管内科医院',
            fetched_at='2026-08-07T00:00:00Z',
        ),
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
    )

    assert major is not None and local is not None
    ranked = rank_candidates(
        [local, major],
        directions=['心血管内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        scope='city',
    )

    assert ranked[0]['name'] == '广东省人民医院'
    assert ranked[0]['score'] > ranked[1]['score']
    assert ranked[0]['score_breakdown']['public_capability'] > ranked[1]['score_breakdown']['public_capability']
    assert ranked[0]['score_breakdown']['specialty'] > ranked[1]['score_breakdown']['specialty']


@pytest.mark.parametrize('hospital_name', ['\u5e7f\u4e1c\u7701\u4eba\u6c11\u533b\u9662', '\u6e56\u5357\u7701\u4eba\u6c11\u533b\u9662'])
def test_provincial_peoples_hospital_prior_is_generic(hospital_name):
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name=hospital_name, city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u8d8a\u79c0\u533a',
        public_capability=78.0,
        sources=[SearchDocument(
            title=hospital_name, url='https://hospital.example.org',
            snippet='\u4e09\u7ea7\u7532\u7b49 \u5fc3\u5185\u79d1', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        scope='city', as_of=fetched_at,
    )

    assert ranked[0]['score_breakdown']['public_capability'] == 92.0


def test_specialty_alias_matches_cardiovascular_and_cardiology_terms():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u5e7f\u4e1c\u7701\u4eba\u6c11\u533b\u9662', city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u8d8a\u79c0\u533a',
        specialties=('\u5fc3\u5185\u79d1',),
        sources=[SearchDocument(
            title='\u5e7f\u4e1c\u7701\u4eba\u6c11\u533b\u9662', url='https://hospital.example.org',
            snippet='\u4e09\u7ea7\u7532\u7b49', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        scope='city', as_of=fetched_at,
    )

    assert ranked[0]['score_breakdown']['specialty'] > 0


def test_rank_result_keeps_grounded_address_and_core_advantages_separate():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u5e7f\u4e1c\u7701\u4eba\u6c11\u533b\u9662', city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u8d8a\u79c0\u533a',
        address='\u5e7f\u4e1c\u7701\u5e7f\u5dde\u5e02\u4e2d\u5c71\u4e8c\u8def106\u53f7',
        core_advantages='\u4e09\u7ea7\u7532\u7b49\uff1b\u5fc3\u5185\u79d1',
        sources=[SearchDocument(
            title='\u5e7f\u4e1c\u7701\u4eba\u6c11\u533b\u9662', url='https://hospital.example.org',
            snippet='\u4e09\u7ea7\u7532\u7b49', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        scope='city', as_of=fetched_at,
    )

    assert ranked[0]['address'] == '\u5e7f\u4e1c\u7701\u5e7f\u5dde\u5e02\u4e2d\u5c71\u4e8c\u8def106\u53f7'
    assert ranked[0]['core_advantages'] == '\u4e09\u7ea7\u7532\u7b49\uff1b\u5fc3\u5185\u79d1'


def test_disease_profile_changes_specialty_evidence_without_changing_weights():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u5fc3\u8840\u7ba1\u4e2d\u5fc3', city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u8d8a\u79c0\u533a',
        specialties=('\u5fc3\u8840\u7ba1\u5185\u79d1',),
        sources=[SearchDocument(
            title='\u5fc3\u8840\u7ba1\u4e2d\u5fc3', url='https://hospital.example.org',
            snippet='\u5fc3\u8840\u7ba1\u91cd\u70b9\u4e13\u79d1 PCI', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        scope='city', profile_key='cardiovascular', as_of=fetched_at,
    )

    assert ranked[0]['score_breakdown']['specialty'] >= 90.0
    assert ranked[0]['score_breakdown']['public_capability'] >= 90.0


def test_wider_scope_reduces_geography_dimension_score():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u6d4b\u8bd5\u533b\u9662', city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u8d8a\u79c0\u533a',
        sources=[SearchDocument(
            title='\u6d4b\u8bd5\u533b\u9662', url='https://hospital.example.org',
            snippet='\u7efc\u5408\u533b\u9662', fetched_at=fetched_at,
        )],
    )
    location = {'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'}

    city = rank_candidates([candidate], directions=[], location=location, scope='city', as_of=fetched_at)
    national = rank_candidates([candidate], directions=[], location=location, scope='national', as_of=fetched_at)

    assert city[0]['score_breakdown']['geography'] > national[0]['score_breakdown']['geography']


def test_national_scope_keeps_out_of_province_candidate_with_lower_geography_score():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u5317\u4eac\u533b\u9662', city='\u5317\u4eac\u5e02', province='\u5317\u4eac\u5e02', district='\u897f\u57ce\u533a',
        sources=[SearchDocument(
            title='\u5317\u4eac\u533b\u9662', url='https://hospital.example.org',
            snippet='\u7efc\u5408\u533b\u9662', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=[],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        scope='national', as_of=fetched_at,
    )

    assert ranked[0]['score_breakdown']['geography'] == 60.0


def test_rank_result_exposes_authoritative_specialty_evidence_and_uses_its_score():
    candidate = HospitalCandidate(
        name='医院 A', city='广州市', province='广东省', district='天河区',
        specialties=('心血管内科',),
        ranking_evidence=({
            'hospital': '医院 A', 'city': '广州市', 'specialty': '心血管内科',
            'rank': 1, 'year': 2025, 'score': 100.0, 'source': 'https://example.org/ranking',
            'verification_status': '待核验',
        },),
        sources=[SearchDocument(title='医院 A', url='https://example.org/a', snippet='心血管内科', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates([candidate], directions=['心血管内科'], location={'province': '广东省', 'city': '广州市', 'district': '天河区'}, scope='district')
    assert ranked[0]['specialty_evidence'][0]['year'] == 2025
    assert 50.0 < ranked[0]['score_breakdown']['specialty'] < 100.0
