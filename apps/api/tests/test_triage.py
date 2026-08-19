import json
from functools import partial

from fastapi.testclient import TestClient

import app.main as main
from app.triage import triage_symptoms


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


def test_triage_returns_possible_directions_with_safety_disclaimer():
    result = triage_symptoms('反复胸痛', ai_consent=True, environ={})

    assert result.disclaimer
    assert result.directions
    assert result.directions[0].department
    assert result.directions[0].basis
    assert result.directions[0].possible_diseases
    assert result.is_diagnosis is False


def test_triage_does_not_show_unrelated_neurology_aliases_for_brain_hemorrhage():
    result = triage_symptoms('脑溢血', ai_consent=False, environ={})

    assert result.explicit_disease_input is True
    assert result.directions[0].possible_diseases == ['脑溢血']
    assert '渐冻症' not in result.directions[0].possible_diseases
    assert '肌萎缩侧索硬化' not in result.directions[0].possible_diseases


def test_ai_triage_does_not_replace_explicit_brain_hemorrhage_with_unrelated_disease():
    payload = {
        'choices': [{'message': {'content': json.dumps({
            'summary': '需要尽快评估',
            'directions': [{
                'key': 'neurology', 'title': '神经内科方向', 'likelihood': '较高',
                'basis': '需要结合检查判断', 'department': '神经内科',
                'possible_diseases': ['渐冻症', '肌萎缩侧索硬化'], 'urgent_warning': '',
            }],
            'urgent_warning': '',
        }, ensure_ascii=False)}}],
    }

    result = triage_symptoms(
        '脑溢血', ai_consent=True, environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result.directions[0].possible_diseases == ['脑溢血']


def test_triage_parses_deepseek_directions_and_caps_at_three():
    payload = {
        'choices': [{'message': {'content': json.dumps({
            'summary': '症状可能涉及心血管系统，需要结合检查判断。',
            'directions': [
                {'key': 'cardiovascular', 'title': '心血管系统问题', 'likelihood': '较高', 'basis': '胸痛与心血管症状相关', 'department': '心血管内科', 'urgent_warning': '突发加重需急诊'},
                {'key': 'respiratory', 'title': '呼吸系统问题', 'likelihood': '中等', 'basis': '需排查呼吸系统原因', 'department': '呼吸内科', 'urgent_warning': ''},
                {'key': 'digestive', 'title': '消化系统问题', 'likelihood': '较低', 'basis': '部分胸部不适可能相关', 'department': '消化内科', 'urgent_warning': ''},
                {'key': 'extra', 'title': '其他', 'likelihood': '低', 'basis': 'x', 'department': '全科', 'urgent_warning': ''},
            ],
            'urgent_warning': '如持续胸痛请尽快就医',
        }, ensure_ascii=False)}}],
    }

    result = triage_symptoms('反复胸痛', ai_consent=True, environ={'DEEPSEEK_API_KEY': 'test'}, transport=lambda *args, **kwargs: FakeResponse(payload))

    assert result.ai_used is True
    assert len(result.directions) == 3
    assert result.directions[0].title == '心血管系统问题'
    assert result.directions[0].possible_diseases == []


def test_triage_preserves_the_ai_likelihood_label():
    payload = {
        'choices': [{'message': {'content': json.dumps({
            'summary': '\u9700\u8981\u8fdb\u4e00\u6b65\u8bc4\u4f30',
            'directions': [{
                'key': 'neurology', 'title': '\u795e\u7ecf\u5185\u79d1\u65b9\u5411', 'likelihood': '\u4e2d',
                'basis': '\u75c7\u72b6\u9700\u8981\u7ed3\u5408\u66f4\u591a\u4fe1\u606f\u8bc4\u4f30', 'department': '\u795e\u7ecf\u5185\u79d1',
                'urgent_warning': '',
            }],
            'urgent_warning': '',
        }, ensure_ascii=False)}}],
    }

    result = triage_symptoms(
        '\u5934\u75db', ai_consent=True, environ={'DEEPSEEK_API_KEY': 'test'},
        transport=lambda *args, **kwargs: FakeResponse(payload),
    )

    assert result.directions[0].likelihood == '\u4e2d'


def test_triage_endpoint_does_not_start_hospital_search_until_direction_confirmed(monkeypatch):
    client = TestClient(main.app)
    response = client.post('/v1/triage', json={'query': '反复胸痛', 'ai_consent': True})
    assert response.status_code == 200
    assert response.json()['directions']

    monkeypatch.setattr(main, '_cached_external_search', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('search should not run')))


def test_realtime_request_accepts_confirmed_direction():
    client = TestClient(main.app)
    main.REALTIME_SEARCH_CACHE._values.clear()
    main.REALTIME_SEARCH_BUDGET._calls.clear()
    response = client.post('/v1/realtime-hospital-search', json={
        'query': '反复胸痛',
        'location': {'province': '广东省', 'city': '广州市', 'district': '天河区'},
        'scope': 'district',
        'ai_consent': True,
        'confirmed_direction': '心血管系统问题',
    })
    assert response.status_code != 422


def test_generic_oncology_query_does_not_accept_thoracic_surgery_as_primary_direction():
    payload = {
        'choices': [{'message': {'content': json.dumps({
            'summary': '\u53ef\u80fd\u6d89\u53ca\u80bf\u7624\u65b9\u5411',
            'directions': [{
                'key': 'oncology', 'title': '\u53ef\u80fd\u6d89\u53ca\u80f8\u5916\u79d1\u65b9\u5411',
                'likelihood': '\u8f83\u9ad8', 'basis': '\u80bf\u7624\u6cbb\u7597\u53ef\u80fd\u9700\u624b\u672f',
                'department': '\u80f8\u5916\u79d1', 'urgent_warning': '',
            }], 'urgent_warning': '',
        }, ensure_ascii=False)}}],
    }
    result = triage_symptoms('\u80bf\u7624\u6cbb\u7597', ai_consent=True, environ={'DEEPSEEK_API_KEY': 'test'}, transport=lambda *args, **kwargs: FakeResponse(payload))

    assert result.directions[0].department == '\u80bf\u7624\u5185\u79d1'
