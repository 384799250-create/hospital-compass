"""Source-grounded DeepSeek synthesis for realtime hospital search."""

import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
LAST_SYNTHESIS_FAILURE: str | None = None


class SynthesizedHospital(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=240)
    score: float = Field(ge=0, le=100)
    reason: str | None = Field(default=None, max_length=500)
    core_advantages: str | None = Field(default=None, max_length=600)
    match_reason: str | None = Field(default=None, max_length=600)
    evidence_status: str | None = Field(default=None, max_length=120)
    score_breakdown: dict[str, object] = Field(default_factory=dict)
    specialty_evidence: list[dict[str, object]] = Field(default_factory=list)


class SynthesisPayload(BaseModel):
    results: list[SynthesizedHospital] = Field(max_length=20)


SYSTEM_PROMPT = (
    '你是医疗信息检索结果整理器。只能根据提供的网页资料整理，不得补写资料中没有的医院、地址、科室、医生或评分依据。'
    '请输出严格 JSON：{"results":[{"id":"候选id","name":"真实医院名称","department":"相关科室","address":"资料中的地址或空字符串",'
    '"score":0到100的数字,"reason":"不超过100字的来源依据"}]}。'
    'name 必须是医院实体名称，不要复制搜索标题中的营销关键词；id 必须来自候选资料。'
)

# Keep the prompt ASCII-safe so Windows process encoding cannot corrupt the
# JSON contract sent to DeepSeek.
SYSTEM_PROMPT = (
    'You are a Chinese hospital ranking editor. Return plain text blocks only, one block per hospital. '
    'Each block must use exactly these labels: 医院ID、核心优势、匹配理由. Do not return JSON or Markdown tables. '
    'Do not output your analysis, planning, candidate-list discussion, instructions, or phrases such as 用户查询为、需要理解任务、候选列表. '
    'The 匹配理由 field must directly explain why this hospital fits the user request in one or two readable sentences. '
    'Use candidate evidence and the user query/location to rank up to ten hospitals. '
    'If candidates are provided, results MUST contain at least one item and may contain up to ten items; never return an empty results array. '
    'Copy each selected candidate id exactly and return only ids that appear in candidates. '
    'Never invent addresses, doctors, departments, scores, or URLs. '
    'Treat candidate name, address, city, tier, score, rankings, credentials, services, and source URLs as factual fields. '
    'Do not rewrite or replace those factual fields; only organize explanatory text around them. '
    'For each hospital return only these three labeled fields: 医院ID, 核心优势, 匹配理由. '
    'Do not repeat factual fields such as name, address, score, or ranking as editable output; '
    'the application fills those from the candidate record. '
    'Write core_advantages in two or three natural Chinese sentences, ideally 70 to 140 Chinese characters. '
    'Start with verified specialty evidence relevant to the requested direction, then add the tier, general ranking, or factual service positioning when available. '
    'Public introductions are supporting evidence only: extract one factual point when needed, never append the original text. '
    'Do not use the label 公开简介, semicolon-separated field lists, repeated hospital names, slogans, generic praise, or capabilities not present in the candidate evidence. '
    'When direct specialty evidence is unavailable, put this as the final sentence: 当前公开信息中未见与该方向直接对应的专科排名，建议结合该方向门诊安排进一步确认。 Do not put this reminder at the beginning. '
    'Write match_reason as a concise paragraph connecting the symptom, department, evidence, and requested location. '
    'Prefer concrete evidence such as ranking scope and rank, named key specialties, medical centers, and treatment capabilities; '
    'never replace missing evidence with generic praise. '
    'score_breakdown keys must be specialty, hospital_strength, geography, completeness, accessibility. '
    'Treat each candidate score and score_breakdown as a deterministic baseline. '
    'Do not place a generic local hospital above a hospital with explicit national or provincial medical-center evidence unless the sources clearly show stronger specialty evidence. '
    'Use 暂无公开资料 when a fact is unavailable.'
)


def _evidence_tokens(base: Mapping[str, object], directions: Sequence[str], query: str) -> tuple[str, ...]:
    text = ' '.join([
        str(base.get('core_advantages') or ''),
        ' '.join(str(source.get('snippet') or '') for source in base.get('sources', []) if isinstance(source, Mapping)),
        ' '.join(str(item.get('specialty') or '') for item in base.get('specialty_evidence', []) if isinstance(item, Mapping)),
        ' '.join(directions),
        query,
    ])
    return tuple(dict.fromkeys(token for token in re.findall(r'[\u4e00-\u9fff]{2,}', text) if len(token) >= 2))


