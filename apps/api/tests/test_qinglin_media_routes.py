from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.qinglin_client import QinglinError


@pytest.fixture
def client():
    return TestClient(main.app)


def test_media_routes_proxy_client(monkeypatch, client):
    class FakeClient:
        def list_models(self, media_type):
            return [{'name': f'{media_type}-model'}]

        def model_detail(self, model_name):
            return {'name': model_name, 'params': {'size': ['1:1']}}

        def balance(self):
            return {'balance': 4}

        def create_task(self, model, prompt, params):
            return 'task-123'

        def task_status(self, task_id):
            return {'is_final': True, 'state': 'success', 'result_url': 'https://cdn.example/result.png'}

    monkeypatch.setattr(main, '_qinglin_client', lambda: FakeClient())
    assert client.get('/v1/media/models?type=image').json()['models'] == [{'name': 'image-model'}]
    assert client.get('/v1/media/models/img').json()['name'] == 'img'
    assert client.get('/v1/media/balance').json() == {'balance': 4}
    created = client.post('/v1/media/tasks', json={'model': 'img', 'prompt': 'cover', 'params': {}})
    assert created.status_code == 202
    assert created.json() == {'task_id': 'task-123', 'status': 'queued'}
    assert client.get('/v1/media/tasks/task-123').json()['result_url'].endswith('.png')


def test_media_generation_checks_balance_before_submit(monkeypatch, client):
    class EmptyClient:
        def balance(self):
            return {'balance': 0}

        def create_task(self, *args, **kwargs):
            pytest.fail('must not submit when balance is empty')

    monkeypatch.setattr(main, '_qinglin_client', lambda: EmptyClient())
    response = client.post('/v1/media/tasks', json={'model': 'img', 'prompt': 'cover', 'params': {}})
    assert response.status_code == 402
    assert response.json()['detail'] == 'Qinglin balance is insufficient'


def test_media_missing_key_is_safe_503(monkeypatch, client):
    monkeypatch.setattr(main, '_qinglin_client', lambda: (_ for _ in ()).throw(QinglinError('Qinglin API key is not configured')))
    response = client.get('/v1/media/balance')
    assert response.status_code == 503
    assert 'key' in response.json()['detail'].lower()
    assert 'Bearer' not in response.text
