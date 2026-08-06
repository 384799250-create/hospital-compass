import json
import os
import re
from datetime import date
from typing import Callable, Literal, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from app.data import DemoHospital
from app.matcher import SPECIALTY_KEYWORDS, MatchResponse, match, match_directions

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
_PROHIBITED_PENDING_CANDIDATE_PATTERNS = (
    re.compile(r'https?://|www\.', re.IGNORECASE),
    re.compile(r'(?<!\d)\d(?:[\s-]*\d){6,}(?!\d)'),
    re.compile(r'推荐'),
    re.compile(r'联系人|联系方式|微信|(?:电子)?邮箱|e-?mail', re.IGNORECASE),
)
_PROHIBITED_LOCATION_CUE_PATTERN = re.compile(r'[省市区县路街号]')
_PROHIBITED_NAME_ADDRESS_PATTERN = re.compile(r'[路街号]')
_DETAILED_CITY_ADDRESS_PATTERN = re.compile(r'[路街号]|[省市].*(?:区|县)')
_PROHIBITED_MEDICAL_ADVICE_PATTERN = re.compile(r'诊断|治疗|用药|服用|手术|处方')
SYSTEM_PROMPT = (
    '只返回 JSON object：summary 是最多 240 字符的字符串，'
    'directions 是建议专科方向的字符串数组；pending_candidates 是可选数组，'
    '每项只能包含 name、city、direction、reason，且最多返回 3 项。'
    '候选必须是中国医院的完整名称且以“医院”结尾；不确定时返回空数组；'
    '不允许科室、门诊、诊所或中心名称。'
    '候选仅是待人工核验的名称，不是已核验推荐；不得提供诊断或治疗建议；'
    '不得编造地址、电话或来源链接。'
)


class AIMetadata(BaseModel):
    used: bool
    summary: str | None
    directions: list[str]
    fallback: bool


class AIMatchResponse(MatchResponse):
    ai: AIMetadata
    pending_candidates: list['PendingCandidate']


class PendingCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: StrictStr = Field(min_length=1, max_length=80)
    city: StrictStr = Field(min_length=1, max_length=40)
    direction: StrictStr = Field(min_length=1, max_length=40)
    reason: StrictStr = Field(min_length=1, max_length=180)

    @field_validator('name', 'city', 'direction', 'reason', mode='before')
    @classmethod
    def strip_text_fields(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

class DeepSeekOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    summary: str = Field(max_length=240)
    directions: list[str]
    pending_candidates: list[object] = Field(default_factory=list)


def ai_match(
    query: str,
    city: str | None,
    priority: Literal['overall', 'specialty', 'convenience'],
    ai_consent: bool,
    *,
    hospitals: tuple[DemoHospital, ...] | None = None,
    as_of: date | None = None,
    environ: Mapping[str, str] | None = None,
    transport: Callable[..., object] | None = None,
) -> AIMatchResponse:
    local = match(query, city, priority, hospitals=hospitals, as_of=as_of)
    settings = os.environ if environ is None else environ
    api_key = settings.get('DEEPSEEK_API_KEY')
    if not ai_consent or local.emergency or not api_key:
        return _fallback(local)

    body = json.dumps(
        {
            'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': query},
            ],
            'response_format': {'type': 'json_object'},
        },
        ensure_ascii=False,
    ).encode('utf-8')
    request = Request(
        DEEPSEEK_URL,
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    send = urlopen if transport is None else transport
    try:
        with send(request, timeout=10.0) as response:
            status = getattr(response, 'status', 200)
            if not 200 <= status < 300:
                return _fallback(local)
            payload = json.loads(response.read().decode('utf-8'))
        content = payload['choices'][0]['message']['content']
        ai_payload = DeepSeekOutput.model_validate(json.loads(content))
        allowed_directions = set(SPECIALTY_KEYWORDS.values())
        directions = list(
            dict.fromkeys(
                direction
                for direction in ai_payload.directions
                if direction in allowed_directions
            )
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        URLError,
        ValidationError,
        json.JSONDecodeError,
    ):
        return _fallback(local)

    pending_candidates = _clean_pending_candidates(ai_payload.pending_candidates)
    if not directions and not pending_candidates:
        return _fallback(local)

    matched = match_directions(directions, city, priority, hospitals=hospitals, as_of=as_of)
    return AIMatchResponse(
        **matched.model_dump(),
        pending_candidates=[] if matched.results else pending_candidates,
        ai=AIMetadata(
            used=True,
            summary=ai_payload.summary,
            directions=directions,
            fallback=False,
        ),
    )


def _clean_pending_candidates(raw_candidates: list[object]) -> list[PendingCandidate]:
    candidates = []
    for raw_candidate in raw_candidates:
        try:
            candidate = PendingCandidate.model_validate(raw_candidate)
        except ValidationError:
            continue
        display_values = candidate.model_dump().values()
        has_prohibited_content = any(
            pattern.search(value)
            for value in display_values
            for pattern in _PROHIBITED_PENDING_CANDIDATE_PATTERNS
        )
        has_address_content = (
            _PROHIBITED_NAME_ADDRESS_PATTERN.search(candidate.name)
            or _DETAILED_CITY_ADDRESS_PATTERN.search(candidate.city)
            or _PROHIBITED_LOCATION_CUE_PATTERN.search(candidate.direction)
            or _PROHIBITED_LOCATION_CUE_PATTERN.search(candidate.reason)
        )
        if (
            not candidate.name.endswith('医院')
            or has_prohibited_content
            or has_address_content
            or _PROHIBITED_MEDICAL_ADVICE_PATTERN.search(candidate.reason)
        ):
            continue
        candidates.append(candidate)
        if len(candidates) == 3:
            break
    return candidates


def _fallback(local: MatchResponse) -> AIMatchResponse:
    return AIMatchResponse(
        **local.model_dump(),
        ai=AIMetadata(used=False, summary=None, directions=[], fallback=True),
        pending_candidates=[],
    )
