from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import app.main as main


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('FEEDBACK_DATABASE_PATH', str(tmp_path / 'feedback.sqlite3'))
    monkeypatch.setenv('FEEDBACK_ADMIN_TOKEN', 'test-admin-token')
    main.FEEDBACK_SUBMISSION_TIMES.clear()
    return TestClient(main.app)


def test_public_feedback_can_be_submitted_and_admin_can_list_it(client: TestClient):
    response = client.post('/v1/feedback', json={
        'category': 'improvement',
        'message': '希望区域切换时保留当前滚动位置。',
        'contact': 'user@example.com',
    })

    assert response.status_code == 201
    feedback_id = response.json()['id']
    assert response.json()['status'] == 'new'

    unauthorized = client.get('/admin/feedback')
    assert unauthorized.status_code == 401

    session = client.post('/admin/feedback/session', json={'token': 'test-admin-token'})
    assert session.status_code == 200
    admin_token = session.json()['token']
    listed = client.get('/admin/feedback', headers={'X-Feedback-Admin-Token': admin_token})
    assert listed.status_code == 200
    assert listed.json()['total'] == 1
    assert listed.json()['items'][0]['id'] == feedback_id
    assert listed.json()['items'][0]['message'] == '希望区域切换时保留当前滚动位置。'


def test_admin_can_mark_feedback_processed(client: TestClient):
    created = client.post('/v1/feedback', json={
        'category': 'bug',
        'message': '提交结果后页面没有更新，请检查。',
    })
    feedback_id = created.json()['id']

    updated = client.patch(
        f'/admin/feedback/{feedback_id}',
        headers={'X-Feedback-Admin-Token': 'test-admin-token'},
        json={'status': 'processed'},
    )

    assert updated.status_code == 200
    assert updated.json()['status'] == 'processed'


def test_feedback_message_length_is_validated(client: TestClient):
    response = client.post('/v1/feedback', json={'category': 'bug', 'message': '太短'})

    assert response.status_code == 400


def test_feedback_can_store_and_return_image_attachment(client: TestClient):
    response = client.post('/v1/feedback', json={
        'category': 'bug',
        'message': '截图说明了反馈窗口在提交时出现的问题。',
        'attachments': [{
            'filename': 'issue.png',
            'content_type': 'image/png',
            'data': 'iVBORw0KGgo=',
        }],
    })

    assert response.status_code == 201
    feedback_id = response.json()['id']
    admin = client.get(
        '/admin/feedback',
        headers={'X-Feedback-Admin-Token': 'test-admin-token'},
    )
    assert admin.status_code == 200
    item = next(entry for entry in admin.json()['items'] if entry['id'] == feedback_id)
    assert item['attachments'][0]['filename'] == 'issue.png'
    assert item['attachments'][0]['content_type'] == 'image/png'
    assert item['attachments'][0]['data'] == 'iVBORw0KGgo='


def test_feedback_rejects_unsupported_or_oversized_attachment(client: TestClient):
    unsupported = client.post('/v1/feedback', json={
        'category': 'bug',
        'message': '上传了不支持的附件格式。',
        'attachments': [{'filename': 'issue.gif', 'content_type': 'image/gif', 'data': 'R0lGODlh'}],
    })
    assert unsupported.status_code == 400


def test_feedback_submission_is_rate_limited_per_source(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('FEEDBACK_MAX_PER_MINUTE', '2')
    payload = {'category': 'other', 'message': '这是一个足够长的反馈内容。'}

    assert client.post('/v1/feedback', json=payload).status_code == 201
    assert client.post('/v1/feedback', json=payload).status_code == 201
    assert client.post('/v1/feedback', json=payload).status_code == 429