def _grounded_generated_text(value: str | None, base: Mapping[str, object], directions: Sequence[str], query: str) -> str | None:
    if not value or _is_internal_reasoning(value) or _has_conflicting_specialty(value, base, directions) or not _has_relevant_direction(value, directions, query):
        return None
    return value if any(token in value for token in _evidence_tokens(base, directions, query)) else None


def _contains_full_public_introduction(value: str, base: Mapping[str, object]) -> bool:
    database_evidence = base.get('database_evidence')
    introduction = str(database_evidence.get('public_introduction') or '').strip() if isinstance(database_evidence, Mapping) else ''
    normalized_introduction = re.sub(r'\s+', '', introduction)
    normalized_value = re.sub(r'\s+', '', value)
    return len(normalized_introduction) >= 20 and normalized_introduction in normalized_value


def _grounded_core_advantages(
    value: str | None, base: Mapping[str, object], directions: Sequence[str], query: str,
) -> str | None:
    normalized = str(value or '').strip()
    if not _grounded_generated_text(normalized, base, directions, query):
        return None
    if len(normalized) > 180 or '公开简介：' in normalized or '；' in normalized:
        return None
    if _contains_full_public_introduction(normalized, base):
        return None
    if _contains_unverified_promotional_claim(normalized):
        return None
    if _has_nonfinal_missing_specialty_note(normalized):
        return None
    return normalized


def _contains_unverified_promotional_claim(value: str) -> bool:
    return any(marker in value for marker in (
        '综合服务能力较强', '全面健康服务', '重要机构', '专业水平高', '临床经验丰富',
        '优质诊疗', '行业领先', '一流医院',
    ))


def _has_nonfinal_missing_specialty_note(value: str) -> bool:
    sentences = [part.strip() for part in re.split(r'(?<=[。！？])', value) if part.strip()]
    note_markers = ('当前公开资料未提供', '当前公开信息中未见')
    return any(any(marker in sentence for marker in note_markers) for sentence in sentences[:-1])


_INTERNAL_REASONING_MARKERS = (
    '用户查询为', '需要理解任务', '候选列表', '我们需要回答',
    '必须输出', '输出排名', '以下是候选', '让我分析',
)


_EXTRA_REASONING_MARKERS = (
    '\u867d\u7136\u7528\u6237\u67e5\u8be2\u65b9\u5411\u4e3a', '\u867d\u7136\u67e5\u8be2', '\u4f5c\u4e3a\u5907\u9009',
    '\u5168\u56fd\u9876\u5c16\u7efc\u5408\u533b\u9662', '\u7528\u6237\u67e5\u8be2\u4e3a', '\u9700\u8981\u7406\u89e3\u4efb\u52a1',
    '\u5019\u9009\u533b\u9662', '\u4ee5\u4e0b\u662f', '\u7406\u7531\u5982\u4e0b', 'analysis', 'reasoning', 'candidate list',
)


def _is_internal_reasoning(value: str | None) -> bool:
    return bool(value and any(marker in value for marker in (*_INTERNAL_REASONING_MARKERS, *_EXTRA_REASONING_MARKERS)))


def _has_relevant_direction(value: str | None, directions: Sequence[str], query: str) -> bool:
    if not value:
        return False
    terms = [str(item).strip() for item in directions if str(item).strip()]
    aliases = {
        '心血管内科': ('心血管', '心内科', '冠心病', '心绞痛'),
        '骨科': ('骨科', '关节', '骨关节'),
        '风湿免疫科': ('风湿', '关节炎', '免疫'),
        '肿瘤内科': ('肿瘤', '癌症'),
        '呼吸科': ('呼吸', '肺部', '咳嗽'),
    }
    for direction in directions:
        terms.extend(aliases.get(str(direction).strip(), ()))
    terms.extend(token for token in re.findall(r'[\u4e00-\u9fff]{2,}', query) if len(token) >= 2)
    return any(term in value for term in terms)


