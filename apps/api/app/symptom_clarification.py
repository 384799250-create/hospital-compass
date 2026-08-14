"""Adaptive symptom clarification with a deterministic safety fallback."""

import json
import os
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ClarificationUnavailableError(RuntimeError):
    """Raised when AI cannot safely produce the next clarification decision."""


MAX_CLARIFICATION_QUESTIONS = 3

URGENT_WARNING = '如果伴有呼吸困难、冷汗、晕厥或症状突然加重，请立即拨打120或前往急诊。'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
SYSTEM_PROMPT = (
    '你是中文健康信息分流助手，不做医学诊断。根据用户症状和已经回答的内容，生成下一步最有帮助的一个确认问题。'
    '只返回 JSON 对象，字段必须是 question；question 包含 id、text、type、options。type 固定为 single，options 提供 3 到 6 个简短易懂的单选项，最后一个必须是“不确定”。'
    '问题和选项使用普通人日常能看懂的说法，不要使用生硬医学术语，不要要求用户自行诊断，不要给出治疗建议。'
)


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=4, max_length=120)
    type: str = Field(pattern='^single$')
    options: list[str] = Field(min_length=3, max_length=6)


class _DeepSeekQuestionOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    question: ClarificationQuestion


class _DeepSeekDirectionOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    directions: list[dict[str, Any]] = Field(min_length=1, max_length=3)
    urgent_warning: str = Field(default='', max_length=240)


