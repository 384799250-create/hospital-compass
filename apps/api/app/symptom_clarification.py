"""Adaptive symptom clarification with a deterministic safety fallback."""

import json
import logging
import os
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError


logger = logging.getLogger(__name__)

class ClarificationUnavailableError(RuntimeError):
    """Raised when AI cannot safely produce the next clarification decision."""


MAX_CLARIFICATION_QUESTIONS = 10
MAX_AI_ATTEMPTS = 2
AI_REQUEST_TIMEOUT_SECONDS = 30.0
UNCERTAINTY_OPTIONS = frozenset({
    '不清楚', '不太清楚', '说不清', '说不清楚', '不知道', '不晓得', '不太确定', '无法确定',
})

URGENT_WARNING = '如果伴有呼吸困难、冷汗、晕厥或症状突然加重，请立即拨打120或前往急诊。'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
QUESTION_JSON_RULES = (
    '输出必须是一个合法 JSON 对象，不得使用 Markdown、代码块或 JSON 以外的文字。'
    'question 只能包含 id、text、type、options；type 必须为 single；options 必须是 3 到 6 个不重复的简短文本，'
    '最后一项且仅最后一项必须是“不确定”。'
)
SYSTEM_PROMPT = (
    '你是中文健康信息分流助手，不做医学诊断。根据用户症状和已经回答的内容，生成下一步最有帮助的一个确认问题。'
    '字段必须是 question、estimated_total；estimated_total 是预计总问题数，必须是 1 到 10 的整数，会根据后续回答动态调整。'
    + QUESTION_JSON_RULES +
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
    estimated_total: int | None = Field(default=None, ge=1, le=MAX_CLARIFICATION_QUESTIONS)


class _DeepSeekDirectionOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    directions: list[dict[str, Any]] = Field(min_length=1, max_length=3)
    urgent_warning: str = Field(default='', max_length=240)


def _retry_ai_result(request: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
    for _ in range(MAX_AI_ATTEMPTS):
        result = request()
        if result is not None:
            return result
    return None


def _normalize_question_id(raw_question: Any) -> Any:
    if isinstance(raw_question, dict):
        question_id = raw_question.get('id')
        if isinstance(question_id, int) and not isinstance(question_id, bool):
            return {**raw_question, 'id': str(question_id)}
    return raw_question


def _normalize_question(raw_question: Any) -> Any:
    normalized = _normalize_question_id(raw_question)
    if not isinstance(normalized, dict):
        return normalized
    question_type = normalized.get('type')
    if question_type in {'单选', 'single_choice'}:
        normalized = {**normalized, 'type': 'single'}
    options = normalized.get('options')
    if isinstance(options, list) and options and all(isinstance(option, str) for option in options):
        normalized_options = list(options)
        if normalized_options[-1].strip() in UNCERTAINTY_OPTIONS:
            normalized_options[-1] = '不确定'
            normalized = {**normalized, 'options': normalized_options}
    return normalized


def _normalize_direction_warnings(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    if normalized.get('urgent_warning') is None or normalized.get('urgent_warning') is False:
        normalized['urgent_warning'] = ''
    directions = normalized.get('directions')
    if isinstance(directions, list):
        normalized['directions'] = [
            {**direction, 'urgent_warning': ''}
            if isinstance(direction, dict) and (direction.get('urgent_warning') is None or direction.get('urgent_warning') is False)
            else direction
            for direction in directions
        ]
    return normalized


def _validate_question(
    raw_question: Any,
    *,
    query: str,
    asked_ids: set[str] | None = None,
    asked_questions: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    # Models sometimes emit a numeric question id even though the public
    # contract uses string ids. Normalize that harmless representation before
    # applying the rest of the strict question validation.
    raw_question = _normalize_question(raw_question)
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
    if _repeats_question_topic(question, asked_questions or []):
        return None
    if ('头疼' in query or '头痛' in query) and (
        '哪里' in question['text']
        or any(option in {'头部', '头', '一边', '两边'} for option in question['options'])
    ):
        return None
    return question


def _repeats_question_topic(question: Mapping[str, Any], asked_questions: list[Mapping[str, Any]]) -> bool:
    """Reject wording changes that ask the user for the same information again."""
    question_text = str(question.get('text') or '').strip()
    normalized_text = ''.join(character for character in question_text if character.isalnum())
    topic = _question_topic(question_text, question.get('options') or [])
    for asked_question in asked_questions:
        asked_text = str(asked_question.get('text') or '').strip()
        normalized_asked_text = ''.join(character for character in asked_text if character.isalnum())
        if normalized_text and normalized_text == normalized_asked_text:
            return True
        if topic and topic == _question_topic(asked_text, asked_question.get('options') or []):
            return True
    return False


def _question_topic(text: str, options: Any) -> str | None:
    combined = f"{text} {' '.join(str(option) for option in options if str(option).strip())}"
    topic_markers = {
        'location': ('哪里', '哪儿', '部位', '位置', '哪个地方'),
        'duration': ('多久', '多长时间', '几天', '持续', '什么时候开始', '何时开始'),
        'trigger': ('活动', '走路', '运动', '休息', '躺下', '饭后'),
        'severity': ('严重', '厉害', '程度', '轻微', '加重', '减轻'),
        'frequency': ('一直', '反复', '偶尔', '频繁', '时有时无'),
    }
    return next((topic for topic, markers in topic_markers.items() if any(marker in combined for marker in markers)), None)


_SAFE_FALLBACK_QUESTIONS = (
    ('duration', '这种情况大概持续多久了？', ('刚开始', '几天到几周', '超过一个月', '不确定')),
    ('symptom', '除了现在的情况，还有没有痒、疼或发红？', ('有痒', '有疼痛', '有发红', '都没有', '不确定')),
    ('appearance', '现在的范围和样子有没有明显变化？', ('范围变大了', '颜色或形状变了', '基本没变化', '不确定')),
    ('spread', '身体其他地方有没有出现类似情况？', ('有', '没有', '不确定')),
    ('trigger', '什么情况下会更明显？', ('活动或摩擦后', '接触某些东西后', '一直差不多', '不确定')),
    ('recurrence', '以前有没有出现过类似情况？', ('以前有过', '第一次出现', '不确定')),
    ('exposure', '最近有没有换过护肤品、洗涤用品或接触新的东西？', ('有', '没有', '不确定')),
    ('impact', '这种情况对日常生活影响大吗？', ('影响比较大', '影响不大', '基本没有影响', '不确定')),
    ('onset', '最开始是突然出现，还是慢慢出现的？', ('突然出现', '慢慢出现', '记不清了', '不确定')),
    ('other', '还有没有其他同时出现的不舒服？', ('有', '没有', '不确定')),
)


def _next_safe_fallback_question(
    answers: list[dict[str, Any]],
    asked_questions: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Return one unused, plain-language question when AI cannot continue."""
    asked_ids = {
        str(item.get('question_id') or item.get('id') or '').strip()
        for item in [*answers, *asked_questions]
        if item.get('question_id') or item.get('id')
    }
    for question_id, text, options in _SAFE_FALLBACK_QUESTIONS:
        question = {'id': question_id, 'text': text, 'type': 'single', 'options': list(options)}
        if question_id in asked_ids or _repeats_question_topic(question, asked_questions):
            continue
        return question
    return None


def _normalize_estimated_total(value: Any, *, current_question: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return min(MAX_CLARIFICATION_QUESTIONS, max(current_question, value))


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
        with send(request, timeout=AI_REQUEST_TIMEOUT_SECONDS) as response:
            if not 200 <= getattr(response, 'status', 200) < 300:
                logger.warning('symptom clarification AI request failed: http_status=%s', getattr(response, 'status', None))
                return None
            payload = json.loads(response.read().decode('utf-8'))
        raw = json.loads(payload['choices'][0]['message']['content'])
        if isinstance(raw, dict) and 'question' in raw:
            raw = {**raw, 'question': _normalize_question(raw['question'])}
        parsed = _DeepSeekQuestionOutput.model_validate(raw)
        question = _validate_question(parsed.question.model_dump(), query=query)
        if not question:
            return None
        return {
            'question': question,
            'estimated_total': _normalize_estimated_total(parsed.estimated_total, current_question=1),
        }
    except TimeoutError:
        logger.warning('symptom clarification AI request timed out after %.0f seconds', AI_REQUEST_TIMEOUT_SECONDS)
        return None
    except OSError:
        logger.warning('symptom clarification AI transport request failed')
        return None
    except (TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        logger.warning('symptom clarification AI response failed validation')
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
        direction_warning = raw_direction.get('urgent_warning', '')
        if not isinstance(direction_warning, str):
            return None
        directions.append({
            'key': str(raw_direction['key']).strip(),
            'title': str(raw_direction['title']).strip(),
            'likelihood': str(raw_direction['likelihood']).strip(),
            'basis': str(raw_direction['basis']).strip(),
            'department': str(raw_direction['department']).strip(),
            'possible_diseases': diseases,
            'urgent_warning': direction_warning.strip(),
        })
    return {'directions': directions, 'urgent_warning': parsed.urgent_warning}


def _ai_next_step(
    query: str,
    answers: list[dict[str, Any]],
    *,
    asked_questions: list[Mapping[str, Any]],
    settings: Mapping[str, str],
    transport: Callable[..., object] | None,
) -> dict[str, Any] | None:
    """Ask the model whether one more question is useful or directions are ready."""
    if not settings.get('DEEPSEEK_API_KEY'):
        return None
    asked_ids = {str(item.get('question_id') or '').strip() for item in answers if item.get('question_id')}
    asked_ids.update(str(item.get('id') or '').strip() for item in asked_questions if item.get('id'))
    force_complete = len(answers) >= MAX_CLARIFICATION_QUESTIONS
    completion_instruction = (
        '\u5df2\u8fbe\u5230\u95ee\u9898\u4e0a\u9650\uff0c\u5fc5\u987b\u8fd4\u56de status=COMPLETE \u4ee5\u53ca directions\uff0c\u4e0d\u5f97\u518d\u8fd4\u56de question\u3002'
        if force_complete else ''
    )
    body = json.dumps({
        'model': settings.get('DEEPSEEK_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': (
                '你是中文健康信息分流助手，不做医学诊断。根据原始症状和已经回答的内容，决定是否还需要确认一个问题。'
                '只返回 JSON。信息不足时返回 status=NEEDS_CLARIFICATION、question、estimated_total；estimated_total 是预计总问题数，必须为 1 到 10 的整数，会根据后续回答动态调整。信息足够时返回 status=COMPLETE、directions、urgent_warning。'
                + QUESTION_JSON_RULES +
                '不得重复已问主题，不要问用户已经明确说过的内容，不要使用诊断、治疗、用药等术语。'
                'directions 每项包含 key、title、likelihood、basis、department、possible_diseases、urgent_warning；possible_diseases 只是方向参考，不是诊断。'
                + completion_instruction
            )},
            {'role': 'user', 'content': json.dumps({
                'query': query,
                'answers': answers,
                'asked_question_ids': sorted(asked_ids),
                'asked_questions': asked_questions,
                'question_limit': MAX_CLARIFICATION_QUESTIONS,
                'force_complete': force_complete,
                'completion_instruction': completion_instruction,
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
        with send(request, timeout=AI_REQUEST_TIMEOUT_SECONDS) as response:
            if not 200 <= getattr(response, 'status', 200) < 300:
                logger.warning('symptom clarification AI request failed: http_status=%s', getattr(response, 'status', None))
                return None
            payload = json.loads(response.read().decode('utf-8'))
        raw = json.loads(payload['choices'][0]['message']['content'])
        if not isinstance(raw, dict):
            return None
        status = str(raw.get('status') or '').strip()
        if status == 'NEEDS_CLARIFICATION' or ('question' in raw and 'directions' not in raw):
            question = _validate_question(
                raw.get('question'), query=query, asked_ids=asked_ids, asked_questions=asked_questions,
            )
            if force_complete:
                return None
            if not question:
                return None
            return {
                'status': 'NEEDS_CLARIFICATION',
                'question': question,
                'estimated_total': _normalize_estimated_total(raw.get('estimated_total'), current_question=len(answers) + 1),
                'ai_used': True,
            }
        if status == 'COMPLETE' or 'directions' in raw:
            parsed = _parse_directions(_normalize_direction_warnings(raw))
            if parsed:
                return {'status': 'COMPLETE', **parsed, 'ai_used': True}
        return None
    except TimeoutError:
        logger.warning('symptom clarification AI request timed out after %.0f seconds', AI_REQUEST_TIMEOUT_SECONDS)
        return None
    except OSError:
        logger.warning('symptom clarification AI transport request failed')
        return None
    except (TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        logger.warning('symptom clarification AI response failed validation')
        return None


def clarify_symptoms(
    query: str,
    *,
    answers: list[dict[str, Any]],
    ai_consent: bool,
    asked_questions: list[Mapping[str, Any]] | None = None,
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
    question_history = [item for item in (asked_questions or []) if isinstance(item, Mapping)]
    if not answers:
        ai_question = _retry_ai_result(
            lambda: _ai_question(normalized, answers, settings=settings, transport=transport),
        )
        if ai_question is None:
            raise ClarificationUnavailableError()
        estimated_total = ai_question.get('estimated_total')
        return {
            'status': 'NEEDS_CLARIFICATION',
            'question': ai_question['question'],
            'progress': {'current': 1, 'total': estimated_total or 1},
            **({'estimated_total': estimated_total} if estimated_total is not None else {}),
            'directions': [],
            'urgent_warning': '',
            'ai_used': True,
        }
    ai_result = _retry_ai_result(
        lambda: _ai_next_step(
            normalized, answers, asked_questions=question_history, settings=settings, transport=transport,
        ),
    )
    if ai_result is None:
        if len(answers) >= MAX_CLARIFICATION_QUESTIONS:
            raise ClarificationUnavailableError()
        fallback_question = _next_safe_fallback_question(answers, question_history)
        if fallback_question is None:
            raise ClarificationUnavailableError()
        question_number = len(answers) + 1
        return {
            'status': 'NEEDS_CLARIFICATION',
            'question': fallback_question,
            'progress': {'current': question_number, 'total': min(MAX_CLARIFICATION_QUESTIONS, question_number + 1)},
            'estimated_total': min(MAX_CLARIFICATION_QUESTIONS, question_number + 1),
            'directions': [],
            'urgent_warning': '',
            'ai_used': False,
        }
    if ai_result['status'] == 'NEEDS_CLARIFICATION':
        if len(answers) >= MAX_CLARIFICATION_QUESTIONS:
            raise ClarificationUnavailableError()
        question = ai_result.get('question')
        if not question:
            raise ClarificationUnavailableError()
        question_number = len(answers) + 1
        estimated_total = ai_result.get('estimated_total')
        return {
            'status': 'NEEDS_CLARIFICATION',
            'question': question,
            'progress': {'current': question_number, 'total': estimated_total or question_number},
            **({'estimated_total': estimated_total} if estimated_total is not None else {}),
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
