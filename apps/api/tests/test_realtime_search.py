import pytest
from datetime import UTC, datetime
from pydantic import ValidationError

from app.schemas import RealtimeSearchRequest
from app.bocha_search import SearchDocument
from app.realtime_search import HospitalCandidate, _fallback_core_advantages, _geography_score, _official_service_score, _overall_ranking_score, _specialty_ranking_bonus, _specialty_strength_score, candidate_from_document, merge_hospital_candidates, normalize_hospital_name, normalize_result_specialty_score, parse_location, rank_candidates, scope_matches


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


def test_official_service_score_uses_official_website_presence():
    assert _official_service_score(None, None) == 60.0
    assert _official_service_score('https://hospital.example.org', None) == 100.0
    assert _official_service_score(None, 'https://guahao.com/example') == 100.0


def test_merge_hospital_candidates_uses_official_full_name_as_identity():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    candidates = [
        HospitalCandidate(
            name='北海市中医院', official_full_name='北海市中医医院', city='北海市',
            address='广西北海市海城区新建路1号',
            sources=[SearchDocument(title='北海市中医院', url='https://directory.example/old', snippet='', fetched_at=fetched_at)],
            ranking_evidence=({'rank': 1271, 'score': 42.0},),
        ),
        HospitalCandidate(
            name='北海市中医医院', official_full_name='北海市中医医院', city='北海市',
            address='广西北海市海城区新建路1号',
            sources=[SearchDocument(title='北海市中医医院', url='https://directory.example/current', snippet='', fetched_at=fetched_at)],
            ranking_evidence=({'rank': 1988, 'score': 70.0},),
        ),
    ]

    merged = merge_hospital_candidates(candidates)

    assert len(merged) == 1
    assert merged[0].name == '北海市中医医院'
    assert {item['score'] for item in merged[0].ranking_evidence} == {42.0, 70.0}


def test_general_ranking_score_preserves_order_after_rank_200_and_infers_national_scope():
    rank_580 = _overall_ranking_score({
        'rank': 580, 'ranking_scope': '综合', 'ranking_name': '全国三甲医院综合实力排名', 'ranking_max_rank': 2448,
    })
    rank_1988 = _overall_ranking_score({
        'rank': 1988, 'ranking_scope': '综合', 'ranking_name': '全国三甲医院综合实力排名', 'ranking_max_rank': 2448,
    })

    assert rank_580 > rank_1988
    assert rank_580 == 79.2
    assert rank_1988 == 64.7


