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


def test_numeric_ai_question_id_is_normalized_to_string():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 1, 'text': '孩子现在多大了？', 'type': 'single',
            'options': ['3岁以下', '3-6岁', '7-12岁', '12岁以上', '不确定'],
        },
        'estimated_total': 5,
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '孩子发热咳嗽', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['question']['id'] == '1'


def test_ai_question_uses_a_thirty_second_timeout():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'age', 'text': '孩子现在多大了？', 'type': 'single',
            'options': ['3岁以下', '3-6岁', '7-12岁', '12岁以上', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    timeouts = []

    def transport(*args, **kwargs):
        timeouts.append(kwargs['timeout'])
        return FakeResponse(payload)

    result = clarify_symptoms(
        '孩子发热咳嗽', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'}, transport=transport,
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert timeouts == [30.0]


def test_ai_normalizes_an_equivalent_uncertainty_option():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'age', 'text': '孩子现在多大了？', 'type': 'single',
            'options': ['3岁以下', '3-6岁', '7-12岁', '12岁以上', '不清楚'],
        },
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '孩子发热咳嗽', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result['question']['options'][-1] == '不确定'


@pytest.mark.parametrize('uncertainty_option', ['不知道', '说不清楚', '不太清楚'])
def test_ai_normalizes_common_uncertainty_options(uncertainty_option):
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'age', 'text': '孩子现在多大了？', 'type': 'single',
            'options': ['3岁以下', '3-6岁', '7-12岁', '12岁以上', uncertainty_option],
        },
    }, ensure_ascii=False)}}]}

    result = clarify_symptoms(
        '孩子发热咳嗽', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result['question']['options'][-1] == '不确定'


def test_follow_up_prompt_requires_json_only_and_no_duplicate_questions():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'skin_duration', 'text': '手肘脱皮有多久了？', 'type': 'single',
            'options': ['刚开始', '几天到几周', '超过一个月', '不确定'],
        },
    }, ensure_ascii=False)}}]}

    def transport(request, **kwargs):
        system_prompt = json.loads(request.data.decode('utf-8'))['messages'][0]['content']
        assert '不得使用 Markdown' in system_prompt
        assert '不得重复已问主题' in system_prompt
        return FakeResponse(payload)

    result = clarify_symptoms(
        '手肘脱皮',
        answers=[{'question_id': 'skin_feeling', 'value': '摸起来粗糙'}],
        asked_questions=[{
            'id': 'skin_feeling', 'text': '脱皮处摸起来是什么感觉？',
            'options': ['粗糙', '光滑', '不确定'],
        }],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=transport,
    )

    assert result['question']['id'] == 'skin_duration'


