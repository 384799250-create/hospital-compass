import json
from datetime import date
from urllib.error import HTTPError, URLError

import pytest

from app.ai_matcher import ai_match
from app.data import DEMO_HOSPITALS

AS_OF = date(2026, 8, 5)


class FakeResponse:
    def __init__(self, payload: dict | bytes, status: int = 200):
        self._body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        )
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self._body


def call_ai_match(**kwargs):
    try:
        return ai_match(**kwargs)
    except TypeError as exc:
        pytest.fail(f'ai_match does not support the injectable client contract: {exc}')


def deepseek_payload(content) -> dict:
    return {'choices': [{'message': {'content': content}}]}


def assert_local_fallback(response):
    assert response.directions == ['心血管内科']
    assert [result.id for result in response.results] == ['demo-1', 'demo-2', 'demo-3']
    assert response.ai.model_dump() == {
        'used': False,
        'summary': None,
        'directions': [],
        'fallback': True,
    }
    assert response.pending_candidates == []


def test_successful_deepseek_json_matches_filtered_direction_with_json_mode():
    captured = {}

    def transport(request, timeout):
        captured['url'] = request.full_url
        captured['authorization'] = request.get_header('Authorization')
        captured['body'] = json.loads(request.data)
        captured['timeout'] = timeout
        return FakeResponse({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': '建议优先匹配心血管内科。',
                        'directions': ['心血管内科'],
                    }, ensure_ascii=False),
                },
            }],
        })

    response = call_ai_match(
        query='持续心慌',
        city='上海',
        priority='specialty',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={
            'DEEPSEEK_API_KEY': 'test-secret',
            'DEEPSEEK_MODEL': 'configured-model',
        },
        transport=transport,
    )

    assert response.ai.model_dump() == {
        'used': True,
        'summary': '建议优先匹配心血管内科。',
        'directions': ['心血管内科'],
        'fallback': False,
    }
    assert response.directions == ['心血管内科']
    assert [result.id for result in response.results] == ['demo-1', 'demo-2', 'demo-3']
    assert captured == {
        'url': 'https://api.deepseek.com/chat/completions',
        'authorization': 'Bearer test-secret',
        'body': {
            'model': 'configured-model',
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        '只返回 JSON object：summary 是最多 240 字符的字符串，'
                        'directions 是建议专科方向的字符串数组；pending_candidates 是可选数组，'
                        '每项只能包含 name、city、direction、reason，且最多返回 3 项。'
                        '候选可为医院、专科门诊、诊所或诊疗中心等中国医疗机构；'
                        '名称必须完整，不确定时返回空数组。'
                        '候选仅是待人工核验的医疗机构名称，不是已核验推荐；'
                        '不得提供诊断或治疗建议；不得捏造联系方式、地址或来源。'
                    ),
                },
                {'role': 'user', 'content': '持续心慌'},
            ],
            'response_format': {'type': 'json_object'},
        },
        'timeout': 10.0,
    }


def test_compliant_pending_candidates_are_returned_when_no_verified_results_exist():
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配。',
            'directions': ['心血管内科'],
            'pending_candidates': [
                {
                    'name': '待核验医院',
                    'city': '上海',
                    'direction': '心血管内科',
                    'reason': '名称可能与所需专科方向相关，需人工核验。',
                },
            ],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='specialty',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.ai.used is True
    assert response.results == []
    assert [candidate.model_dump() for candidate in response.pending_candidates] == [{
        'name': '待核验医院',
        'city': '上海',
        'direction': '心血管内科',
        'reason': '名称可能与所需专科方向相关，需人工核验。',
    }]


def test_pending_candidate_accepts_unknown_direction_and_city_suffix():
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配，保留待核验候选。',
            'directions': ['神经内科'],
            'pending_candidates': [{
                'name': '北京大学第一医院',
                'city': '北京市',
                'direction': '神经内科',
                'reason': '名称可能与所需专科方向相关，需人工核验。',
            }],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续头痛',
        city='北京市',
        priority='specialty',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.ai.used is True
    assert response.ai.directions == []
    assert response.directions == []
    assert response.results == []
    assert [candidate.model_dump() for candidate in response.pending_candidates] == [{
        'name': '北京大学第一医院',
        'city': '北京市',
        'direction': '神经内科',
        'reason': '名称可能与所需专科方向相关，需人工核验。',
    }]


def test_compliant_medical_entity_is_preserved_and_prohibited_content_is_dropped_without_ai_directions():
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无可匹配的正式结果，保留待核验候选。',
            'directions': [],
            'pending_candidates': [
                {
                    'name': '头痛门诊',
                    'city': '上海',
                    'direction': '神经内科',
                    'reason': '名称可能与头痛就医方向相关，需人工核验。',
                },
                {
                    'name': '另一个头痛门诊',
                    'city': '上海',
                    'direction': '神经内科',
                    'reason': '联系电话 123-456-7890',
                },
            ],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续头痛',
        city='上海',
        priority='specialty',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.ai.model_dump() == {
        'used': True,
        'summary': '暂无可匹配的正式结果，保留待核验候选。',
        'directions': [],
        'fallback': False,
    }
    assert response.directions == []
    assert response.results == []
    assert [candidate.model_dump() for candidate in response.pending_candidates] == [{
        'name': '头痛门诊',
        'city': '上海',
        'direction': '神经内科',
        'reason': '名称可能与头痛就医方向相关，需人工核验。',
    }]