def test_institutional_strength_prefers_the_best_verified_rank_from_the_displayed_list():
    candidate = HospitalCandidate(
        name='北海市中医医院', city='北海市', province='广西壮族自治区', district='海城区',
        ranking_evidence=(
            {
                'hospital': '北海市中医医院', 'specialty': '', 'rank': 1988,
                'ranking_max_rank': 2448, 'ranking_scope': '综合',
                'ranking_name': '全国三甲医院综合实力排名',
                'ranking_source_name': '2024年度全国三甲医院综合实力排名', 'verification_status': '已通过',
            },
            {
                'hospital': '北海市中医院', 'specialty': '', 'rank': 1271,
                'ranking_max_rank': 2448, 'ranking_scope': '综合',
                'ranking_name': '全国三甲医院综合实力排名',
                'ranking_source_name': '2024年度全国三甲医院综合实力排名', 'verification_status': '已通过',
            },
        ),
        sources=[SearchDocument(
            title='北海市中医医院', url='https://hospital.example.org', snippet='三级甲等',
            fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['呼吸内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'}, scope='city',
    )

    assert '第1271名' in ranked[0]['core_advantages']
    assert ranked[0]['specialty_evidence'][0]['rank'] == 1271
    assert ranked[0]['score_breakdown']['public_capability'] == 72.1


def test_rank_candidates_exposes_official_service_score_for_website_presence():
    fetched_at = datetime(2026, 8, 13, tzinfo=UTC)
    candidates = [
        HospitalCandidate(
            name='无官网医院', city='广州市', province='广东省', district='越秀区',
            sources=[SearchDocument(title='无官网医院', url='https://example.org/no-site', snippet='医院资料', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='有官网医院', city='广州市', province='广东省', district='越秀区',
            official_website_url='https://hospital.example.org',
            sources=[SearchDocument(title='有官网医院', url='https://example.org/has-site', snippet='医院资料', fetched_at=fetched_at)],
        ),
    ]

    ranked = rank_candidates(
        candidates,
        directions=[],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city',
        as_of=fetched_at,
    )
    by_name = {item['name']: item for item in ranked}

    assert by_name['无官网医院']['score_breakdown']['official_service'] == 60.0
    assert by_name['有官网医院']['score_breakdown']['official_service'] == 100.0


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


def test_district_scope_rejects_city_only_evidence():
    document = SearchDocument(
        title='Cardiology - Sun Yat-Sen Memorial Hospital',
        url='https://www.gzsys.org.cn/cardiology',
        snippet='Guangzhou hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        require_location_evidence=True,
        require_district_evidence=True,
    )

    assert candidate is None


def test_district_scope_keeps_explicit_district_evidence():
    document = SearchDocument(
        title='\u756a\u79ba\u533a\u5fc3\u8840\u7ba1\u533b\u9662',
        url='https://example.org/panyu-cardiology',
        snippet='\u756a\u79ba\u533a \u5e7f\u5dde\u5e02 hospital cardiology department',
        fetched_at='2026-08-07T00:00:00Z',
    )

    candidate = candidate_from_document(
        document,
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        require_location_evidence=True,
        require_district_evidence=True,
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
def test_structured_capability_takes_precedence_over_provincial_peoples_hospital_name_prior(hospital_name):
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

    assert ranked[0]['score_breakdown']['public_capability'] == 78.0


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

    assert ranked[0]['score_breakdown']['specialty'] == 57.2


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


def test_rank_result_builds_natural_advantages_without_appending_public_introduction():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='\u5e7f\u4e1c\u7701\u5987\u5e7c\u4fdd\u5065\u9662', city='\u5e7f\u5dde\u5e02', tier='\u4e09\u7ea7\u7532\u7b49',
        public_introduction='\u4e3a\u5987\u5973\u548c\u513f\u7ae5\u63d0\u4f9b\u5168\u5468\u671f\u533b\u7597\u4fdd\u5065\u670d\u52a1\u3002',
        capability_evidence=({
            'department': '\u5987\u4ea7\u79d1',
            'strength_level': '\u91cd\u70b9\u4e13\u79d1',
        },),
        sources=[SearchDocument(
            title='\u5e7f\u4e1c\u7701\u5987\u5e7c\u4fdd\u5065\u9662', url='https://hospital.example.org',
            snippet='\u4e09\u7ea7\u7532\u7b49', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5987\u4ea7\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        scope='city', as_of=fetched_at,
    )

    advantages = ranked[0]['core_advantages']
    assert '\u516c\u5f00\u7b80\u4ecb\uff1a' not in advantages
    assert candidate.public_introduction not in advantages
    assert '\u5987\u4ea7\u79d1' in advantages
    assert '\u4e09\u7ea7\u7532\u7b49' in advantages
    assert ranked[0]['database_evidence']['public_introduction'] == '\u4e3a\u5987\u5973\u548c\u513f\u7ae5\u63d0\u4f9b\u5168\u5468\u671f\u533b\u7597\u4fdd\u5065\u670d\u52a1\u3002'


def test_rank_result_states_missing_specialty_evidence_without_copying_long_public_introduction():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    introduction = '\u8be5\u9662\u4e3a\u5f53\u5730\u5c45\u6c11\u63d0\u4f9b\u9884\u9632\u3001\u4fdd\u5065\u3001\u5eb7\u590d\u548c\u5065\u5eb7\u7ba1\u7406\u7b49\u7efc\u5408\u670d\u52a1\uff0c\u59cb\u7ec8\u575a\u6301\u4ee5\u4eba\u4e3a\u672c\u3001\u8ffd\u6c42\u4e00\u6d41\u533b\u7597\u670d\u52a1\u7684\u613f\u666f\u3002'
    candidate = HospitalCandidate(
        name='\u6d4b\u8bd5\u533b\u9662', city='\u5e7f\u5dde\u5e02', tier='\u4e09\u7ea7\u7532\u7b49',
        public_introduction=introduction,
        sources=[SearchDocument(
            title='\u6d4b\u8bd5\u533b\u9662', url='https://hospital.example.org',
            snippet='\u7efc\u5408\u533b\u7597\u670d\u52a1', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        scope='city', as_of=fetched_at,
    )

    advantages = ranked[0]['core_advantages']
    assert advantages.endswith('\u5f53\u524d\u516c\u5f00\u4fe1\u606f\u4e2d\u672a\u89c1\u4e0e\u5fc3\u8840\u7ba1\u5185\u79d1\u65b9\u5411\u76f4\u63a5\u5bf9\u5e94\u7684\u4e13\u79d1\u6392\u540d\uff0c\u5efa\u8bae\u7ed3\u5408\u5fc3\u8840\u7ba1\u5185\u79d1\u95e8\u8bca\u5b89\u6392\u8fdb\u4e00\u6b65\u786e\u8ba4\u3002')
    assert not advantages.startswith('\u5f53\u524d\u516c\u5f00')
    assert '\u4e09\u7ea7\u7532\u7b49' in advantages
    assert introduction not in advantages


def test_fallback_core_advantages_removes_promotional_profile_phrasing():
    candidate = HospitalCandidate(
        name='广东省妇幼保健院',
        city='广州市',
        tier='三级甲等',
        hospital_type='妇幼保健院',
        public_introduction='该院为三级甲等妇幼保健院，位于番禺区，是广州妇女儿童医疗保健的重要机构，可为儿童提供全面健康服务。',
        sources=[SearchDocument(
            title='广东省妇幼保健院公开资料',
            url='https://example.org/women-children',
            snippet='妇女和儿童医疗保健服务',
            fetched_at=datetime.now(UTC),
        )],
    )

    advantages = _fallback_core_advantages(candidate, ['儿科'], candidate.sources[0])

    assert '妇女和儿童相关医疗保健服务' in advantages
    assert '重要机构' not in advantages
    assert '全面健康服务' not in advantages


def test_rank_result_uses_each_hospitals_own_source_for_core_advantages():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    first = HospitalCandidate(
        name='医院甲', city='广州市', address='广东省广州市越秀区甲路1号',
        sources=[SearchDocument(title='医院甲', url='https://example.org/a', snippet='甲路1号', fetched_at=fetched_at)],
    )
    second = HospitalCandidate(
        name='医院乙', city='广州市', address='广东省广州市天河区乙路2号',
        sources=[SearchDocument(title='医院乙', url='https://example.org/b', snippet='乙路2号', fetched_at=fetched_at)],
    )
    ranked = rank_candidates(
        [first, second], directions=[],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city', as_of=fetched_at,
    )
    by_name = {item['name']: item for item in ranked}
    assert by_name['医院甲']['address'] == '广东省广州市越秀区甲路1号'
    assert by_name['医院乙']['address'] == '广东省广州市天河区乙路2号'
    assert '乙路2号' not in by_name['医院甲']['core_advantages']
    assert '甲路1号' not in by_name['医院乙']['core_advantages']


def test_hospital_name_normalization_handles_common_campus_suffixes():
    assert normalize_hospital_name('广东省人民医院（总院）') == '广东省人民医院'
    assert normalize_hospital_name('广东省人民医院 院本部') == '广东省人民医院'


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

    assert ranked[0]['score_breakdown']['specialty'] == 57.2
    assert ranked[0]['score_breakdown']['public_capability'] >= 90.0


def test_national_scope_preserves_same_district_geography_score():
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

    assert city[0]['score_breakdown']['geography'] == 100.0
    assert national[0]['score_breakdown']['geography'] == 100.0


def test_province_scope_gives_same_city_hospital_full_geography_score():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    same_city = HospitalCandidate(
        name='同市医院', city='广州市', province='广东省', district='越秀区',
        sources=[SearchDocument(title='同市医院', url='https://hospital.example.org/a', snippet='综合医院', fetched_at=fetched_at)],
    )
    other_city = HospitalCandidate(
        name='同省医院', city='深圳市', province='广东省', district='福田区',
        sources=[SearchDocument(title='同省医院', url='https://hospital.example.org/b', snippet='综合医院', fetched_at=fetched_at)],
    )
    location = {'province': '广东省', 'city': '广州市', 'district': '越秀区'}

    ranked = rank_candidates([same_city, other_city], directions=[], location=location, scope='province', as_of=fetched_at)

    scores = {item['name']: item['score_breakdown']['geography'] for item in ranked}
    assert scores['同市医院'] == 100.0
    assert scores['同省医院'] == 70.0


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

    assert 0.0 < ranked[0]['score_breakdown']['geography'] < 60.0


def test_ignore_geography_ranks_by_non_geographic_score_before_limiting_results():
    fetched_at = datetime(2026, 8, 1, tzinfo=UTC)
    location = {'province': '广西壮族自治区', 'city': '北海市', 'district': '合浦县'}
    nearby = HospitalCandidate(
        name='邻近医院',
        province='海南省',
        city='三亚市',
        district='海棠区',
        public_capability=95,
        ranking_evidence=({'specialty': '神经内科', 'rank': 8, 'score': 79.0, 'ranking_scope': '全国'},),
        sources=[SearchDocument(title='邻近医院', url='https://near.example', snippet='三级甲等', fetched_at=fetched_at)],
    )
    stronger_remote = HospitalCandidate(
        name='北京协和医院',
        province='北京市',
        city='北京市',
        district='东城区',
        public_capability=100,
        ranking_evidence=({'specialty': '神经内科', 'rank': 1, 'score': 100.0, 'ranking_scope': '全国'},),
        sources=[SearchDocument(title='北京协和医院', url='https://pumch.example', snippet='三级甲等', fetched_at=fetched_at)],
    )

    ranked = rank_candidates(
        [nearby, stronger_remote],
        directions=['神经内科'],
        location=location,
        scope='national',
        ignore_geography=True,
    )

    assert [item['name'] for item in ranked] == ['北京协和医院', '邻近医院']
    assert all(item['score_breakdown']['geography'] == 100.0 for item in ranked)


def test_national_scope_uses_location_proximity_tiers():
    fetched_at = datetime(2026, 8, 6, tzinfo=UTC)
    candidates = [
        HospitalCandidate(
            name='同区医院', city='广州市', province='广东省', district='越秀区',
            sources=[SearchDocument(title='同区', url='https://hospital.example.org/district', snippet='综合医院', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='同市医院', city='广州市', province='广东省', district='番禺区',
            sources=[SearchDocument(title='同市', url='https://hospital.example.org/city', snippet='综合医院', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='同省医院', city='深圳市', province='广东省', district='南山区',
            sources=[SearchDocument(title='同省', url='https://hospital.example.org/province', snippet='综合医院', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='外省医院', city='北京市', province='北京市', district='西城区',
            sources=[SearchDocument(title='外省', url='https://hospital.example.org/national', snippet='综合医院', fetched_at=fetched_at)],
        ),
    ]

    ranked = rank_candidates(
        candidates, directions=[],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='national', as_of=fetched_at,
    )

    scores = {item['name']: item['score_breakdown']['geography'] for item in ranked}
    assert scores['同区医院'] == 100.0
    assert scores['同市医院'] == 85.0
    assert scores['同省医院'] == 70.0
    assert 0.0 < scores['外省医院'] < 60.0


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


def test_specialty_score_uses_the_stronger_of_ranking_and_credential_contributions():
    fetched_at = datetime(2026, 8, 18, tzinfo=UTC)
    candidates = [
        HospitalCandidate(
            name='全国第一名医院', city='北京市', public_capability=50.0,
            ranking_evidence=({'specialty': '神经内科', 'rank': 1, 'score': 100.0, 'ranking_scope': '全国'},),
            sources=[SearchDocument(title='全国第一名医院', url='https://example.org/first', snippet='神经内科', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='全国第二名医院', city='北京市', public_capability=100.0,
            ranking_evidence=({'specialty': '神经内科', 'rank': 2, 'score': 97.0, 'ranking_scope': '全国'},),
            capability_evidence=({'department': '神经内科', 'strength_level': '国家级', 'diagnosis_scope': '国家临床重点专科'},),
            sources=[SearchDocument(title='全国第二名医院', url='https://example.org/second', snippet='神经内科', fetched_at=fetched_at)],
        ),
        HospitalCandidate(
            name='全国第十五名医院', city='北京市', public_capability=100.0,
            ranking_evidence=({'specialty': '神经内科', 'rank': 15, 'score': 58.0, 'ranking_scope': '全国'},),
            capability_evidence=({'department': '神经内科', 'strength_level': '国家级', 'diagnosis_scope': '国家临床重点专科'},),
            sources=[SearchDocument(title='全国第十五名医院', url='https://example.org/fifteenth', snippet='神经内科', fetched_at=fetched_at)],
        ),
    ]

    ranked = rank_candidates(
        candidates, directions=['神经内科'],
        location={'province': '北京市', 'city': '北京市', 'district': '东城区'}, scope='national', as_of=fetched_at,
    )

    specialty = {item['name']: item['score_breakdown']['specialty'] for item in ranked}
    assert specialty['全国第一名医院'] == 70.0
    assert specialty['全国第二名医院'] == 99.3684
    assert specialty['全国第十五名医院'] == 91.1579


def test_specialty_ranking_scope_weights_are_ordered_by_geographic_level():
    candidates = []
    for label in ('\u5168\u56fd\u4e13\u79d1\u58f0\u8a89\u6392\u540d', '\u7701\u7ea7\u4e13\u79d1\u6392\u540d', '\u5e02\u7ea7\u4e13\u79d1\u6392\u540d', '\u533a\u7ea7\u4e13\u79d1\u6392\u540d'):
        candidates.append(HospitalCandidate(
            name=label, city='\u5e7f\u5dde\u5e02', province='\u5e7f\u4e1c\u7701', district='\u756a\u79ba\u533a',
            ranking_evidence=({
                'specialty': '\u5fc3\u8840\u7ba1\u5185\u79d1', 'rank': 1, 'score': 100.0,
                'ranking_scope': label,
            },),
            sources=[SearchDocument(title=label, url=f'https://example.org/{len(candidates)}', snippet='\u5fc3\u8840\u7ba1\u5185\u79d1', fetched_at=datetime.now(UTC))],
        ))

    ranked = rank_candidates(
        candidates, directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'],
        location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        scope='district',
    )

    scores = {item['name']: item['score_breakdown']['specialty'] for item in ranked}
    assert scores['\u5168\u56fd\u4e13\u79d1\u58f0\u8a89\u6392\u540d'] > scores['\u7701\u7ea7\u4e13\u79d1\u6392\u540d'] > scores['\u5e02\u7ea7\u4e13\u79d1\u6392\u540d'] > scores['\u533a\u7ea7\u4e13\u79d1\u6392\u540d']
def test_rank_result_builds_natural_language_fallback_explanations():
    candidate = HospitalCandidate(
        name='测试三甲医院', city='广州市', province='广东省', district='越秀区',
        tier='三级甲等', specialties=('心内科',),
        sources=[SearchDocument(title='医院公开资料', url='https://example.org', snippet='心血管专科实力突出', fetched_at=datetime(2026, 8, 6, tzinfo=UTC))],
    )
    ranked = rank_candidates([candidate], directions=['心内科'], location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='district')
    assert ranked[0]['core_advantages'].startswith('公开资料显示，该院开设心内科相关诊疗服务。')
    assert ranked[0]['match_reason'].startswith('用户描述与心内科相关')


def test_fallback_core_advantages_names_ranking_source_for_users():
    candidate = HospitalCandidate(
        name='中山大学附属第一医院',
        city='广州市',
        tier='三级甲等',
        ranking_evidence=({
            'specialty': '儿科',
            'rank': 15,
            'year': 2024,
            'ranking_scope': '大区级',
            'ranking_name': '儿科',
            'ranking_source_name': '2024年度华南地区中医儿科专科声誉排行榜',
            'ranking_publisher': '复旦大学医院管理研究所',
        },),
        sources=[SearchDocument(
            title='医院资料',
            url='https://example.org',
            snippet='儿科相关资料',
            fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
        )],
    )

    advantages = _fallback_core_advantages(candidate, ['儿科或全科'], candidate.sources[0])

    assert '《2024年度华南地区中医儿科专科声誉排行榜》' in advantages
    assert '复旦大学医院管理研究所' in advantages
    assert '第15名' in advantages
    assert '数据库' not in advantages


def test_fallback_core_advantages_names_general_ranking_source_for_users():
    candidate = HospitalCandidate(
        name='广东省妇幼保健院',
        city='广州市',
        tier='三级甲等',
        ranking_evidence=(
            {
                'specialty': '',
                'rank': 1552,
                'year': 2024,
                'ranking_scope': '综合',
                'ranking_name': '全国',
                'ranking_source_name': '2024年度全国三甲医院综合实力排名',
            },
        ),
        sources=[SearchDocument(
            title='医院资料',
            url='https://example.org',
            snippet='综合排名资料',
            fetched_at=datetime.now(UTC),
        )],
    )

    advantages = _fallback_core_advantages(candidate, ['儿科'], candidate.sources[0])

    assert '《2024年度全国三甲医院综合实力排名》' in advantages
    assert '综合全国' not in advantages


def test_rank_result_deduplicates_identical_ranking_evidence():
    candidate = HospitalCandidate(
        name='广东省妇幼保健院', city='广州市', tier='三级甲等',
        ranking_evidence=(
            {'specialty': '', 'rank': 1552, 'year': 2024, 'ranking_source_name': '2024年度全国三甲医院综合实力排名'},
            {'specialty': '', 'rank': 1552, 'year': 2024, 'ranking_source_name': '2024年度全国三甲医院综合实力排名'},
        ),
        sources=[SearchDocument(
            title='医院资料', url='https://example.org', snippet='综合排名资料', fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['儿科'],
        location={'province': '广东省', 'city': '广州市', 'district': '番禺区'},
        scope='city',
    )

    assert len(ranked[0]['specialty_evidence']) == 1


def test_rank_result_only_exposes_current_direction_evidence_before_general_rankings():
    candidate = HospitalCandidate(
        name='中山大学附属第一医院', city='广州市', tier='三级甲等',
        capability_evidence=(
            {'department': '心血管内科', 'diagnosis_scope': '心内科相关诊疗'},
        ),
        ranking_evidence=(
            {'specialty': '', 'rank': 9, 'year': 2024, 'ranking_source_name': '2024全国医院互联网口碑排行榜'},
            {'specialty': '儿科', 'rank': 15, 'year': 2024, 'ranking_source_name': '2024年度华南地区中医儿科专科声誉排行榜'},
            {'specialty': '新生儿科', 'rank': 15, 'year': 2024, 'ranking_source_name': '2024年度华南地区新生儿科专科声誉排行榜'},
        ),
        sources=[SearchDocument(
            title='医院资料', url='https://example.org', snippet='儿科相关资料', fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['儿科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city',
    )

    evidence = ranked[0]['specialty_evidence']
    assert all(item.get('department') != '心血管内科' for item in evidence)
    assert [item.get('specialty') for item in evidence[:2]] == ['儿科', '新生儿科']


def test_rank_result_exposes_source_backed_capability_before_general_ranking():
    candidate = HospitalCandidate(
        name='合浦县人民医院', city='北海市', tier='三级甲等',
        ranking_evidence=({
            'specialty': '', 'rank': 765, 'year': 2024,
            'ranking_source_name': '2024年度全国三甲医院综合实力排名',
        },),
        sources=[SearchDocument(
            title='医院简介 - 合浦县人民医院',
            url='https://hospital.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。北海市重点（建设）学科为神经内科。',
            fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '合浦县'},
        scope='district',
    )

    evidence = ranked[0]['specialty_evidence']
    assert evidence[0] == {
        'department': '神经内科',
        'diagnosis_scope': '神经内科为广西医疗卫生重点学科（县级）',
        'strength_level': '广西医疗卫生重点学科（县级）',
        'source': 'https://hospital.example.org/about',
        'ranking_source_name': '医院简介 - 合浦县人民医院',
        'verification_status': '公开资料',
    }
    assert evidence[-1]['rank'] == 765
    assert ranked[0]['has_direct_specialty_evidence'] is True


def test_county_specialty_evidence_is_a_limited_bonus_on_institutional_strength():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    county = HospitalCandidate(
        name='县级医院', city='北海市', province='广西壮族自治区', district='海城区',
        public_capability=77.3,
        sources=[SearchDocument(
            title='县级医院简介', url='https://county.example.org/about',
            snippet='神经内科为广西医疗卫生重点学科（县级）。', fetched_at=fetched_at,
        )],
    )
    flagship = HospitalCandidate(
        name='综合实力医院', city='北海市', province='广西壮族自治区', district='海城区',
        public_capability=97.0,
        sources=[SearchDocument(
            title='综合实力医院简介', url='https://flagship.example.org/about',
            snippet='三级甲等综合医院。', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [county, flagship], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'},
        scope='province', as_of=fetched_at,
    )

    specialty = {item['name']: item['score_breakdown']['specialty'] for item in ranked}
    assert specialty['县级医院'] == 54.38
    assert specialty['综合实力医院'] == 58.2
    assert ranked[0]['name'] == '综合实力医院'


def test_persisted_official_capability_is_reused_in_province_scope():
    fetched_at = datetime(2026, 8, 17, tzinfo=UTC)
    candidate = HospitalCandidate(
        name='合浦县人民医院', city='北海市', province='广西壮族自治区', district='合浦县',
        public_capability=77.3,
        capability_evidence=({
            'department': '神经内科',
            'diagnosis_scope': '神经内科为广西医疗卫生重点学科（县级）',
            'strength_level': '广西医疗卫生重点学科（县级）',
            'evidence_summary': '神经内科为广西医疗卫生重点学科（县级）',
            'evidence_url': 'https://hospital.example.org/about',
            'verification_status': '官网自动核验',
        },),
        sources=[SearchDocument(
            title='本地医院资料', url='https://directory.example.org/hospital',
            snippet='三级甲等医院', fetched_at=fetched_at,
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '合浦县'},
        scope='province', as_of=fetched_at,
    )

    assert ranked[0]['score_breakdown']['specialty'] == 54.38
    assert ranked[0]['specialty_evidence'][0]['verification_status'] == '官网自动核验'
    assert ranked[0]['specialty_evidence'][0]['evidence_url'] == 'https://hospital.example.org/about'


@pytest.mark.parametrize(('snippet', 'expected'), [
    ('神经内科为县级重点学科。', 54.38),
    ('神经内科为北海市重点学科。', 58.38),
    ('神经内科为广西省级重点专科。', 64.38),
    ('神经内科为国家临床重点专科。', 71.38),
])
def test_specialty_bonus_uses_the_explicit_evidence_level(snippet, expected):
    candidate = HospitalCandidate(
        name='分级医院', city='北海市', public_capability=77.3,
        sources=[SearchDocument(
            title='神经内科简介', url='https://example.org/about', snippet=snippet,
            fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'},
        scope='city', as_of=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert ranked[0]['score_breakdown']['specialty'] == expected


def test_multiple_specialty_evidence_records_use_only_the_highest_bonus():
    candidate = HospitalCandidate(
        name='多证据医院', city='北海市', public_capability=77.3,
        sources=[SearchDocument(
            title='医院简介', url='https://example.org/about',
            snippet='神经内科为县级重点学科；神经内科为北海市重点学科。',
            fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广西壮族自治区', 'city': '北海市', 'district': '海城区'},
        scope='city', as_of=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert ranked[0]['score_breakdown']['specialty'] == 58.38


def test_specialty_score_uses_institutional_baseline_without_direct_evidence():
    candidate = HospitalCandidate(
        name='综合医院', city='广州市', public_capability=72.1,
        sources=[SearchDocument(
            title='综合医院简介', url='https://hospital.example.org', snippet='三级甲等综合医院。',
            fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['specialty'] == 43.26


def test_fallback_core_advantages_explains_type_credentials_and_service_positioning():
    candidate = HospitalCandidate(
        name='广东祈福医院',
        city='广州市',
        tier='三级甲等',
        hospital_type='中西医结合医院',
        public_introduction='通过国际 JCI 认证、CIHA 国际认证，集医疗、科研、教学、预防保健于一体。',
        sources=[SearchDocument(
            title='广东祈福医院公开资料',
            url='https://example.org/clifford',
            snippet='医院公开资料',
            fetched_at=datetime.now(UTC),
        )],
    )

    advantages = _fallback_core_advantages(candidate, ['儿科'], candidate.sources[0])

    assert '三级甲等中西医结合医院' in advantages
    assert 'JCI' in advantages and 'CIHA' in advantages
    assert '医疗、科研、教学、预防保健' in advantages
    assert advantages.endswith('当前公开信息中未见与儿科方向直接对应的专科排名，建议结合儿科门诊安排进一步确认。')
    assert '公开简介：' not in advantages


def test_fallback_core_advantages_infers_type_and_cleans_hospital_name_from_profile():
    candidate = HospitalCandidate(
        name='广东祈福医院',
        city='广州市',
        tier='三级甲等',
        public_introduction='广东祈福医院是中国首家通过国际JCI认证的大型三甲中西医结合医院，也是中国首家获CIHA国际认证的民营医院，集医疗、科研、教学、预防保健为一体。',
        sources=[SearchDocument(
            title='广东祈福医院公开资料',
            url='https://example.org/clifford',
            snippet='医院公开资料',
            fetched_at=datetime.now(UTC),
        )],
    )

    advantages = _fallback_core_advantages(candidate, ['儿科'], candidate.sources[0])

    assert '三级甲等中西医结合医院' in advantages
    assert '医院广东祈福医院' not in advantages
    assert '已通过国际JCI认证和CIHA国际认证' in advantages


def test_specialty_alias_matches_cardiovascular_disease_to_cardiology():
    candidate = HospitalCandidate(
        name='测试医院', city='广州市', specialties=('心血管病',),
        sources=[SearchDocument(
            title='测试医院心血管病专科',
            url='https://example.org',
            snippet='心血管病专科',
            fetched_at=datetime.now(UTC),
        )],
    )
    score = _specialty_strength_score(candidate, candidate.sources[0], ['心血管内科'])
    assert score >= 76.0


def test_specialty_score_uses_hospital_bound_capability_when_search_snippet_is_generic():
    candidate = HospitalCandidate(
        name='医院甲', city='广州市', specialties=(),
        capability_evidence=({
            'department': '心血管内科',
            'diagnosis_scope': '冠心病介入诊疗',
            'strength_level': '国家级重点',
        },),
        sources=[SearchDocument(
            title='医院甲', url='https://example.org', snippet='三级甲等医院',
            fetched_at=datetime.now(UTC),
        )],
    )
    ranked = rank_candidates(
        [candidate], directions=['心血管内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city',
    )
    assert ranked[0]['score_breakdown']['specialty'] == 71.8
    assert ranked[0]['specialty_evidence'][0]['department'] == '心血管内科'


def test_institution_name_alone_does_not_create_disease_capability_score():
    candidate = HospitalCandidate(
        name='广东省心血管病研究所', city='广州市',
        sources=[SearchDocument(
            title='医院地址信息', url='https://example.org', snippet='三级甲等',
            fetched_at=datetime.now(UTC),
        )],
    )
    ranked = rank_candidates(
        [candidate], directions=['心血管内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city', profile_key='cardiovascular',
    )
    assert ranked[0]['score_breakdown']['specialty'] == 46.8


def test_general_ranking_cannot_outweigh_missing_authoritative_specialty_ranking():
    candidate = HospitalCandidate(
        name='医院甲', city='广州市',
        ranking_evidence=({'specialty': '', 'rank': 5, 'score': 88.0},),
        sources=[SearchDocument(
            title='心血管内科介绍', url='https://third-party.example.org', snippet='冠心病诊疗',
            fetched_at=datetime.now(UTC),
        )],
    )
    ranked = rank_candidates(
        [candidate], directions=['心血管内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        scope='city', profile_key='cardiovascular',
    )
    assert ranked[0]['score_breakdown']['specialty'] <= 82.0


def test_specialty_score_keeps_baseline_with_ordinary_department_evidence():
    candidate = HospitalCandidate(
        name='科室目录医院', city='广州市', specialties=('神经内科',),
        ranking_evidence=({'specialty': '', 'rank': 765, 'ranking_scope': '全国', 'ranking_name': '综合排名'},),
        sources=[SearchDocument(
            title='科室目录医院神经内科', url='https://hospital.example.org', snippet='设有神经内科门诊',
            fetched_at=datetime.now(UTC),
        )],
    )

    ranked = rank_candidates(
        [candidate], directions=['神经内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['specialty'] == 47.9


def test_normalize_result_specialty_score_repairs_legacy_hidden_specialty_points():
    result = normalize_result_specialty_score({
        'score': 85.475,
        'score_breakdown': {
            'specialty': 82.0,
            'public_capability': 72.1,
            'geography': 100.0,
            'freshness_completeness': 87.5,
            'official_service': 100.0,
        },
        'has_direct_specialty_evidence': False,
    })

    assert result['score_breakdown']['specialty'] == 43.26
    assert result['score'] == 71.916


def test_normalize_result_specialty_score_keeps_explicit_specialty_evidence():
    result = normalize_result_specialty_score({
        'score': 90.125,
        'score_breakdown': {
            'specialty': 95.0,
            'public_capability': 100.0,
            'geography': 37.3,
            'freshness_completeness': 92.9,
            'official_service': 100.0,
        },
        'has_direct_specialty_evidence': False,
        'specialty_evidence': [
            {
                'department': '神经内科',
                'strength_level': '国家级',
                'diagnosis_scope': '国家临床重点专科',
            },
            {'specialty': '神经内科', 'rank': 1},
        ],
    })

    assert result['has_direct_specialty_evidence'] is True
    assert result['score_breakdown']['specialty'] == 95.0


def test_geography_score_uses_the_users_smallest_filled_region():
    assert _geography_score(('广东省', '广州市', '越秀区'), ('广东省', '广州市', '越秀区')) == 100.0
    assert _geography_score(('广东省', '广州市', '番禺区'), ('广东省', '广州市', '越秀区')) == 85.0
    assert _geography_score(('广东省', '深圳市', '南山区'), ('广东省', '广州市', '越秀区')) == 70.0
    assert _geography_score(('广东省', '广州市', ''), ('广东省', '广州市', '')) == 100.0
    assert _geography_score(('广东省', '深圳市', ''), ('广东省', '广州市', '')) == 70.0
    assert _geography_score(('广东省', '', ''), ('广东省', '', '')) == 100.0


def test_geography_score_decays_with_cross_province_distance():
    near = _geography_score(('湖南省', '长沙市', ''), ('广东省', '广州市', ''))
    far = _geography_score(('黑龙江省', '哈尔滨市', ''), ('广东省', '广州市', ''))
    assert 0.0 < far < near < 60.0


def test_rank_candidates_uses_explicit_city_level_when_district_field_is_city_fallback():
    candidate = HospitalCandidate(
        name='广州医院', city='广州市', province='广东省', district='越秀区',
        sources=[SearchDocument(title='广州医院', url='https://hospital.example.org', snippet='综合医院', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=[],
        location={'province': '广东省', 'city': '广州市', 'district': '广州市'},
        location_level='city', scope='national',
    )
    assert ranked[0]['score_breakdown']['geography'] == 100.0


def test_general_national_ranking_overrides_institution_name_prior_for_hospital_strength():
    candidate = HospitalCandidate(
        name='广东省人民医院', city='广州市', province='广东省', district='越秀区', public_capability=78.0,
        ranking_evidence=({'specialty': '', 'rank': 35, 'ranking_scope': '全国', 'ranking_name': '综合排名'},),
        sources=[SearchDocument(title='广东省人民医院', url='https://hospital.example.org', snippet='三级甲等', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=['肿瘤内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['public_capability'] == 98.6


def test_low_city_level_general_ranking_preserves_long_tail_rank_signal():
    candidate = HospitalCandidate(
        name='市级上榜医院', city='广州市', province='广东省', district='越秀区', public_capability=78.0,
        ranking_evidence=({'specialty': '', 'rank': 300, 'ranking_scope': '市级', 'ranking_name': '综合排名'},),
        sources=[SearchDocument(title='市级上榜医院', url='https://hospital.example.org', snippet='三级甲等', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=['肿瘤内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['public_capability'] == 70.4


def test_specialized_tcm_hospital_ranking_does_not_count_as_general_institutional_strength():
    candidate = HospitalCandidate(
        name='广东省中医院', city='广州市', province='广东省', district='越秀区', public_capability=78.0,
        ranking_evidence=({'specialty': '', 'rank': 1, 'ranking_scope': '全国', 'ranking_name': '中医医院综合排名'},),
        sources=[SearchDocument(title='广东省中医院', url='https://hospital.example.org', snippet='三级甲等', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=['肿瘤内科'],
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['public_capability'] == 78.0


def test_exact_specialty_ranking_takes_precedence_over_broader_category_ranking():
    candidate = HospitalCandidate(
        name='肿瘤医院', city='广州市', province='广东省', district='越秀区',
        ranking_evidence=(
            {'specialty': '肿瘤学', 'rank': 1, 'score': 100.0, 'ranking_scope': '全国'},
            {'specialty': '肿瘤内科', 'rank': 10, 'score': 73.0, 'ranking_scope': '全国'},
        ),
        sources=[SearchDocument(title='医院目录', url='https://hospital.example.org', snippet='三级甲等', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=['肿瘤内科'], profile_key='oncology',
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['specialty'] == 81.1158


def test_broader_specialty_ranking_is_discounted_when_no_exact_ranking_exists():
    candidate = HospitalCandidate(
        name='肿瘤医院', city='广州市', province='广东省', district='越秀区',
        ranking_evidence=({'specialty': '肿瘤学', 'rank': 1, 'score': 100.0, 'ranking_scope': '全国'},),
        sources=[SearchDocument(title='医院目录', url='https://hospital.example.org', snippet='三级甲等', fetched_at=datetime.now(UTC))],
    )
    ranked = rank_candidates(
        [candidate], directions=['肿瘤内科'], profile_key='oncology',
        location={'province': '广东省', 'city': '广州市', 'district': '越秀区'}, scope='city',
    )

    assert ranked[0]['score_breakdown']['specialty'] == 80.8


@pytest.mark.parametrize(('rank', 'expected_bonus'), [
    (1, 40.0),
    (20, 28.0),
    (21, 27.775),
    (100, 10.0),
    (101, 0.0),
])
def test_national_specialty_ranking_bonus_uses_confirmed_two_segment_rank_curve(rank, expected_bonus):
    evidence = {'rank': rank, 'score': 100.0, 'ranking_scope': '全国'}

    assert _specialty_ranking_bonus([(evidence, 2, 1.0)]) == expected_bonus
