import json
import logging
from datetime import UTC, datetime

from app.bocha_search import BochaSearchClient
from app.realtime_search import HospitalCandidate, merge_hospital_candidates


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


def test_missing_key_returns_safe_unavailable_state_without_a_request():
    client = BochaSearchClient(settings={})

    result = client.search('cardiology')

    assert result.available is False
    assert result.documents == []


def test_bearer_request_uses_key_without_logging_secret(caplog):
    captured = {}

    def transport(request, timeout):
        captured['authorization'] = request.get_header('Authorization')
        captured['timeout'] = timeout
        return FakeResponse({'data': {'webPages': {'value': []}}})

    secret = 'do-not-log-this-key'
    with caplog.at_level(logging.INFO):
        result = BochaSearchClient(
            settings={'BOCHA_API_KEY': secret}, transport=transport,
        ).search('cardiology')

    assert result.available is True
    assert captured == {'authorization': f'Bearer {secret}', 'timeout': 10.0}
    assert secret not in caplog.text


def test_search_caps_requested_result_count_at_ten():
    captured = {}

    def transport(request, timeout):
        captured['body'] = json.loads(request.data)
        return FakeResponse({'data': {'webPages': {'value': []}}})

    BochaSearchClient(
        settings={'BOCHA_API_KEY': 'test-key'}, transport=transport,
    ).search('cardiology', count=25)

    assert captured['body']['count'] == 10


def test_nonofficial_urls_are_never_marked_as_registration_links():
    candidate = HospitalCandidate.from_document(
        name='Example Hospital',
        city='Shenzhen',
        document={
            'title': 'Example Hospital appointment booking',
            'url': 'https://directory.example.org/example-hospital',
            'snippet': 'Public directory listing.',
            'fetched_at': '2026-08-07T00:00:00+00:00',
        },
    )

    assert candidate.registration_url is None
    assert candidate.sources[0].url == 'https://directory.example.org/example-hospital'


def test_same_hospital_and_city_merge_and_keep_newest_source_record():
    older = HospitalCandidate.from_document(
        name='Example Hospital', city='Shenzhen', document={
            'title': 'Example Hospital',
            'url': 'https://www.example-hospital.cn/old',
            'snippet': 'old source',
            'fetched_at': datetime(2026, 8, 6, tzinfo=UTC),
        },
    )
    newer = HospitalCandidate.from_document(
        name=' Example  Hospital ', city='Shenzhen', document={
            'title': 'Example Hospital updated',
            'url': 'https://www.example-hospital.cn/new',
            'snippet': 'new source',
            'fetched_at': datetime(2026, 8, 7, tzinfo=UTC),
        },
    )

    merged = merge_hospital_candidates([older, newer])

    assert len(merged) == 1
    assert [source.url for source in merged[0].sources] == ['https://www.example-hospital.cn/new']