def _has_conflicting_specialty(value: str | None, base: Mapping[str, object], directions: Sequence[str]) -> bool:
    if not value:
        return False
    evidence_items = base.get('specialty_evidence')
    if not isinstance(evidence_items, list):
        return False
    for item in evidence_items:
        if not isinstance(item, Mapping):
            continue
        department = str(item.get('department') or item.get('specialty') or '').strip()
        if department and department in value and not _has_relevant_direction(department, directions, ''):
            return True
    return False


def _fallback_match_reason(
    base: Mapping[str, object], directions: Sequence[str], query: str, location: Mapping[str, str],
) -> str:
    department = next((str(item).strip() for item in directions if str(item).strip()), '相关专科')
    city = str(base.get('city') or location.get('city') or '').strip()
    evidence_items = [item for item in base.get('specialty_evidence', []) if isinstance(item, Mapping)]
    evidence = evidence_items[0] if evidence_items else None
    if evidence:
        detail = str(evidence.get('specialty') or department)
        if evidence.get('rank'):
            detail += f"在{evidence.get('year') or '公开数据'}年相关区域排名第{evidence['rank']}"
        elif evidence.get('tier'):
            detail += f"具备{evidence['tier']}资质"
        reason = f"该院{detail}，与“{query}”对应的{department}就医方向相关"
    else:
        reason = f"该院已匹配{department}方向，但目前缺少明确的权威专科证据"
    return f"{reason}；医院位于{city or '当前选择区域'}，符合本次地域范围。"


def _fallback_hospital_strength(base: Mapping[str, object], directions: Sequence[str] = ()) -> str:
    tier = str(base.get('tier') or '医院').strip()
    database_evidence = base.get('database_evidence')
    hospital_type = str(
        base.get('hospital_type')
        or (database_evidence.get('hospital_type') if isinstance(database_evidence, Mapping) else '')
        or ''
    ).strip()
    if not hospital_type and isinstance(database_evidence, Mapping):
        introduction = str(database_evidence.get('public_introduction') or '')
        hospital_type = next((
            value for value in ('中西医结合医院', '妇幼保健院', '专科医院', '综合医院')
            if value in introduction
        ), '')
    rankings = database_evidence.get('rankings', []) if isinstance(database_evidence, Mapping) else []
    sentences: list[str] = []
    direction_terms = tuple(
        term.casefold()
        for direction in directions
        for term in re.split(r'[或/、,，]', str(direction))
        if term.strip()
    )
    specialty_ranking = next((
        item for item in base.get('specialty_evidence', [])
        if isinstance(item, Mapping)
        and item.get('rank')
        and str(item.get('specialty') or '').strip()
        and (
            not direction_terms
            or any(
                term in str(item.get('specialty') or '').casefold()
                or str(item.get('specialty') or '').casefold() in term
                for term in direction_terms
            )
        )
    ), None)
    missing_specialty_note = bool(directions and not specialty_ranking)
    if specialty_ranking:
        title = str(specialty_ranking.get('ranking_source_name') or '').strip()
        publisher = str(specialty_ranking.get('ranking_publisher') or '').strip()
        specialty = str(specialty_ranking.get('specialty') or '').strip()
        if title:
            publisher_part = f'{publisher}发布的' if publisher else ''
            sentences.append(f'该院{specialty}在{publisher_part}《{title}》中位列第{specialty_ranking.get("rank")}名。')
    generic_ranking = next((item for item in rankings if isinstance(item, Mapping) and item.get('rank') and not str(item.get('specialty') or '').strip()), None)
    if not sentences and generic_ranking:
        source_name = str(generic_ranking.get('ranking_source_name') or '').strip()
        if source_name:
            sentences.append(f'医院在《{source_name}》中位列第{generic_ranking.get("rank")}名。')
        else:
            year = f"{generic_ranking.get('year')}年" if generic_ranking.get('year') else ''
            scope = str(generic_ranking.get('ranking_scope') or generic_ranking.get('scope') or '公开榜单').strip()
            name = str(generic_ranking.get('ranking_name') or '综合排名').strip()
            sentences.append(f'医院在{year}{scope}{name}中位列第{generic_ranking.get("rank")}名。')
    if tier != '医院' or hospital_type:
        if not generic_ranking:
            institution = f'{tier}{hospital_type}' if hospital_type else f'{tier}医院'
            sentences.append(f'该院为{institution}。')
    profile = _factual_profile_sentence(database_evidence)
    if profile:
        sentences.append(profile)
    if missing_specialty_note:
        direction = _direction_label(directions)
        sentences.append(f'当前公开信息中未见与{direction}方向直接对应的专科排名，建议结合{direction}门诊安排进一步确认。')
        sentences = sentences[:-1][:2] + [sentences[-1]]
    if sentences:
        return ''.join(sentences[:3])[:260]
    return f'{_direction_label(directions)}方向的医院综合服务信息待进一步核实。'


