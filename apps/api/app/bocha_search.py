import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator


BOCHA_SEARCH_URL = 'https://api.bochaai.com/v1/web-search'
logger = logging.getLogger(__name__)


class SearchDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: StrictStr
    url: StrictStr
    snippet: StrictStr
    fetched_at: datetime

    @field_validator('url')
    @classmethod
    def url_must_be_absolute_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise ValueError('url must be an absolute http URL')
        return value


@dataclass(frozen=True)
class SearchResult:
    available: bool
    documents: list[SearchDocument]


class BochaSearchClient:
    def __init__(
        self,
        *,
        settings: Mapping[str, str] | None = None,
        transport: Callable[..., object] | None = None,
    ) -> None:
        self._settings = os.environ if settings is None else settings
        self._transport = urlopen if transport is None else transport

    def search(self, query: str, count: int = 10) -> SearchResult:
        api_key = self._settings.get('BOCHA_API_KEY')
        if not api_key:
            return SearchResult(available=False, documents=[])

        count = min(max(count, 1), 10)

        request = Request(
            BOCHA_SEARCH_URL,
            data=json.dumps({'query': query, 'count': count}).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with self._transport(request, timeout=10.0) as response:
                if not 200 <= getattr(response, 'status', 200) < 300:
                    return SearchResult(available=False, documents=[])
                payload = json.loads(response.read().decode('utf-8'))
            return SearchResult(available=True, documents=_documents_from_payload(payload))
        except (HTTPError, OSError, TypeError, UnicodeDecodeError, URLError, json.JSONDecodeError):
            logger.warning('bocha_search_request_failed')
            return SearchResult(available=False, documents=[])


def _documents_from_payload(payload: object) -> list[SearchDocument]:
    if not isinstance(payload, dict):
        return []
    data = payload.get('data')
    if not isinstance(data, dict):
        return []
    web_pages = data.get('webPages')
    if not isinstance(web_pages, dict):
        return []
    values = web_pages.get('value')
    if not isinstance(values, list):
        return []

    fetched_at = datetime.now(UTC)
    documents = []
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            documents.append(SearchDocument.model_validate({
                'title': value.get('name', value.get('title', '')),
                'url': value.get('url', ''),
                'snippet': value.get('snippet', value.get('summary', '')),
                'fetched_at': fetched_at,
            }))
        except ValidationError:
            continue
    return documents
