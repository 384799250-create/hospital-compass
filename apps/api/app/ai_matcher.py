import json
import os
from datetime import date
from typing import Callable, Literal, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.data import DemoHospital
from app.matcher import SPECIALTY_KEYWORDS, MatchResponse, match, match_directions

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
SYSTEM_PROMPT = (
    '只返回 JSON object：summary 是最多 240 字符的字符串，'
    'directions 是建议专科方向的字符串数组。'
)


class AIMetadata(BaseModel):
    used: bool
    summary: str | None
    directions: list[str]
    fallback: bool


class AIMatchResponse(MatchResponse):
    ai: AIMetadata


class DeepSeekOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    summary: str = Field(max_length=240)
    directions: list[str]


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

    if not directions:
        return _fallback(local)

    matched = match_directions(directions, city, priority, hospitals=hospitals, as_of=as_of)
    return AIMatchResponse(
        **matched.model_dump(),
        ai=AIMetadata(
            used=True,
            summary=ai_payload.summary,
            directions=directions,
            fallback=False,
        ),
    )


def _fallback(local: MatchResponse) -> AIMatchResponse:
    return AIMatchResponse(
        **local.model_dump(),
        ai=AIMetadata(used=False, summary=None, directions=[], fallback=True),
    )
