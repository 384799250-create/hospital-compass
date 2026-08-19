import json

from app.anysearch import AnySearchClient, prefer_search_result
from app.bocha_search import SearchResult


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode('utf-8')


def test_anysearch_client_sends_json_rpc_and_parses_markdown_results():
    captured = {}

    def transport(request, timeout):
        captured['body'] = json.loads(request.data)
        captured['authorization'] = request.get_header('Authorization')
        return FakeResponse({'result': {'content': [{
            'type': 'text',
            'text': '## Search Results (1 results)\n\n### 1. Example Hospital\n- **URL**: https://hospital.example.org\n- Official cardiology department',
        }]}})

    result = AnySearchClient(settings={'ANYSEARCH_API_KEY': 'test-key'}, transport=transport).search('cardiology')

    assert result.available is True
    assert result.documents[0].url == 'https://hospital.example.org'
    assert result.documents[0].title == 'Example Hospital'
    assert captured['body']['method'] == 'tools/call'
    assert captured['body']['params']['name'] == 'search'
    assert captured['authorization'] == 'Bearer test-key'


def test_prefer_search_result_uses_bocha_only_when_anysearch_has_no_documents():
    primary = SearchResult(available=True, documents=[])
    fallback = SearchResult(available=True, documents=['document'])

    assert prefer_search_result(primary, fallback) is fallback