def test_pending_candidates_are_hidden_when_verified_results_exist():
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '已有核验结果。',
            'directions': ['心血管内科'],
            'pending_candidates': [{
                'name': '不应公开的待核验名称',
                'city': '上海',
                'direction': '心血管内科',
                'reason': '仅供人工核验。',
            }],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert [result.id for result in response.results] == ['demo-1', 'demo-2', 'demo-3']
    assert response.pending_candidates == []


def test_invalid_pending_candidates_are_dropped_without_failing_the_ai_match():
    valid_candidate = {
        'name': '合规待核验医院',
        'city': '上海',
        'direction': '心血管内科',
        'reason': '只保留名称供人工核验。',
    }
    invalid_candidates = [
        'not-an-object',
        {**valid_candidate, 'address': '不得返回的地址'},
        {**valid_candidate, 'name': 42},
        {**valid_candidate, 'city': '   '},
        {**valid_candidate, 'direction': '   '},
        {**valid_candidate, 'direction': '科' * 41},
        {**valid_candidate, 'name': '医' * 81},
        {**valid_candidate, 'city': '城' * 41},
        {**valid_candidate, 'reason': '因' * 181},
    ]

    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '过滤不安全候选。',
            'directions': ['心血管内科'],
            'pending_candidates': [*invalid_candidates, valid_candidate],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.ai.used is True
    assert response.results == []
    assert [candidate.model_dump() for candidate in response.pending_candidates] == [
        valid_candidate,
    ]


@pytest.mark.parametrize(
    'unsafe_reason',
    [
        '详情见 http://example.cn/hospital',
        '详情见 https://example.cn/hospital',
        '详情见 www.example.cn/hospital',
        '联系电话 123 4567',
        '联系电话 123-456-7890',
        '位于某省',
        '位于某市',
        '位于某区',
        '位于某县',
        '位于健康路',
        '位于平安街',
        '门牌 10 号',
        '推荐前往该院核验',
        '诊断为偏头痛',
        '可服用止痛药治疗',
        '联系人张医生',
        '微信 doctor123',
        '邮箱 doctor@example.cn',
    ],
    ids=[
        'http-url',
        'https-url',
        'www-url',
        'spaced-phone',
        'dashed-phone',
        'province-address-cue',
        'city-address-cue',
        'district-address-cue',
        'county-address-cue',
        'road-address-cue',
        'street-address-cue',
        'number-address-cue',
        'recommendation-wording',
        'diagnosis-advice',
        'treatment-advice',
        'contact-person',
        'wechat-contact',
        'email-contact',
    ],
)
def test_pending_candidate_is_dropped_when_reason_contains_prohibited_content(unsafe_reason):
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配。',
            'directions': ['心血管内科'],
            'pending_candidates': [{
                'name': '待核验医院',
                'city': '上海',
                'direction': '心血管内科',
                'reason': unsafe_reason,
            }],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.ai.used is True
    assert response.results == []
    assert response.pending_candidates == []


@pytest.mark.parametrize(
    'field',
    ['name', 'city', 'direction'],
    ids=['name', 'city', 'direction'],
)
def test_pending_candidate_is_dropped_when_another_display_field_contains_prohibited_content(field):
    candidate = {
        'name': '待核验医院',
        'city': '上海',
        'direction': '心血管内科',
        'reason': '名称可能与所需专科方向相关，需人工核验。',
    }
    candidate[field] = '包含推荐措辞'

    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配。',
            'directions': ['心血管内科'],
            'pending_candidates': [candidate],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.pending_candidates == []


@pytest.mark.parametrize(
    'detailed_city',
    ['北京市朝阳区', '健康路 10 号', '南京市鼓楼区中山路'],
    ids=['city-district', 'road-number', 'city-district-road'],
)
def test_pending_candidate_is_dropped_when_city_contains_detailed_address(detailed_city):
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配。',
            'directions': [],
            'pending_candidates': [{
                'name': '待核验医院',
                'city': detailed_city,
                'direction': '神经内科',
                'reason': '名称可能与所需专科方向相关，需人工核验。',
            }],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续头痛',
        city='北京市',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.pending_candidates == []
    assert response.ai.fallback is True


def test_pending_candidates_require_city_level_city_values():
    def candidate(city):
        return {
            'name': '待核验医院',
            'city': city,
            'direction': '神经内科',
            'reason': '名称可能与所需专科方向相关，需人工核验。',
        }

    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '暂无已核验匹配。',
            'directions': [],
            'pending_candidates': [
                *(candidate(city) for city in ('朝阳区', '海淀区', '浦东新区')),
                *(candidate(city) for city in ('北京市', 'Beijing', 'Shanghai', 'Guangzhou')),
            ],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续头痛',
        city='北京市',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert [candidate.city for candidate in response.pending_candidates] == [
        '北京市',
        'Beijing',
        'Shanghai',
    ]