def _validate_question(
    raw_question: Any,
    *,
    query: str,
    asked_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    try:
        question = ClarificationQuestion.model_validate(raw_question).model_dump()
    except ValidationError:
        return None
    if question['options'][-1] != '不确定' or len(set(question['options'])) != len(question['options']):
        return None
    if any(term in question['text'] for term in ('诊断', '治疗', '用药')):
        return None
    if asked_ids and question['id'] in asked_ids:
        return None
    if ('头疼' in query or '头痛' in query) and (
        '哪里' in question['text']
        or any(option in {'头部', '头', '一边', '两边'} for option in question['options'])
    ):
        return None
    return question


def _ai_question(
    query: str,
    answers: list[dict[str, Any]],
    *,
    settings: Mapping[str, str],
    transport: Callable[..., object] | None,
) -> dict[str, Any] | None:
    if not settings.get('DEEPSEEK_API_KEY'):
        return None
    body = json.dumps({
        'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps({'query': query, 'answers': answers}, ensure_ascii=False)},
        ],
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
                return None
            payload = json.loads(response.read().decode('utf-8'))
        raw = json.loads(payload['choices'][0]['message']['content'])
        parsed = _DeepSeekQuestionOutput.model_validate(raw)
        return _validate_question(parsed.question.model_dump(), query=query)
    except (OSError, TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return None


def _parse_directions(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        parsed = _DeepSeekDirectionOutput.model_validate({
            'directions': raw.get('directions'),
            'urgent_warning': raw.get('urgent_warning', ''),
        })
    except ValidationError:
        return None
    directions: list[dict[str, Any]] = []
    for raw_direction in parsed.directions:
        allowed = {'key', 'title', 'likelihood', 'basis', 'department', 'possible_diseases', 'urgent_warning'}
        if not set(raw_direction).issubset(allowed):
            return None
        diseases = [str(item).strip() for item in (raw_direction.get('possible_diseases') or []) if str(item).strip()][:5]
        if not all(str(raw_direction.get(field) or '').strip() for field in ('key', 'title', 'likelihood', 'basis', 'department')):
            return None
        directions.append({
            'key': str(raw_direction['key']).strip(),
            'title': str(raw_direction['title']).strip(),
            'likelihood': str(raw_direction['likelihood']).strip(),
            'basis': str(raw_direction['basis']).strip(),
            'department': str(raw_direction['department']).strip(),
            'possible_diseases': diseases,
            'urgent_warning': str(raw_direction.get('urgent_warning') or '').strip(),
        })
    return {'directions': directions, 'urgent_warning': parsed.urgent_warning}


def _ai_next_step(
    query: str,
    answers: list[dict[str, Any]],
    *,
    settings: Mapping[str, str],
    transport: Callable[..., object] | None,
) -> dict[str, Any] | None:
    """Ask the model whether one more question is useful or directions are ready."""
    if not settings.get('DEEPSEEK_API_KEY'):
        return None
    asked_ids = {str(item.get('question_id') or '').strip() for item in answers if item.get('question_id')}
    body = json.dumps({
        'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': (
                '你是中文健康信息分流助手，不做医学诊断。根据原始症状和已经回答的内容，决定是否还需要确认一个问题。'
                '只返回 JSON。信息不足时返回 status=NEEDS_CLARIFICATION 和 question；信息足够时返回 status=COMPLETE、directions、urgent_warning。'
                'question 必须包含 id、text、type、options，type 固定为 single，options 提供 3 到 6 个通俗单选项，最后一个必须是“不确定”。'
                '不要重复已经问过的 question_id，不要问用户已经明确说过的内容，不要使用诊断、治疗、用药等术语。'
                'directions 每项包含 key、title、likelihood、basis、department、possible_diseases、urgent_warning；possible_diseases 只是方向参考，不是诊断。'
            )},
            {'role': 'user', 'content': json.dumps({
                'query': query,
                'answers': answers,
                'asked_question_ids': sorted(asked_ids),
                'question_limit': MAX_CLARIFICATION_QUESTIONS,
            }, ensure_ascii=False)},
        ],
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
                return None
            payload = json.loads(response.read().decode('utf-8'))
        raw = json.loads(payload['choices'][0]['message']['content'])
        if not isinstance(raw, dict):
            return None
        status = str(raw.get('status') or '').strip()
        if status == 'NEEDS_CLARIFICATION' or ('question' in raw and 'directions' not in raw):
            question = _validate_question(raw.get('question'), query=query, asked_ids=asked_ids)
            return {'status': 'NEEDS_CLARIFICATION', 'question': question, 'ai_used': True} if question else None
        if status == 'COMPLETE' or 'directions' in raw:
            parsed = _parse_directions(raw)
            if parsed:
                return {'status': 'COMPLETE', **parsed, 'ai_used': True}
        return None
    except (OSError, TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return None


def clarify_symptoms(
    query: str,
    *,
    answers: list[dict[str, Any]],
    ai_consent: bool,
    environ: dict[str, str] | None = None,
    transport: Callable[..., object] | None = None,
) -> dict[str, Any]:
    if not ai_consent:
        raise ValueError('AI consent is required before clarification')
    answer_values = [str(item.get('value') or '').strip() for item in answers]
    answer_text = ' '.join(answer_values)
    if any(term in answer_text for term in ('呼吸困难', '冷汗', '晕厥', '意识不清', '突然剧烈出现', '突然一下子特别疼')):
        return {'status': 'EMERGENCY', 'question': None, 'progress': {'current': len(answers), 'total': 1}, 'directions': [], 'urgent_warning': URGENT_WARNING, 'ai_used': False}
    normalized = query.strip()
    settings = os.environ if environ is None else environ
    if not answers:
        question = _ai_question(normalized, answers, settings=settings, transport=transport)
        if question is None:
            raise ClarificationUnavailableError()
        return {
            'status': 'NEEDS_CLARIFICATION',
            'question': question,
            'progress': {'current': 1, 'total': 1},
            'directions': [],
            'urgent_warning': '',
            'ai_used': True,
        }
    ai_result = _ai_next_step(normalized, answers, settings=settings, transport=transport)
    if ai_result is None:
        raise ClarificationUnavailableError()
    if ai_result['status'] == 'NEEDS_CLARIFICATION':
        if len(answers) >= MAX_CLARIFICATION_QUESTIONS:
            raise ClarificationUnavailableError()
        question = ai_result.get('question')
        if not question:
            raise ClarificationUnavailableError()
        question_number = len(answers) + 1
        return {
            'status': 'NEEDS_CLARIFICATION',
            'question': question,
            'progress': {'current': question_number, 'total': question_number},
            'directions': [],
            'urgent_warning': '',
            'ai_used': True,
        }
    if ai_result['status'] != 'COMPLETE':
        raise ClarificationUnavailableError()
    return {
        'status': 'COMPLETE',
        'question': None,
        'progress': {'current': len(answers), 'total': len(answers)},
        'directions': ai_result['directions'],
        'urgent_warning': ai_result['urgent_warning'],
        'ai_used': True,
    }
