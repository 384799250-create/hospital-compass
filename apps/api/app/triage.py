"""Safety-first symptom triage before hospital matching."""

import json
import os
from typing import Callable, Mapping, Sequence
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.disease_profiles import PROFILES, has_explicit_disease, matched_explicit_disease_terms, profile_for_query

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'


class TriageDirection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    key: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=100)
    likelihood: str = Field(min_length=1, max_length=30)
    basis: str = Field(min_length=1, max_length=240)
    department: str = Field(min_length=1, max_length=60)
    possible_diseases: list[str] = Field(default_factory=list, max_length=5)
    urgent_warning: str = Field(default='', max_length=240)


class TriageResponse(BaseModel):
    summary: str = Field(max_length=500)
    directions: list[TriageDirection] = Field(max_length=3)
    urgent_warning: str = Field(default='', max_length=240)
    disclaimer: str
    is_diagnosis: bool = False
    ai_used: bool = False
    explicit_disease_input: bool = False


class _DeepSeekOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    summary: str = Field(max_length=500)
    directions: list[TriageDirection]
    urgent_warning: str = Field(default='', max_length=240)


DISCLAIMER = '以上是基于症状的健康信息整理，不是医学诊断；如症状严重、突然加重或出现危险信号，请及时联系急救或就近就医。'
SYSTEM_PROMPT = (
    '你是中文健康信息分流助手，不做医学诊断。只返回 JSON 对象，字段为 summary、directions、urgent_warning。'
    'directions 最多 3 项，每项包含 key、title、likelihood、basis、department、possible_diseases、urgent_warning。possible_diseases 是 0 到 5 个可能涉及的疾病名称，只作方向参考，不是诊断。'
    '根据用户症状说明可能涉及的疾病方向及依据，使用谨慎措辞，不给出用药、治疗或确定诊断。'
)


def _fallback(query: str) -> TriageResponse:
    profile = profile_for_query(query)
    if profile.key == 'general':
        direction = TriageDirection(
            key='general', title='需要进一步评估的健康问题', likelihood='待评估',
            basis='当前症状信息不足以区分具体疾病方向，建议先由全科或相关专科进行初步评估。',
            department='全科医学科', possible_diseases=[], urgent_warning='',
        )
        return TriageResponse(summary='当前症状需要结合病史、体格检查或检查结果进一步判断。', directions=[direction], disclaimer=DISCLAIMER)
    matched_terms = matched_explicit_disease_terms(query)
    possible_diseases = list(matched_terms) if matched_terms else list(profile.keywords[:3])
    basis_term = matched_terms[0] if matched_terms else profile.keywords[0]
    direction = TriageDirection(
        key=profile.key,
        title=f'可能涉及{profile.departments[0]}方向',
        likelihood='需要评估',
        basis=f'症状与{basis_term}等表现存在相关性，仍需医生结合完整病史判断。',
        department=profile.departments[0],
        possible_diseases=possible_diseases,
        urgent_warning='；'.join(profile.urgent_terms),
    )
    return TriageResponse(summary='根据症状关键词整理出以下就医方向，不能替代医生诊断。', directions=[direction], disclaimer=DISCLAIMER)


def _sanitize_directions(query: str, directions: Sequence[TriageDirection], fallback: TriageDirection) -> list[TriageDirection]:
    profile = profile_for_query(query)
    if profile.key != 'oncology':
        return list(directions)
    thoracic_specific = any(term in query for term in ('肺癌', '肺部结节', '胸部肿块', '纵隔', '胸腔'))
    if thoracic_specific:
        return list(directions)
    allowed = set(profile.departments[:3])
    filtered = [direction for direction in directions if direction.department in allowed]
    return filtered or [fallback]


def triage_symptoms(
    query: str,
    ai_consent: bool,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Callable[..., object] | None = None,
) -> TriageResponse:
    fallback = _fallback(query)
    explicit_disease_input = has_explicit_disease(query)
    settings = os.environ if environ is None else environ
    if not ai_consent or not settings.get('DEEPSEEK_API_KEY'):
        return fallback.model_copy(update={'explicit_disease_input': explicit_disease_input})
    body = json.dumps({
        'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': query}],
        'response_format': {'type': 'json_object'},
    }, ensure_ascii=False).encode('utf-8')
    request = Request(DEEPSEEK_URL, data=body, headers={
        'Authorization': f"Bearer {settings['DEEPSEEK_API_KEY']}",
        'Content-Type': 'application/json',
    }, method='POST')
    send = urlopen if transport is None else transport
    try:
        with send(request, timeout=10.0) as response:
            if not 200 <= getattr(response, 'status', 200) < 300:
                return fallback.model_copy(update={'explicit_disease_input': explicit_disease_input})
            payload = json.loads(response.read().decode('utf-8'))
        raw = json.loads(payload['choices'][0]['message']['content'])
        raw['directions'] = list(raw.get('directions') or [])[:3]
        parsed = _DeepSeekOutput.model_validate(raw)
        if not parsed.directions:
            return fallback.model_copy(update={'explicit_disease_input': explicit_disease_input})
    except (OSError, TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return fallback.model_copy(update={'explicit_disease_input': explicit_disease_input})
    sanitized_directions = _sanitize_directions(query, parsed.directions, fallback.directions[0])
    if explicit_disease_input:
        matched_terms = list(matched_explicit_disease_terms(query))
        if matched_terms:
            sanitized_directions = [
                direction.model_copy(update={'possible_diseases': matched_terms})
                for direction in sanitized_directions
            ]
    return TriageResponse(summary=parsed.summary, directions=sanitized_directions, urgent_warning=parsed.urgent_warning, disclaimer=DISCLAIMER, is_diagnosis=False, ai_used=True, explicit_disease_input=explicit_disease_input)