def test_pending_candidates_are_trimmed_and_limited_to_three_valid_items():
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(json.dumps({
            'summary': '返回最多三个待核验名称。',
            'directions': ['心血管内科'],
            'pending_candidates': [
                {
                    'name': f'  待核验{number}医院  ',
                    'city': '  上海  ',
                    'direction': '  心血管内科  ',
                    'reason': '  仅供人工核验。  ',
                }
                for number in range(1, 5)
            ],
        }, ensure_ascii=False)))

    response = call_ai_match(
        query='持续心悸',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=(),
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert [candidate.model_dump() for candidate in response.pending_candidates] == [
        {
            'name': f'待核验{number}医院',
            'city': '上海',
            'direction': '心血管内科',
            'reason': '仅供人工核验。',
        }
        for number in range(1, 4)
    ]


def test_no_consent_returns_local_match_without_calling_transport():
    def transport(request, timeout):
        raise AssertionError('transport must not be called without consent')

    response = call_ai_match(
        query='冠心病',
        city='上海',
        priority='overall',
        ai_consent=False,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.directions == ['心血管内科']
    assert response.ai.model_dump() == {
        'used': False,
        'summary': None,
        'directions': [],
        'fallback': True,
    }
    assert response.pending_candidates == []


def test_emergency_keeps_local_emergency_result_without_calling_transport():
    def transport(request, timeout):
        raise AssertionError('transport must not be called for an emergency')

    response = call_ai_match(
        query='突发胸痛并呼吸困难',
        city=None,
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.emergency is True
    assert response.directions == []
    assert response.results == []
    assert response.ai.model_dump() == {
        'used': False,
        'summary': None,
        'directions': [],
        'fallback': True,
    }
    assert response.pending_candidates == []


def test_unknown_ai_directions_are_removed_before_matching():
    def transport(request, timeout):
        return FakeResponse({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': '保留可核验的专科方向。',
                        'directions': ['不存在的科室', '心血管内科', '心血管内科'],
                    }, ensure_ascii=False),
                },
            }],
        })

    response = call_ai_match(
        query='持续心慌',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert response.directions == ['心血管内科']
    assert response.ai.directions == ['心血管内科']


@pytest.mark.parametrize(
    'content',
    [
        '',
        'not json',
        '[]',
        json.dumps({'summary': '过长' * 121, 'directions': ['心血管内科']}, ensure_ascii=False),
        json.dumps({'summary': '无有效方向', 'directions': []}, ensure_ascii=False),
        json.dumps({'summary': '未知方向', 'directions': ['未知科室']}, ensure_ascii=False),
        json.dumps({'summary': '无效方向', 'directions': [42]}, ensure_ascii=False),
        json.dumps({'summary': 42, 'directions': ['心血管内科']}, ensure_ascii=False),
        json.dumps(
            {'summary': '含未允许字段', 'directions': ['心血管内科'], 'extra': True},
            ensure_ascii=False,
        ),
    ],
    ids=[
        'empty-content',
        'malformed-json',
        'non-object-json',
        'summary-too-long',
        'empty-directions',
        'unknown-only-directions',
        'non-string-direction',
        'non-string-summary',
        'extra-field',
    ],
)
def test_invalid_ai_content_returns_local_fallback(content):
    def transport(request, timeout):
        return FakeResponse(deepseek_payload(content))

    response = call_ai_match(
        query='冠心病',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert_local_fallback(response)


@pytest.mark.parametrize(
    'error',
    [
        TimeoutError('timed out'),
        URLError('connection refused'),
        HTTPError('https://api.deepseek.com/chat/completions', 500, 'server error', None, None),
    ],
    ids=['timeout', 'url-error', 'http-error'],
)
def test_transport_errors_return_local_fallback(error):
    def transport(request, timeout):
        raise error

    response = call_ai_match(
        query='冠心病',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert_local_fallback(response)


@pytest.mark.parametrize(
    ('payload', 'status'),
    [
        (b'', 200),
        (b'not json', 200),
        (deepseek_payload(json.dumps({'summary': '不应使用', 'directions': ['心血管内科']})), 503),
    ],
    ids=['empty-response', 'invalid-response-json', 'http-status-error'],
)
def test_invalid_http_response_returns_local_fallback(payload, status):
    def transport(request, timeout):
        return FakeResponse(payload, status=status)

    response = call_ai_match(
        query='冠心病',
        city='上海',
        priority='overall',
        ai_consent=True,
        hospitals=DEMO_HOSPITALS,
        as_of=AS_OF,
        environ={'DEEPSEEK_API_KEY': 'test-secret'},
        transport=transport,
    )

    assert_local_fallback(response)
