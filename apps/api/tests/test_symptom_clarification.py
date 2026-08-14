import json

import pytest

from app.symptom_clarification import ClarificationUnavailableError, clarify_symptoms


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_ambiguous_input_returns_one_question():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'location', 'text': '你主要是哪里不舒服？', 'type': 'single',
            'options': ['胸口', '肚子', '其他', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '不舒服', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['question']['text'] == '你主要是哪里不舒服？'
    assert result['question']['options']
    assert result['progress']['current'] == 1


def test_deepseek_generates_one_plain_language_question():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'chest_trigger',
            'text': '胸口不舒服是在什么时候出现的？',
            'type': 'single',
            'options': ['走路或活动时', '休息时也会', '吃完饭后', '说不清楚', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '胸闷', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['ai_used'] is True
    assert result['question']['text'] == '胸口不舒服是在什么时候出现的？'
    assert len(result['question']['options']) == 5


def test_deepseek_controls_question_for_longer_ambiguous_description():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'breath_timing',
            'text': '这种不舒服是在什么时候更明显？',
            'type': 'single',
            'options': ['活动时', '休息时', '晚上躺下后', '说不清楚', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '胸闷气短', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['ai_used'] is True
    assert result['question']['id'] == 'breath_timing'


def test_invalid_deepseek_question_fails_without_local_fallback():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {'id': 'x', 'text': '请诊断疾病', 'type': 'single', 'options': ['冠心病']},
    }, ensure_ascii=False)}}]}
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms(
            '胸闷', answers=[], ai_consent=True,
            environ={'DEEPSEEK_API_KEY': 'test'},
            transport=lambda *args, **kwargs: FakeResponse(payload),
        )