def test_follow_up_uses_an_unasked_safe_question_when_ai_is_unavailable():
    def unavailable(*args, **kwargs):
        return FakeResponse({'invalid': True})

    result = clarify_symptoms(
        '手肘脱皮',
        answers=[{'question_id': 'skin_feeling', 'value': '摸起来粗糙'}],
        asked_questions=[{
            'id': 'skin_feeling', 'text': '脱皮处摸起来是什么感觉？',
            'options': ['粗糙', '光滑', '不确定'],
        }],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=unavailable,
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['ai_used'] is False
    assert result['question']['id'] != 'skin_feeling'
    assert result['question']['options'][-1] == '不确定'


def test_follow_up_retries_twice_before_using_a_safe_question():
    attempts = 0

    def unavailable(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse({'invalid': True})

    result = clarify_symptoms(
        '手肘脱皮',
        answers=[{'question_id': 'skin_feeling', 'value': '摸起来粗糙'}],
        asked_questions=[{
            'id': 'skin_feeling', 'text': '脱皮处摸起来是什么感觉？',
            'options': ['粗糙', '光滑', '不确定'],
        }],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=unavailable,
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert attempts == 2


def test_ai_estimated_question_count_is_returned_to_the_client():
    payload = {'choices': [{'message': {'content': json.dumps({
        'question': {
            'id': 'duration', 'text': '这种不舒服大概多久了？', 'type': 'single',
            'options': ['刚开始', '几天了', '很久了', '不确定'],
        },
        'estimated_total': 4,
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '不舒服', answers=[], ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )
    assert result['estimated_total'] == 4


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


def test_completed_direction_preserves_the_ai_likelihood_label():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'neurology', 'title': '\u795e\u7ecf\u5185\u79d1\u65b9\u5411', 'likelihood': '\u4e2d',
            'basis': '\u9700\u8981\u7ed3\u5408\u75c7\u72b6\u8fdb\u4e00\u6b65\u8bc4\u4f30', 'department': '\u795e\u7ecf\u5185\u79d1',
            'possible_diseases': ['\u504f\u5934\u75db'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}

    result = clarify_symptoms(
        '\u5934\u75db',
        answers=[{'question_id': 'pattern', 'value': '\u53cd\u590d\u51fa\u73b0'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result['directions'][0]['likelihood'] == '\u4e2d'


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
            'estimated_total': 4,
        }, ensure_ascii=False)}}]},
        {'choices': [{'message': {'content': json.dumps({
            'status': 'NEEDS_CLARIFICATION',
            'question': {
                'id': 'duration',
                'text': '这种不舒服大概多久了？',
                'type': 'single',
                'options': ['刚开始', '几天了', '很久了', '不确定'],
            },
            'estimated_total': 3,
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
    assert first['estimated_total'] == 4
    assert second['status'] == 'NEEDS_CLARIFICATION'
    assert second['estimated_total'] == 3
    assert second['question']['id'] == 'duration'
    assert complete['status'] == 'COMPLETE'
    assert complete['progress']['current'] == 2


def test_ai_retries_when_a_follow_up_question_repeats_a_previous_topic():
    repeated_question = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'symptom_duration', 'text': '这种情况持续多长时间了？', 'type': 'single',
            'options': ['刚开始', '几天了', '很久了', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    distinct_question = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'activity_trigger', 'text': '走路或活动时会不会更明显？', 'type': 'single',
            'options': ['会明显加重', '没有变化', '休息时更明显', '不确定'],
        },
    }, ensure_ascii=False)}}]}
    payloads = [repeated_question, distinct_question]

    result = clarify_symptoms(
        '胸闷',
        answers=[{'question_id': 'duration', 'value': '几天了'}],
        asked_questions=[{
            'id': 'duration', 'text': '这种不舒服大概多久了？',
            'options': ['刚开始', '几天了', '很久了', '不确定'],
        }],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payloads.pop(0)),
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['question']['id'] == 'activity_trigger'


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
            answers=[{'question_id': f'q{index}', 'value': '不确定'} for index in range(1, 11)],
            ai_consent=True,
            environ={'DEEPSEEK_API_KEY': 'test'},
            transport=lambda *args, **kwargs: FakeResponse(repeated_question),
        )


def test_ai_can_ask_a_fourth_question_before_the_ten_question_limit():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'q4', 'text': '\u8fd9\u79cd\u60c5\u51b5\u662f\u4e00\u76f4\u6709\u8fd8\u662f\u65f6\u6709\u65f6\u65e0\uff1f', 'type': 'single',
            'options': ['\u4e00\u76f4\u6709', '\u65f6\u6709\u65f6\u65e0', '\u4e0d\u786e\u5b9a'],
        },
    }, ensure_ascii=False)}}]}

    result = clarify_symptoms(
        '\u6389\u5934\u53d1',
        answers=[
            {'question_id': 'q1', 'value': '\u4e0d\u5230\u4e00\u4e2a\u6708'},
            {'question_id': 'q2', 'value': '\u5934\u9876\u6216\u53d1\u9645\u7ebf'},
            {'question_id': 'q3', 'value': '\u6709\u5934\u76ae\u95ee\u9898'},
        ],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['question']['id'] == 'q4'
    assert result['progress'] == {'current': 4, 'total': 4}


def test_ai_retries_with_a_complete_result_after_reaching_the_question_limit():
    repeated_question = {'choices': [{'message': {'content': json.dumps({
        'status': 'NEEDS_CLARIFICATION',
        'question': {
            'id': 'q4', 'text': '\u8fd9\u79cd\u60c5\u51b5\u662f\u6301\u7eed\u8fd8\u662f\u65f6\u6709\u65f6\u65e0\uff1f', 'type': 'single',
            'options': ['\u4e00\u76f4\u5982\u6b64', '\u65f6\u6709\u65f6\u65e0', '\u4e0d\u786e\u5b9a'],
        },
    }, ensure_ascii=False)}}]}
    complete = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'hair_loss', 'title': '\u8131\u53d1\u65b9\u5411', 'likelihood': '\u8f83\u9ad8',
            'basis': '\u5df2\u6839\u636e\u524d\u4e09\u4e2a\u56de\u7b54\u5b8c\u6210\u5206\u6d41', 'department': '\u76ae\u80a4\u79d1',
            'possible_diseases': ['\u96c4\u6fc0\u7d20\u6027\u8131\u53d1'], 'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    payloads = [repeated_question, complete]
    attempts = 0

    def transport(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse(payloads.pop(0))

    result = clarify_symptoms(
        '\u6389\u5934\u53d1',
        answers=[{'question_id': f'q{index}', 'value': '\u4e0d\u786e\u5b9a'} for index in range(1, 11)],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=transport,
    )

    assert result['status'] == 'COMPLETE'
    assert result['directions'][0]['department'] == '\u76ae\u80a4\u79d1'
    assert attempts == 2


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


def test_ai_completion_normalizes_false_urgent_warnings():
    malformed_payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'hair_loss',
            'title': '\u8131\u53d1\u65b9\u5411',
            'likelihood': '\u8f83\u9ad8',
            'basis': '\u5934\u9876\u548c\u53d1\u9645\u7ebf\u8131\u53d1\u9700\u8981\u76ae\u80a4\u79d1\u8bc4\u4f30',
            'department': '\u76ae\u80a4\u79d1',
            'possible_diseases': ['\u96c4\u6fc0\u7d20\u6027\u8131\u53d1'],
            'urgent_warning': False,
        }],
        'urgent_warning': False,
    }, ensure_ascii=False)}}]}
    attempts = 0

    def transport(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse(malformed_payload)

    result = clarify_symptoms(
        '\u6389\u5934\u53d1',
        answers=[{'question_id': 'q1', 'value': '\u5934\u9876\u8131\u53d1'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=transport,
    )

    assert result['status'] == 'COMPLETE'
    assert attempts == 1
    assert result['urgent_warning'] == ''
    assert result['directions'][0]['urgent_warning'] == ''
    assert result['directions'][0]['department'] == '\u76ae\u80a4\u79d1'


def test_ai_completion_retries_once_after_a_transient_transport_error():
    payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE',
        'directions': [{
            'key': 'hair_loss',
            'title': '\u8131\u53d1\u65b9\u5411',
            'likelihood': '\u8f83\u9ad8',
            'basis': '\u5934\u9876\u548c\u53d1\u9645\u7ebf\u8131\u53d1\u9700\u8981\u76ae\u80a4\u79d1\u8bc4\u4f30',
            'department': '\u76ae\u80a4\u79d1',
            'possible_diseases': ['\u96c4\u6fc0\u7d20\u6027\u8131\u53d1'],
            'urgent_warning': '',
        }],
        'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    attempts = 0

    def transport(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError('connection reset')
        return FakeResponse(payload)

    result = clarify_symptoms(
        '\u6389\u5934\u53d1',
        answers=[{'question_id': 'q1', 'value': '\u5934\u9876\u8131\u53d1'}],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=transport,
    )

    assert result['status'] == 'COMPLETE'
    assert attempts == 2


def test_ai_unavailable_does_not_use_local_question_or_direction():
    with pytest.raises(ClarificationUnavailableError):
        clarify_symptoms('不舒服', answers=[], ai_consent=True, environ={})


def test_invalid_ai_direction_continues_with_a_safe_question_without_guessing():
    invalid_payload = {'choices': [{'message': {'content': json.dumps({
        'status': 'COMPLETE', 'directions': [], 'urgent_warning': '',
    }, ensure_ascii=False)}}]}
    result = clarify_symptoms(
        '胸闷',
        answers=[{'question_id': 'location', 'value': '胸口'}],
        asked_questions=[{
            'id': 'location', 'text': '主要是哪里不舒服？',
            'options': ['胸口', '肚子', '不确定'],
        }],
        ai_consent=True,
        environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(invalid_payload),
    )

    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert result['directions'] == []
    assert result['question']
    assert result['ai_used'] is False
