"""Small server-side client for Qinglin asynchronous media tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


QINGLIN_BASE_URL = 'https://api.lk888.ai/api'
MediaType = Literal['image', 'video']
Transport = Callable[[Request, float], Any]


class QinglinError(RuntimeError):
    """An upstream or configuration error safe to expose to an API client."""


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return values
    for line in lines:
        text = line.strip()
        if not text or text.startswith('#') or '=' not in text:
            continue
        name, value = text.split('=', 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def resolve_qinglin_key(environ: dict[str, str] | None = None, dotenv_path: Path | None = None) -> str:
    """Resolve the key without reading arbitrary files or exposing its value."""
    process = environ if environ is not None else os.environ
    for name in ('QINGLIN_API_KEY', 'API_KEY'):
        value = str(process.get(name, '')).strip()
        if value:
            return value
    for name in ('QINGLIN_API_KEY', 'API_KEY'):
        value = str(os.environ.get(name, '')).strip()
        if value:
            return value
    project_dotenv = dotenv_path or Path(__file__).resolve().parent.parent / '.env'
    dotenv = _read_dotenv(project_dotenv)
    for name in ('QINGLIN_API_KEY', 'API_KEY'):
        value = dotenv.get(name, '').strip()
        if value:
            return value
    raise QinglinError('Qinglin API key is not configured')


def _default_transport(request: Request, timeout: float) -> Any:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS API host
        return response.read()


class QinglinClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = QINGLIN_BASE_URL,
        timeout: float = 20.0,
        transport: Transport | None = None,
        environ: dict[str, str] | None = None,
        dotenv_path: Path | None = None,
    ) -> None:
        self.api_key = (api_key or resolve_qinglin_key(environ, dotenv_path)).strip()
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.transport = transport or _default_transport

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        request = Request(
            f'{self.base_url}{path}',
            data=payload,
            method=method,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Accept': 'application/json',
                **({'Content-Type': 'application/json'} if body is not None else {}),
            },
        )
        try:
            raw = self.transport(request, self.timeout)
            if hasattr(raw, 'read'):
                raw = raw.read()
            return json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
        except HTTPError as exc:
            raise QinglinError(f'Qinglin request failed with HTTP {exc.code}') from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise QinglinError('Qinglin service is temporarily unavailable') from exc

    def list_models(self, media_type: MediaType) -> list[dict[str, Any]]:
        response = self._request('GET', f'/v1/skills/models?type={quote(media_type)}')
        data = response.get('data') if isinstance(response, dict) else response
        if isinstance(data, dict):
            data = data.get('models', data.get('items', []))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def model_detail(self, model_name: str) -> dict[str, Any]:
        response = self._request('GET', f'/v1/skills/models/{quote(model_name, safe="")}')
        return response.get('data', response) if isinstance(response, dict) else {}

    def balance(self) -> dict[str, Any]:
        response = self._request('GET', '/v1/skills/balance')
        return response.get('data', response) if isinstance(response, dict) else {}

    def create_task(self, model: str, prompt: str, params: dict[str, Any]) -> str:
        response = self._request('POST', '/v1/media/generate', {'model': model, 'prompt': prompt, 'params': params})
        if not isinstance(response, dict) or response.get('code') != 200:
            message = response.get('msg') if isinstance(response, dict) else None
            raise QinglinError(str(message or 'Qinglin media task was not created'))
        task_id = (response.get('data') or {}).get('task_id')
        if not task_id:
            raise QinglinError('Qinglin media task did not return a task id')
        return str(task_id)

    def task_status(self, task_id: str) -> dict[str, Any]:
        response = self._request('GET', f'/v1/skills/task-status?task_id={quote(task_id, safe="")}')
        if not isinstance(response, dict):
            raise QinglinError('Qinglin returned an invalid task status')
        return response
