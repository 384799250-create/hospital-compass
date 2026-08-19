import base64
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


FEEDBACK_STATUSES = ('new', 'processed')


def database_path() -> Path:
    configured = os.environ.get('FEEDBACK_DATABASE_PATH', '').strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / 'data' / 'feedback.sqlite3'


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute(
        '''CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            contact TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''',
    )
    connection.execute(
        '''CREATE TABLE IF NOT EXISTS feedback_attachments (
            id TEXT PRIMARY KEY,
            feedback_id TEXT NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            data BLOB NOT NULL
        )''',
    )
    connection.commit()
    return connection


def _attachment_response(row: sqlite3.Row) -> dict[str, object]:
    return {
        'id': row['id'],
        'filename': row['filename'],
        'content_type': row['content_type'],
        'data': base64.b64encode(row['data']).decode('ascii'),
    }


def _feedback_response(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    item = dict(row)
    attachments = connection.execute(
        'SELECT id, filename, content_type, data FROM feedback_attachments WHERE feedback_id = ? ORDER BY id',
        (row['id'],),
    ).fetchall()
    item['attachments'] = [_attachment_response(attachment) for attachment in attachments]
    return item


def create_feedback(
    category: str,
    message: str,
    contact: str | None = None,
    attachments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    item = {
        'id': str(uuid4()),
        'category': category,
        'message': message,
        'contact': contact or None,
        'status': 'new',
        'created_at': now,
        'updated_at': now,
    }
    with _connect() as connection:
        connection.execute(
            'INSERT INTO feedback (id, category, message, contact, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (item['id'], item['category'], item['message'], item['contact'], item['status'], item['created_at'], item['updated_at']),
        )
        for attachment in attachments or []:
            connection.execute(
                'INSERT INTO feedback_attachments (id, feedback_id, filename, content_type, data) VALUES (?, ?, ?, ?, ?)',
                (
                    str(uuid4()), item['id'], str(attachment['filename']), str(attachment['content_type']),
                    base64.b64decode(str(attachment['data']), validate=True),
                ),
            )
    return item


def list_feedback(*, status: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, object]:
    with _connect() as connection:
        if status:
            rows = connection.execute(
                'SELECT * FROM feedback WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (status, limit, offset),
            ).fetchall()
            total = connection.execute('SELECT COUNT(*) FROM feedback WHERE status = ?', (status,)).fetchone()[0]
        else:
            rows = connection.execute(
                'SELECT * FROM feedback ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (limit, offset),
            ).fetchall()
            total = connection.execute('SELECT COUNT(*) FROM feedback').fetchone()[0]
        items = [_feedback_response(connection, row) for row in rows]
    return {'items': items, 'total': int(total), 'limit': limit, 'offset': offset}


def update_feedback_status(feedback_id: str, status: str) -> dict[str, object] | None:
    now = datetime.now(UTC).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            'UPDATE feedback SET status = ?, updated_at = ? WHERE id = ?',
            (status, now, feedback_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute('SELECT * FROM feedback WHERE id = ?', (feedback_id,)).fetchone()
        return _feedback_response(connection, row) if row else None