def _direction_label(directions: Sequence[str]) -> str:
    for direction in directions:
        label = re.split(r'[或/、,，]', str(direction), maxsplit=1)[0].strip()
        if label:
            return label
    return '当前就医'


def _factual_profile_sentence(database_evidence: object) -> str:
    if not isinstance(database_evidence, Mapping):
        return ''
    introduction = str(database_evidence.get('public_introduction') or '').strip()
    promotional_markers = ('愿景', '使命', '一流', '致力于', '秉承', '追求', '坚持')
    for sentence in re.split(r'[。！？]', introduction):
        sentence = sentence.strip()
        if not sentence or len(sentence) > 120 or any(marker in sentence for marker in promotional_markers):
            continue
        if ('妇女和儿童' in sentence or '妇女儿童' in sentence) and ('医疗保健' in sentence or '健康服务' in sentence):
            return '医院提供妇女和儿童相关医疗保健服务。'
        if any(term in sentence for term in ('临床科室', '诊疗范围', '诊疗服务', '健康服务')):
            return f'{sentence}。'
        if any(term in sentence for term in ('认证', '医疗、科研', '医疗、教学', '预防保健')):
            certifications = re.findall(
                r'(?:通过(?:国际)?|获)([A-Z][A-Z0-9-]*)(?:国际)?认证',
                sentence,
            )
            if certifications and '集医疗' in sentence:
                unique_certifications = list(dict.fromkeys(certifications))
                certification_text = '和'.join(
                    f'国际{name}认证' if index == 0 else f'{name}国际认证'
                    for index, name in enumerate(unique_certifications)
                )
                return f'医院已通过{certification_text}，集医疗、科研、教学、预防保健为一体，能够提供综合医疗服务。'
            normalized = re.sub(r'^[^，。！？]{2,40}医院(?:是|为)', '', sentence)
            return f'医院{normalized}。'
    return ''


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
    global LAST_SYNTHESIS_FAILURE
    LAST_SYNTHESIS_FAILURE = None
    settings = os.environ if environ is None else environ
    api_key = settings.get('DEEPSEEK_API_KEY')
    if not api_key or not results:
        LAST_SYNTHESIS_FAILURE = 'missing_api_key_or_candidates'
        return None
    candidate_payload = [
        {
            'id': item.get('id'),
            'name': item.get('name'),
            'city': item.get('city'),
            'address': item.get('address'),
            'tier': item.get('tier'),
            'hospital_type': item.get('hospital_type'),
            'specialties': item.get('specialties', []),
            'core_advantages': item.get('core_advantages'),
            'score': item.get('score'),
            'score_breakdown': item.get('score_breakdown', {}),
            'sources': [
                {**source, 'snippet': str(source.get('snippet') or '')[:300]}
                for source in item.get('sources', [])[:3]
                if isinstance(source, Mapping)
            ],
            # Keep the prompt bounded while retaining the strongest evidence.
            'specialty_evidence': item.get('specialty_evidence', [])[:5],
            'database_evidence': {
                **(item.get('database_evidence') or {}),
                'hospital_type': item.get('hospital_type') or (item.get('database_evidence') or {}).get('hospital_type'),
                'public_introduction': str((item.get('database_evidence') or {}).get('public_introduction') or '')[:300],
                'capabilities': (item.get('database_evidence') or {}).get('capabilities', [])[:4],
                'rankings': (item.get('database_evidence') or {}).get('rankings', [])[:3],
            },
            'official_service_score': (item.get('score_breakdown') or {}).get('official_service'),
        }
        for item in results[:10]
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
        'temperature': 0.1,
        'max_tokens': 2400,
    }, ensure_ascii=False).encode('utf-8')
    request = Request(DEEPSEEK_URL, data=body, headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }, method='POST')
    send = urlopen if transport is None else transport
    try:
        with send(request, timeout=90.0) as response:
            if not 200 <= getattr(response, 'status', 200) < 300:
                return None
            try:
                payload = _extract_json_object(response.read().decode('utf-8-sig'))
            except json.JSONDecodeError:
                LAST_SYNTHESIS_FAILURE = 'api_envelope_json_decode_error'
                raise
        message = payload['choices'][0]['message']
        content = _message_text(message).strip()
        try:
            raw_payload = _extract_json_object(content)
        except json.JSONDecodeError:
            raw_payload = {'results': _parse_plain_text_results(content, results)}
        raw_results = raw_payload.get('results', []) if isinstance(raw_payload, dict) else []
        # A reasoning preamble may contain an example JSON object with an
        # empty results array. In that case continue with the labeled blocks
        # that follow instead of treating the preamble as the answer.
        if not isinstance(raw_results, list) or not raw_results:
            raw_results = _parse_plain_text_results(content, results)
        if not isinstance(raw_results, list):
            raw_results = []
        parsed_items = []
        candidate_by_id = {str(item.get('id')): dict(item) for item in results}
        candidate_by_name = {
            str(item.get('name') or '').strip().casefold(): dict(item)
            for item in results if str(item.get('name') or '').strip()
        }
        for position, raw_item in enumerate(raw_results[:20]):
            try:
                if not isinstance(raw_item, Mapping):
                    continue
                candidate = candidate_by_id.get(str(raw_item.get('id') or '').strip())
                if candidate is None:
                    candidate = candidate_by_name.get(str(raw_item.get('name') or '').strip().casefold())
                if candidate is None and position < len(results):
                    candidate = dict(results[position])
                # The model supplies prose; candidate records supply every
                # factual field required by the response contract.
                normalized = dict(candidate or {})
                normalized.update(raw_item)
                for factual_key in ('id', 'name', 'department', 'address', 'score', 'score_breakdown', 'specialty_evidence'):
                    if candidate and candidate.get(factual_key) is not None:
                        normalized[factual_key] = candidate[factual_key]
                parsed_items.append(SynthesizedHospital.model_validate(normalized))
            except ValidationError as item_error:
                logger.warning('deepseek_web_result_skipped detail=%s', str(item_error)[:180])
        parsed = SynthesisPayload(results=parsed_items)
        if not parsed.results:
            LAST_SYNTHESIS_FAILURE = 'model_returned_no_valid_results'
            return [dict(item) for item in results]
    except (HTTPError, OSError, TypeError, URLError, UnicodeDecodeError,
            json.JSONDecodeError, KeyError, IndexError, ValidationError) as exc:
        LAST_SYNTHESIS_FAILURE = type(exc).__name__
        logger.warning('deepseek_web_synthesis_failed type=%s detail=%s', type(exc).__name__, str(exc)[:240])
        return None

    by_id = {str(item.get('id')): dict(item) for item in results}
    by_name = {
        str(item.get('name') or '').strip().casefold(): dict(item)
        for item in results
        if str(item.get('name') or '').strip()
    }
    synthesized = []
    synthesized_ids: set[str] = set()
    for position, item in enumerate(parsed.results):
        base = by_id.get(item.id)
        if base is None:
            base = by_name.get(item.name.strip().casefold())
        if base is None and position < len(results):
            positional = dict(results[position])
            if str(positional.get('id')) not in synthesized_ids:
                base = positional
        if base is None:
            continue
        base['name'] = item.name
        base['score'] = round(float(base.get('score') or item.score), 2)
        base['score_reasons'] = [item.reason] if item.reason else base.get('score_reasons', [])
        base['department'] = item.department or ''
        base['address'] = str(base.get('address') or '')
        generated_advantages = _grounded_core_advantages(item.core_advantages, base, directions, query)
        if generated_advantages and directions and not _has_directional_specialty_ranking(base, directions):
            generated_advantages = _append_missing_specialty_note(generated_advantages, directions)
        generated_match_reason = _grounded_generated_text(item.match_reason, base, directions, query)
        if _is_internal_reasoning(generated_advantages):
            generated_advantages = None
        if _is_internal_reasoning(generated_match_reason):
            generated_match_reason = None
        existing_advantages = base.get('core_advantages')
        if _is_internal_reasoning(existing_advantages) or _has_conflicting_specialty(existing_advantages, base, directions) or not _has_relevant_direction(existing_advantages, directions, query):
            existing_advantages = None
        base['core_advantages'] = generated_advantages or existing_advantages or _fallback_hospital_strength(base, directions)
        existing_reason = base.get('match_reason')
        if _is_internal_reasoning(existing_reason) or _has_conflicting_specialty(existing_reason, base, directions) or not _has_relevant_direction(existing_reason, directions, query):
            existing_reason = None
        model_reason = item.reason if not _is_internal_reasoning(item.reason) and not _has_conflicting_specialty(item.reason, base, directions) and _has_relevant_direction(item.reason, directions, query) else None
        base['match_reason'] = generated_match_reason or existing_reason or model_reason or _fallback_match_reason(
            base, directions, query, location,
        )
        base['evidence_status'] = item.evidence_status or ('有公开资料' if base.get('sources') else '暂无公开资料')
        base['score_breakdown'] = base.get('score_breakdown') or {
            key: float(value) for key, value in item.score_breakdown.items()
            if isinstance(value, (int, float))
        }
        base['specialty_evidence'] = base.get('specialty_evidence') or item.specialty_evidence
        synthesized.append(base)
        synthesized_ids.add(str(base.get('id')))
    # DeepSeek may omit valid candidates because of response-length limits.
    # Keep the deterministic local candidates after the AI-ranked entries so
    # search recall is never reduced by the synthesis step.
    for base in results:
        candidate_id = str(base.get('id'))
        if candidate_id not in synthesized_ids:
            synthesized.append(dict(base))
    synthesized.sort(
        key=lambda item: (
            -float(item.get('score') or 0),
            str(item.get('name') or '').casefold(),
        )
    )
    return synthesized[:10] or None


