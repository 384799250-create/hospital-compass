"""AnySearch MCP client normalized to the project's search result contract."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from app.bocha_search import SearchDocument, SearchResult

ANYSEARCH_URL = 'https://api.anysearch.com/mcp'
logger = logging.getLogger(__name__)


class AnySearchClient:
    def __init__(
        self,
        *,
        settings: Mapping[str, str] | None = None,
        transport: Callable[..., object] | None = None,
    ) -> None:
        self._settings = os.environ if settings is None else settings
        self._transport = urlopen if transport is None else transport

    def search(self, query: str, count: int = 10) -> SearchResult:
        count = min(max(count, 1), 10)
        payload = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/call',
            'params': {'name': 'search', 'arguments': {'query': query, 'max_results': count}},
        }
        headers = {
            'Content-Type': 'application/json',
            'X-Anysearch-Client': 'hospital-compass/1.0',
        }
        api_key = self._settings.get('ANYSEARCH_API_KEY')
        if not api_key:
            return SearchResult(available=False, documents=[])
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        request = Request(ANYSEARCH_URL, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        for attempt in range(2):
            try:
                with self._transport(request, timeout=30.0) as response:
                    if not 200 <= getattr(response, 'status', 200) < 300:
                        return SearchResult(available=False, documents=[])
                    body = json.loads(response.read().decode('utf-8'))
                if body.get('error'):
                    return SearchResult(available=False, documents=[])
                text = _response_text(body)
                return SearchResult(available=True, documents=_documents_from_text(text, count))
            except (HTTPError, OSError, TypeError, UnicodeDecodeError, URLError, json.JSONDecodeError, AttributeError):
                if attempt == 0:
                    continue
                logger.warning('anysearch_request_failed')
        return SearchResult(available=False, documents=[])


def prefer_search_result(primary: SearchResult, fallback: SearchResult) -> SearchResult:
    """Keep AnySearch authoritative and use Bocha only when it has no usable documents."""
    if primary.available and primary.documents:
        return primary
    if fallback.available and fallback.documents:
        return fallback
    return primary


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ''
    content = payload.get('result', {}).get('content', []) if isinstance(payload.get('result'), dict) else []
    for item in content:
        if isinstance(item, dict) and item.get('type') == 'text':
            return str(item.get('text') or '')
    return ''


def _documents_from_text(text: str, count: int) -> list[SearchDocument]:
    fetched_at = datetime.now(UTC)
    documents: list[SearchDocument] = []
    blocks = re.split(r'(?=^###\s+\d+\.)', text, flags=re.MULTILINE)
    for block in blocks:
        if len(documents) >= count:
            break
        heading = re.search(r'^###\s+\d+\.\s*(.+)$', block, flags=re.MULTILINE)
        url_match = re.search(r'\*\*URL\*\*:\s*(https?://\S+)', block)
        if not heading or not url_match:
            continue
        url = url_match.group(1).rstrip('),')
        snippet = ' '.join(line.strip('- ').strip() for line in block.splitlines() if line.strip() and not line.startswith('#') and 'URL**' not in line)
        try:
            documents.append(SearchDocument(
                title=heading.group(1).strip(), url=url, snippet=snippet, fetched_at=fetched_at,
            ))
        except ValidationError:
            continue
    return documents
