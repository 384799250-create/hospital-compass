from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.qinglin_client import QinglinClient, QinglinError, resolve_qinglin_key


def test_key_resolution_prefers_process_qinglin_key_and_strips_quotes(tmp_path: Path):
    dotenv = tmp_path / '.env'
    dotenv.write_text('QINGLIN_API_KEY="dotenv-key"\n', encoding='utf-8')
    assert resolve_qinglin_key({'QINGLIN_API_KEY': ' process-key '}, dotenv) == 'process-key'


def test_key_resolution_reads_project_dotenv_as_last_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('QINGLIN_API_KEY', raising=False)
    monkeypatch.delenv('API_KEY', raising=False)
    dotenv = tmp_path / '.env'
    dotenv.write_text("API_KEY='dotenv-key'\n", encoding='utf-8')
    assert resolve_qinglin_key({}, dotenv) == 'dotenv-key'


def test_client_uses_expected_envelopes_without_logging_secrets():
    requests = []

    def transport(request, timeout):
        requests.append(request)
        path = urlparse(request.full_url).path
        if path.endswith('/models'):
            return b'{"code":200,"data":[{"name":"img"}]}'
        if path.endswith('/balance'):
            return b'{"code":200,"data":{"balance":12}}'
        if path.endswith('/generate'):
            return b'{"code":200,"data":{"task_id":"task-1"}}'
        return b'{"is_final":true,"state":"success","result_url":"https://cdn.example/result.png"}'

    client = QinglinClient(api_key='secret-key', base_url='https://qinglin.test/api', transport=transport)
    assert client.list_models('image') == [{'name': 'img'}]
    assert client.balance() == {'balance': 12}
    assert client.create_task('img', 'make a cover', {'size': '1:1'}) == 'task-1'
    assert client.task_status('task-1')['result_url'].endswith('.png')
    assert all(request.headers['Authorization'] == 'Bearer secret-key' for request in requests)
    assert parse_qs(urlparse(requests[0].full_url).query) == {'type': ['image']}


def test_create_task_rejects_non_200_submission():
    client = QinglinClient(
        api_key='secret-key',
        transport=lambda request, timeout: b'{"code":403,"msg":"insufficient balance"}',
    )
    with pytest.raises(QinglinError, match='insufficient balance'):
        client.create_task('img', 'prompt', {})
