import io
import json

from app.web_ranker import _extract_json_object, _fallback_hospital_strength, _parse_plain_text_results, synthesize_hospital_results


def test_extract_json_object_accepts_markdown_and_trailing_text():
    assert _extract_json_object('说明如下：```json\n{"results": []}\n```\n以上。') == {'results': []}


def test_parse_plain_text_results_maps_by_hospital_id():
    candidates = [{'id': 'h1', 'name': '医院一', 'address': '地址一'}]
    output = _parse_plain_text_results('医院ID：h1\n核心优势：国家重点专科\n匹配理由：与当前方向相关。', candidates)
    assert output[0]['core_advantages'] == '国家重点专科'
    assert output[0]['address'] == '地址一'


def test_parse_plain_text_results_accepts_real_chinese_labels_and_ascii_colons():
    candidates = [{'id': 'h1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'address': '\u5e7f\u5dde\u5e02'}]
    content = (
        '\u533b\u9662ID: h1\n'
        '\u6838\u5fc3\u4f18\u52bf: \u5fc3\u5185\u79d1\u4e3a\u7701\u7ea7\u91cd\u70b9\u4e13\u79d1\n'
        '\u5339\u914d\u7406\u7531: \u513f\u7ae5\u53d1\u70ed\u54b3\u55fd\u4e0e\u513f\u79d1\u65b9\u5411\u76f8\u5173\n'
    )
    output = _parse_plain_text_results(content, candidates)
    assert len(output) == 1
    assert output[0]['core_advantages'].startswith('\u5fc3\u5185\u79d1')


def test_synthesis_falls_back_to_plain_text_when_preamble_contains_json_braces():
    candidates = [{'id': 'h1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'score': 80, 'sources': []}]
    content = (
        'We need answer in the requested format. Example {"results": []}.\n\n'
        '\u533b\u9662ID: h1\n\u6838\u5fc3\u4f18\u52bf: \u513f\u79d1\u8bc1\u636e\n\u5339\u914d\u7406\u7531: \u513f\u7ae5\u53d1\u70ed\u65b9\u5411\u76f8\u5173\n'
    )

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': content}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='\u513f\u7ae5\u53d1\u70ed', location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        directions=['\u513f\u79d1'], results=candidates,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )
    assert output is not None


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
    assert output[0]['core_advantages'].startswith('冠心病诊疗中心')
    assert output[0]['match_reason'] == '心血管内科与症状高度匹配'
    assert output[0]['evidence_status'] == '有公开资料'
    assert output[0]['score_breakdown']['specialty'] == 98


def test_synthesis_orders_final_results_by_deterministic_score():
    results = [
        {'id': 'high', 'name': '高分医院', 'city': '广州市', 'score': 77.17, 'sources': [], 'source_urls': [], 'fetched_at': '2026-08-11T00:00:00+00:00'},
        {'id': 'low', 'name': '低分医院', 'city': '广州市', 'score': 52.47, 'sources': [], 'source_urls': [], 'fetched_at': '2026-08-11T00:00:00+00:00'},
    ]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [
            {'id': 'low', 'name': '低分医院', 'score': 52.47, 'reason': '有匹配资料'},
            {'id': 'high', 'name': '高分医院', 'score': 77.17, 'reason': '有匹配资料'},
        ]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='关节疼痛', location={'province': '广东省', 'city': '广州市', 'district': '番禺区'},
        directions=['骨科'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert [item['id'] for item in output] == ['high', 'low']


def test_synthesis_fills_factual_fields_when_model_returns_only_text_fields():
    results = [{
        'id': 'hospital-1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'city': '\u5e7f\u5dde\u5e02',
        'address': '\u5e7f\u5dde\u5e02\u4e2d\u5c71\u4e8c\u8def', 'score': 82,
        'sources': [],
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1',
            'core_advantages': '\u513f\u79d1\u4e13\u79d1\u8bc1\u636e',
            'match_reason': '\u4e0e\u513f\u7ae5\u75c7\u72b6\u65b9\u5411\u76f8\u5173',
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='\u513f\u7ae5\u53d1\u70ed', location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        directions=['\u513f\u79d1'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert output[0]['name'] == '\u6d4b\u8bd5\u533b\u9662'
    assert output[0]['score'] == 82
    assert output[0]['core_advantages'].startswith('\u513f\u79d1\u4e13\u79d1\u8bc1\u636e')
    assert output[0]['core_advantages'].endswith('\u5f53\u524d\u516c\u5f00\u4fe1\u606f\u4e2d\u672a\u89c1\u4e0e\u513f\u79d1\u65b9\u5411\u76f4\u63a5\u5bf9\u5e94\u7684\u4e13\u79d1\u6392\u540d\uff0c\u5efa\u8bae\u7ed3\u5408\u513f\u79d1\u95e8\u8bca\u5b89\u6392\u8fdb\u4e00\u6b65\u786e\u8ba4\u3002')


def test_synthesis_reads_reasoning_content_when_message_content_is_empty():
    results = [{'id': 'hospital-1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'city': '\u5e7f\u5dde\u5e02', 'score': 82, 'sources': []}]

    def transport(request, timeout):
        payload = {'choices': [{'message': {
            'content': '',
            'reasoning_content': '\u533b\u9662ID: hospital-1\n\u6838\u5fc3\u4f18\u52bf: \u513f\u79d1\u8bc1\u636e\n\u5339\u914d\u7406\u7531: \u75c7\u72b6\u76f8\u5173',
        }}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='\u513f\u7ae5\u53d1\u70ed', location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        directions=['\u513f\u79d1'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert output[0]['name'] == '\u6d4b\u8bd5\u533b\u9662'


def test_synthesis_replaces_internal_reasoning_with_user_facing_match_reason():
    results = [{
        'id': 'hospital-1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'city': '\u5e7f\u5dde\u5e02',
        'score': 82, 'address': '\u5e7f\u5dde\u5e02\u756a\u79ba\u533a',
        'sources': [{'snippet': '\u513f\u79d1\u4e13\u79d1\u516c\u5f00\u8d44\u6599', 'url': 'https://example.org'}],
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1',
            'core_advantages': '\u513f\u79d1\u4e13\u79d1\u516c\u5f00\u8d44\u6599',
            'match_reason': '\u7528\u6237\u67e5\u8be2\u4e3a\u513f\u7ae5\u53d1\u70ed\uff0c\u9700\u8981\u7406\u89e3\u4efb\u52a1\uff0c\u5019\u9009\u5217\u8868\u4e2d\u5305\u542b\u8be5\u533b\u9662',
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='\u513f\u7ae5\u53d1\u70ed', location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u756a\u79ba\u533a'},
        directions=['\u513f\u79d1'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )
    assert output is not None
    assert '\u7528\u6237\u67e5\u8be2\u4e3a' not in output[0]['match_reason']
    assert '\u5019\u9009\u5217\u8868' not in output[0]['match_reason']


def test_synthesis_keeps_candidates_deepseek_does_not_return():
    results = [
        {
            'id': 'hospital-1', 'name': '广东省人民医院', 'city': '广州市', 'score': 90,
            'sources': [{'title': '医院官网', 'url': 'https://example.org/1', 'snippet': '心血管中心', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
        },
        {
            'id': 'hospital-2', 'name': '广州市第一人民医院', 'city': '广州市', 'score': 80,
            'sources': [{'title': '医院官网', 'url': 'https://example.org/2', 'snippet': '心血管内科', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
        },
    ]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1', 'name': '广东省人民医院', 'score': 96,
            'department': '心血管内科', 'address': '', 'reason': '来源充分',
            'core_advantages': '心血管中心', 'match_reason': '方向匹配',
            'evidence_status': '有公开资料', 'score_breakdown': {},
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='心绞痛', location={'province': '广东省', 'city': '广州市', 'district': '南山区'},
        directions=['心血管内科'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert [item['id'] for item in output] == ['hospital-1', 'hospital-2']


def test_synthesis_does_not_overwrite_grounded_address_or_advantage():
    results = [{
        'id': 'hospital-1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'city': '\u5e7f\u5dde\u5e02', 'score': 90,
        'address': '\u5e7f\u5dde\u5e02\u4e2d\u5c71\u4e8c\u8def106\u53f7',
        'core_advantages': '\u4e09\u7ea7\u7532\u7b49\uff1b\u5fc3\u5185\u79d1',
        'sources': [{'title': '\u516c\u5f00\u8d44\u6599', 'url': 'https://example.org/1', 'snippet': '\u5df2\u77e5\u8d44\u6599', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1', 'name': '\u6d4b\u8bd5\u533b\u9662', 'department': '',
            'address': '\u5176\u4ed6\u5730\u5740', 'score': 90, 'reason': '',
            'core_advantages': '\u5176\u4ed6\u4f18\u52bf', 'match_reason': '',
            'evidence_status': '', 'score_breakdown': {},
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='\u5fc3\u8840\u7ba1\u75be\u75c5', location={'province': '\u5e7f\u4e1c\u7701', 'city': '\u5e7f\u5dde\u5e02', 'district': '\u8d8a\u79c0\u533a'},
        directions=['\u5fc3\u8840\u7ba1\u5185\u79d1'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert output[0]['address'] == '\u5e7f\u5dde\u5e02\u4e2d\u5c71\u4e8c\u8def106\u53f7'
    assert output[0]['core_advantages'] == '\u4e09\u7ea7\u7532\u7b49\uff1b\u5fc3\u5185\u79d1'


def test_synthesis_uses_richer_advantage_when_it_repeats_source_evidence():
    results = [{
        'id': 'hospital-1', 'name': '测试医院', 'city': '广州市', 'score': 90,
        'core_advantages': '三级甲等；心内科',
        'sources': [{'title': '公开资料', 'url': 'https://example.org/1', 'snippet': '心血管专科公开介绍', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1', 'name': '测试医院', 'department': '心内科', 'address': '', 'score': 90,
            'reason': '症状与心内科方向相关',
            'core_advantages': '公开资料显示，该院设有心血管专科并提供心内科相关诊疗服务。作为三级甲等医院，其已公开的心血管专科信息可作为本次选院的参考。',
            'match_reason': '用户症状与心内科方向相关，且医院位于当前城市范围。',
            'evidence_status': '有公开资料', 'score_breakdown': {},
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='心血管症状', location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        directions=['心内科'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output[0]['core_advantages'].startswith('公开资料显示')
    assert output[0]['match_reason'].startswith('用户症状')


def test_synthesis_rejects_labeled_public_introduction_in_core_advantages():
    introduction = '该院为妇女和儿童提供全周期医疗保健服务，并开展与妇产科相关的专业诊疗。'
    results = [{
        'id': 'hospital-1', 'name': '测试妇幼医院', 'city': '广州市', 'tier': '三级甲等', 'score': 90,
        'sources': [{'title': '妇产科公开资料', 'url': 'https://example.org/1', 'snippet': '妇产科专科信息', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
        'database_evidence': {'public_introduction': introduction},
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1', 'name': '测试妇幼医院', 'department': '妇产科', 'address': '', 'score': 90,
            'reason': '妇产科方向相关',
            'core_advantages': f'公开简介：{introduction}',
            'match_reason': '妇产科与当前就医方向相关。',
            'evidence_status': '有公开资料', 'score_breakdown': {},
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='妇产科就医', location={'province': '广东省', 'city': '广州市', 'district': '越秀区'},
        directions=['妇产科'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert '公开简介：' not in output[0]['core_advantages']
    assert introduction not in output[0]['core_advantages']
    assert output[0]['core_advantages'].endswith('当前公开信息中未见与妇产科方向直接对应的专科排名，建议结合妇产科门诊安排进一步确认。')


def test_web_fallback_core_advantages_uses_natural_credentials_and_type_summary():
    advantages = _fallback_hospital_strength({
        'tier': '三级甲等',
        'hospital_type': '',
        'specialty_evidence': [],
        'database_evidence': {
            'public_introduction': '广东祈福医院是中国首家通过国际JCI认证的大型三甲中西医结合医院，也是中国首家获CIHA国际认证的民营医院，集医疗、科研、教学、预防保健为一体。',
            'rankings': [],
        },
    }, ['儿科'])

    assert '三级甲等中西医结合医院' in advantages
    assert '医院广东祈福医院' not in advantages
    assert '已通过国际JCI认证和CIHA国际认证' in advantages
    assert advantages.endswith('当前公开信息中未见与儿科方向直接对应的专科排名，建议结合儿科门诊安排进一步确认。')


def test_synthesis_rejects_unverified_promotional_core_advantage_claims():
    results = [{
        'id': 'hospital-1', 'name': '测试医院', 'city': '广州市', 'tier': '三级甲等', 'score': 90,
        'sources': [{'title': '儿科资料', 'url': 'https://example.org/pediatrics', 'snippet': '儿科相关诊疗服务', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1', 'name': '测试医院', 'department': '儿科', 'address': '', 'score': 90,
            'core_advantages': '该院儿科综合服务能力较强，能够为儿童提供优质诊疗。',
            'match_reason': '儿科方向相关。',
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='孩子发热', location={'province': '广东省', 'city': '广州市', 'district': '番禺区'},
        directions=['儿科'], results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert '综合服务能力较强' not in output[0]['core_advantages']
    assert '优质诊疗' not in output[0]['core_advantages']


def test_synthesis_fallback_prefers_directional_ranking_over_generic_ranking():
    results = [{
        'id': 'hospital-1',
        'name': '测试医院',
        'city': '广州市',
        'tier': '三级甲等',
        'score': 90,
        'core_advantages': '',
        'sources': [{'title': '医院资料', 'url': 'https://example.org', 'snippet': '儿科相关资料', 'fetched_at': '2026-08-07T00:00:00+00:00'}],
        'specialty_evidence': [{
            'specialty': '儿科',
            'rank': 15,
            'year': 2024,
            'ranking_scope': '大区级',
            'ranking_name': '专科',
            'ranking_source_name': '2024年度华南地区中医儿科专科声誉排行榜',
            'ranking_publisher': '复旦大学医院管理研究所',
        }, {
            'specialty': '',
            'rank': 9,
            'year': 2024,
            'ranking_scope': '全国级',
            'ranking_name': '综合',
            'ranking_source_name': '2024全国医院互联网口碑排行榜',
            'ranking_publisher': '好大夫在线',
        }],
        'database_evidence': {
            'public_introduction': '医院临床科室齐全，设有内科、外科、妇产科、儿科、急诊科等多个临床医技科室，诊疗范围覆盖常见病、多发病及疑难重症。',
        },
    }]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': json.dumps({'results': [{
            'id': 'hospital-1',
            'name': '测试医院',
            'department': '儿科',
            'address': '',
            'score': 90,
            'reason': '儿科方向相关',
            'core_advantages': '医院综合排名第9名。',
            'match_reason': '儿科方向相关。',
        }]}, ensure_ascii=False)}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='孩子发热咳嗽',
        location={'province': '广东省', 'city': '广州市', 'district': '番禺区'},
        directions=['儿科或全科'],
        results=results,
        environ={'DEEPSEEK_API_KEY': 'test-key'},
        transport=transport,
    )

    assert output is not None
    assert '《2024年度华南地区中医儿科专科声誉排行榜》' in output[0]['core_advantages']
    assert '全国医院互联网口碑排行榜' not in output[0]['core_advantages']
    assert '三级甲等医院' in output[0]['core_advantages']
    assert '临床科室齐全' in output[0]['core_advantages']


def test_plain_text_parser_accepts_markdown_labels_without_a_space_in_hospital_id():
    candidates = [{'id': 'h1', 'name': '测试医院', 'address': '广州市'}]
    content = '**医院ID：** h1\n**核心优势：** 肿瘤内科为重点专科\n**匹配理由：** 与肿瘤治疗方向相关'

    output = _parse_plain_text_results(content, candidates)

    assert len(output) == 1
    assert output[0]['core_advantages'] == '肿瘤内科为重点专科'


def test_synthesis_keeps_deterministic_candidates_when_model_has_no_parseable_records():
    candidates = [{'id': 'h1', 'name': '测试医院', 'score': 88.0, 'sources': [], 'source_urls': [], 'fetched_at': '2026-08-11T00:00:00+00:00'}]

    def transport(request, timeout):
        payload = {'choices': [{'message': {'content': '无法按指定格式输出。'}}]}
        return type('Response', (), {
            'status': 200,
            'read': lambda self: json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            '__enter__': lambda self: self,
            '__exit__': lambda self, *args: None,
        })()

    output = synthesize_hospital_results(
        query='肿瘤治疗', location={'province': '广东省', 'city': '广州市', 'district': '广州市'},
        directions=['肿瘤内科'], results=candidates,
        environ={'DEEPSEEK_API_KEY': 'test-key'}, transport=transport,
    )

    assert output is not None
    assert output[0]['id'] == 'h1'