def _has_directional_specialty_ranking(base: Mapping[str, object], directions: Sequence[str]) -> bool:
    direction_terms = tuple(
        term.casefold()
        for direction in directions
        for term in re.split(r'[或/、,，]', str(direction))
        if term.strip()
    )
    return any(
        isinstance(item, Mapping)
        and item.get('rank')
        and str(item.get('specialty') or '').strip()
        and any(
            term in str(item.get('specialty') or '').casefold()
            or str(item.get('specialty') or '').casefold() in term
            for term in direction_terms
        )
        for item in base.get('specialty_evidence', [])
    )


def _append_missing_specialty_note(value: str, directions: Sequence[str]) -> str:
    if '当前公开信息中未见' in value:
        return value
    direction = _direction_label(directions)
    return f'{value.rstrip("。！？")}。当前公开信息中未见与{direction}方向直接对应的专科排名，建议结合{direction}门诊安排进一步确认。'


def _extract_json_object(content: str) -> dict[str, object]:
    """Extract the response object even when the model adds prose or fences."""
    text = content.strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed = None
        for match in re.finditer(r'\{', text):
            try:
                candidate, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and 'results' in candidate:
                parsed = candidate
                break
        if parsed is None:
            raise
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError('expected JSON object', text, 0)
    return parsed


