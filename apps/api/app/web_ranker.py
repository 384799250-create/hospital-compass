"""Source-grounded DeepSeek synthesis for realtime hospital search."""

import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'


class SynthesizedHospital(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=120)
    score: float = Field(ge=0, le=100)
    reason: str | None = Field(default=None, max_length=240)
    core_advantages: str | None = Field(default=None, max_length=300)
    match_reason: str | None = Field(default=None, max_length=300)
    evidence_status: str | None = Field(default=None, max_length=80)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    specialty_evidence: list[dict[str, object]] = Field(default_factory=list)


class SynthesisPayload(BaseModel):
    results: list[SynthesizedHospital] = Field(max_length=10)


SYSTEM_PROMPT = (
    '你是医疗信息检索结果整理器。只能根据提供的网页资料整理，不得补写资料中没有的医院、地址、科室、医生或评分依据。'
    '请输出严格 JSON：{"results":[{"id":"候选id","name":"真实医院名称","department":"相关科室","address":"资料中的地址或空字符串",'
    '"score":0到100的数字,"reason":"不超过100字的来源依据"}]}。'
    'name 必须是医院实体名称，不要复制搜索标题中的营销关键词；id 必须来自候选资料。'
)

# Keep the prompt ASCII-safe so Windows process encoding cannot corrupt the
# JSON contract sent to DeepSeek.
SYSTEM_PROMPT = (
    'You are a Chinese hospital ranking editor. Return strict JSON only. '
    'Use candidate evidence and the user query/location to rank up to ten hospitals. '
    'Never invent addresses, doctors, departments, scores, or URLs. '
    'Every result must contain id, name, department, address, score, reason, '
    'core_advantages, match_reason, evidence_status, and score_breakdown. '
    'Write core_advantages and match_reason in concise Chinese. '
    'score_breakdown keys must be specialty, hospital_strength, geography, completeness, accessibility. '
    'Treat each candidate score and score_breakdown as a deterministic baseline. '
    'Do not place a generic local hospital above a hospital with explicit national or provincial medical-center evidence unless the sources clearly show stronger specialty evidence. '
    'Use 暂无公开资料 when a fact is unavailable.'
)


def synthesize_hospital_results(
    *,
    query: str,
    location: Mapping[str, str],
    directions: Sequence[str],
    results: Sequence[Mapping[str, object]],
    environ: Mapping[str, str] | None = None,
    transport: Callable[..., object] | None = None,
) -> list[dict[str, object]] | None:
    """Ask DeepSeek to normalize and rank only the already searched candidates."""
    settings = os.environ if environ is None else environ
    api_key = settings.get('DEEPSEEK_API_KEY')
    if not api_key or not results:
        return None
    candidate_payload = [
        {
            'id': item.get('id'),
            'name': item.get('name'),
            'city': item.get('city'),
            'address': item.get('address'),
            'core_advantages': item.get('core_advantages'),
            'score': item.get('score'),
            'score_breakdown': item.get('score_breakdown', {}),
            'sources': item.get('sources', []),
            'specialty_evidence': item.get('specialty_evidence', []),
        }
        for item in results[:20]
    ]
    user_prompt = json.dumps({
        'query': query,
        'location': dict(location),
        'directions': list(directions),
        'candidates': candidate_payload,
    }, ensure_ascii=False)
    body = json.dumps({
        'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'response_format': {'type': 'json_object'},
        'temperature': 0.1,
    }, ensure_ascii=False).encode('utf-8')
    request = Request(DEEPSEEK_URL, data=body, headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }, method='POST')
    send = urlopen if transport is None else transport
    try:
        with send(request, timeout=20.0) as response:
            if not 200 <= getattr(response, 'status', 200) < 300:
                return None
            payload = json.loads(response.read().decode('utf-8'))
        content = payload['choices'][0]['message']['content'].strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        parsed = SynthesisPayload.model_validate(json.loads(content))
    except (HTTPError, OSError, TypeError, URLError, UnicodeDecodeError,
            json.JSONDecodeError, KeyError, IndexError, ValidationError) as exc:
        logger.warning('deepseek_web_synthesis_failed type=%s', type(exc).__name__)
        return None

    by_id = {str(item.get('id')): dict(item) for item in results}
    synthesized = []
    synthesized_ids: set[str] = set()
    for item in parsed.results:
        base = by_id.get(item.id)
        if base is None:
            continue
        base['name'] = item.name
        base['score'] = round(float(base.get('score') or item.score), 2)
        base['score_reasons'] = [item.reason] if item.reason else base.get('score_reasons', [])
        base['department'] = item.department or ''
        base['address'] = str(base.get('address') or '')
        base['core_advantages'] = base.get('core_advantages') or next(
            (source.get('snippet') for source in base.get('sources', []) if source.get('snippet')),
            '暂无公开资料',
        )
        base['match_reason'] = item.match_reason or item.reason or '根据症状、科室和地理范围综合匹配。'
        base['evidence_status'] = item.evidence_status or ('有公开资料' if base.get('sources') else '暂无公开资料')
        base['score_breakdown'] = base.get('score_breakdown') or item.score_breakdown
        base['specialty_evidence'] = base.get('specialty_evidence') or item.specialty_evidence
        synthesized.append(base)
        synthesized_ids.add(item.id)
    # DeepSeek may omit valid candidates because of response-length limits.
    # Keep the deterministic local candidates after the AI-ranked entries so
    # search recall is never reduced by the synthesis step.
    for base in results:
        candidate_id = str(base.get('id'))
        if candidate_id not in synthesized_ids:
            synthesized.append(dict(base))
    return synthesized[:10] or None