def test_deepseek_does_not_repeat_headache_location_question():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'location',
            'text': '你的头疼是哪里疼？',
            'type': 'single',
            'options': ['头部', '其他', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms(
            '头疼', answers=[], ai_consent=True,
            environ={'DEEPSEEK_API_KEY': 'test'},
            transport=lambda *args, **kwargs: FakeResponse(payload),
        )


def test_answer_can_resolve_to_direction_and_department():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'cardiology', 'title': '心血管相关疾病方向', 'likelihood': '更符合',
            'basis': '症状位置需要结合检查评估。', 'department': '心血管内科',
            'possible_diseases': ['心绞痛'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '胸口不舒服',
        answers=[{'question_id': 'location', 'value': '胸口'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'COMPLETE'
    assert result['directions'][0]['department'] == '心血管内科'
    assert result['directions'][0]['possible_diseases']


def test_red_flag_answer_stops_normal_flow():
    result = clarify_symptoms(
        '胸痛',
        answers=[{'question_id': 'severity', 'value': '呼吸困难'}],
        ai_consent=True,
        environ={},
    )
    assert result['status'] == 'EMERGENCY'
    assert result['urgent_warning']


def test_headache_query_does_not_repeat_known_body_location():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('头疼', answers=[], ai_consent=True, environ={})


def test_headache_pattern_resolves_to_neurology():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'neurology', 'title': '偏头痛相关方向', 'likelihood': '更符合',
            'basis': '头痛模式需要医生进一步评估。', 'department': '神经内科',
            'possible_diseases': ['偏头痛'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '头疼',
        answers=[{'question_id': 'headache_pattern', 'value': '一边一跳一跳地疼，还可能想吐'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'COMPLETE'
    assert result['directions'][0]['department'] == '神经内科'


def test_sudden_severe_headache_triggers_emergency_flow():
    result = clarify_symptoms('头疼', answers=[{'question_id': 'headache_pattern', 'value': '突然一下子特别疼'}], ai_consent=True, environ={})
    assert result['status'] == 'EMERGENCY'
    assert result['urgent_warning']


def test_custom_answer_can_resolve_by_matching_plain_language_description():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'cardiology', 'title': '心血管相关疾病方向', 'likelihood': '需要评估',
            'basis': '需要结合检查判断。', 'department': '心血管内科',
            'possible_diseases': ['心绞痛'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms('不舒服', answers=[{
        'question_id': 'location', 'value': '胸口左边像针扎一样，活动时更明显',
    }], ai_consent=True, environ={'DEEPSEEK_API_KEY': 'test'}, transport=lambda *args, **kwargs: FakeResponse(payload))
    assert result['status'] == 'COMPLETE'
    assert result['directions'][0]['department'] == '心血管内科'


def test_custom_answer_containing_red_flag_triggers_emergency_flow():
    result = clarify_symptoms('不舒服', answers=[{
        'question_id': 'location', 'value': '胸口不舒服，而且呼吸困难',
    }], ai_consent=True, environ={})
    assert result['status'] == 'EMERGENCY'
    assert result['urgent_warning']


def test_deepseek_resolves_follow_up_answer_to_possible_diseases():
    payload = {'choices': [{'message': {'content': json.dumps({
        'directions': [{
            'key': 'cardiology', 'title': '心血管相关疾病方向', 'likelihood': '需要评估',
            'basis': '胸闷需要结合病史和检查进一步判断。', 'department': '心血管内科',
            'possible_diseases': ['心绞痛', '冠心病'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '胸闷', answers=[{'question_id': 'location', 'value': '不确定'}], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'}, transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'COMPLETE'
    assert result['ai_used'] is True
    assert result['directions'][0]['possible_diseases'] == ['心绞痛', '冠心病']


def test_ai_can_choose_follow_up_question_then_complete():
    payloads = [
        {'choices': [{'message': {'content': json.dumps({
            'question': {
                'id': 'location',
                'text': '你主要是哪里不舒服？',
                'type': 'single',
                'options': ['胸口', '肚子', '其他', '不确定'],
            },
        }, ensure_ascii=False)}}]},
        {'choices': [{'message': {'content': json.dumps({
            'status': 'NEEDS_CLARIFICATION',
            'question': {
                'id': 'duration',
                'text': '这种不舒服大概多久了？',
                'type': 'single',
                'options': ['刚开始', '几天了', '很久了', '不确定'],
            },
        }, ensure_ascii=False)}}]},
        {'choices': [{'message': {'content': json.dumps({
            'status': 'COMPLETE',
            'directions': [{
                'key': 'general', 'title': '需要进一步评估的健康问题', 'likelihood': '待评估',
                'basis': '需要结合更多信息判断。', 'department': '全科医学科',
                'possible_diseases': [], 'urgent_warning': '',
            }],
            'urgent_warning': '',
        }, ensure_ascii=False)}}]},
    ]

    def transport(*args, **kwargs):
        return FakeResponse(payloads.pop(0))

    first = clarify_symptoms(
        '不舒服', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'}, transport=transport,
    )
    second = clarify_symptoms(
        '不舒服', answers=[{'question_id': 'location', 'value': '不确定'}], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'}, transport=transport,
    )
    complete = clarify_symptoms(
        '不舒服', answers=[
            {'question_id': 'location', 'value': '不确定'},
            {'question_id': 'duration', 'value': '不确定'},
        ], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'}, transport=transport,
    )

    assert first['status'] == 'NEEDS_CLARIFICATION'
    assert second['status'] == 'NEEDS_CLARIFICATION'
    assert second['question']['id'] == 'duration'
    assert complete['status'] == 'COMPLETE'
    assert complete['progress']['current'] == 2


def test_ai_cannot_keep_clarifying_past_the_question_limit():
    repeated_question = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'next', 'text': '还有其他情况吗？', 'type': 'single',
            'options': ['有', '没有', '不确定'],
        },
    }, ensure_ascii=False)}}]}

    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms(
            '不舒服',
            answers=[
                {'question_id': 'q1', 'value': '不确定'},
                {'question_id': 'q2', 'value': '不确定'},
                {'question_id': 'q3', 'value': '不确定'},
            ],
            ai_consent=True,
            environ={'DEEPSEEK_API_KEY': 'test'},
            transport=lambda *args, **kwargs: FakeResponse(repeated_question),
        )


def test_ai_completion_is_used_even_for_a_vague_uncertain_answer():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'general', 'title': '需要进一步评估的健康问题', 'likelihood': '待评估',
            'basis': '信息仍然有限。', 'department': '全科医学科',
            'possible_diseases': [], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '不舒服',
        answers=[{'question_id': 'location', 'value': '不确定'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['status'] == 'COMPLETE'
    assert result['ai_used'] is True
    assert result['directions'][0]['department'] == '全科医学科'


def test_ai_unavailable_does_not_use_local_question_or_direction():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('不舒服', answers=[], ai_consent=True, environ={})


def test_invalid_ai_direction_does_not_return_local_disease_guess():
    invalid_payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE', 'directions': [], 'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms(
            '胸闷',
            answers=[{'question_id': 'location', 'value': '胸口'}],
            ai_consent=True,
            environ={'DEEPSEEK_API_KEY': 'test'},
            transport=lambda *args, **kwargs: FakeResponse(invalid_payload),
        )