def _message_text(message: Mapping[str, object]) -> str:
    """Read DeepSeek text across chat and reasoning-style response shapes."""
    content = message.get('content')
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get('text'), str):
                parts.append(item['text'])
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return '\n'.join(parts)
    reasoning = message.get('reasoning_content')
    return reasoning if isinstance(reasoning, str) else ''


def _parse_plain_text_results(content: str, results: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Map labeled plain-text blocks back to factual candidate records."""
    by_id = {str(item.get('id')): item for item in results}
    normalized_content = re.sub(r'[*_`#]+', '', content)
    blocks = re.split(r'(?=医院\s*(?:ID|编号)\s*[:：])', normalized_content, flags=re.IGNORECASE)
    parsed: list[dict[str, object]] = []
    for block in blocks:
        id_match = re.search(r'医院\s*(?:ID|编号)\s*[:：]\s*([^\s\r\n]+)', block, re.IGNORECASE)
        if not id_match:
            continue
        candidate = by_id.get(id_match.group(1).strip())
        if candidate is None:
            continue
        advantage = re.search(r'核心优势\s*[:：]\s*(.*?)(?=\n\s*匹配理由\s*[:：]|$)', block, re.DOTALL)
        reason = re.search(r'匹配理由\s*[:：]\s*(.*?)(?=\n\s*医院\s*ID\s*[:：]|$)', block, re.DOTALL)
        item = dict(candidate)
        item['core_advantages'] = advantage.group(1).strip() if advantage else ''
        item['match_reason'] = reason.group(1).strip() if reason else ''
        parsed.append(item)
    return parsed
