import io
import json

from app.web_ranker import synthesize_hospital_results


def test_synthesis_preserves_evidence_fields_from_deepseek():
    results = [{
        'id': 'hospital-1',
        'name': '广东省人民医院',
        'city': '广州市',
        'score': 70,
        'score_reasons': ['geography=100'],
        'sources': [{
            'title': '心血管内科',
            'url': 'https://example.org/cardiology',
            'snippet': '冠心病诊疗中心',
            'fetched_at': '2026-08-07T00:00:00+00:00',
        }],
        'source_urls': ['https://example.org/cardiology'],
        'fetched_at': '2026-08-07T00:00:00+00:00',
        'registration_url': None,
    }]

    def transport(request, timeout):
        payload = {
            'choices': [{
                'message': {'content': json.dumps({'results': [{
                    'id': 'hospital-1',
                    'name': '广东省人民医院',
                    'department': '心血管内科',
                    'address': '广州市越秀区',
                    'score': 96,
                    'reason': '心绞痛与冠心病方向高度匹配',
                    'core_advantages': '冠心病诊疗中心实力突出',
                    'match_reason': '心血管内科与症状高度匹配',
                    'evidence_status': '有公开资料',
                    'score_breakdown': {
                        'specialty': 98,
                        'hospital_strength': 96,
                        'geography': 100,
                        'completeness': 90,
                        'accessibility': 80,
                    },
                }]}, ensure_ascii=False)}
            }],
        }
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='心绞痛',
        location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        directions=['心血管内科'],
        results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'},
        transport=transport,
    )

    assert output is not None
    assert output[0]['core_advantages'] == '冠心病诊疗中心实力突出'
    assert output[0]['match_reason'] == '心血管内科与症状高度匹配'
    assert output[0]['evidence_status'] == '有公开资料'
    assert output[0]['score_breakdown']['specialty'] == 98
