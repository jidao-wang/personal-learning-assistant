from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from app.core.database import get_connection, init_db
from app.core.errors import NotFoundError, ValidationError


DEFAULT_DB_PATH = Path("data/app.sqlite3")


def _db_path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _connection(db_path: str | Path | None):
    path = _db_path(db_path)
    init_db(path)
    return get_connection(path)


def _session_record(row) -> dict:
    return dict(row)


def _message_record(row) -> dict:
    record = dict(row)
    record["citations"] = json.loads(record.pop("citations_json") or "[]")
    return record


def create_session(knowledge_base_id: str | None, db_path=None) -> dict:
    now = _now()
    record = {
        "id": str(uuid4()),
        "knowledge_base_id": knowledge_base_id,
        "title": "",
        "created_at": now,
        "updated_at": now,
    }
    with _connection(db_path) as conn:
        if knowledge_base_id is not None:
            row = conn.execute(
                "SELECT id FROM knowledge_bases WHERE id = ?", (knowledge_base_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("知识库不存在")
        conn.execute(
            "INSERT INTO chat_sessions (id, knowledge_base_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            tuple(record.values()),
        )
        conn.commit()
    return record


def get_session(session_id: str, db_path=None) -> dict:
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, knowledge_base_id, title, created_at, updated_at "
            "FROM chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError("会话不存在")
    return _session_record(row)


def list_sessions(db_path=None) -> list[dict]:
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, knowledge_base_id, title, created_at, updated_at "
            "FROM chat_sessions ORDER BY created_at, id"
        ).fetchall()
    return [_session_record(row) for row in rows]


def add_message(
    session_id: str,
    role: str,
    content: str,
    task_type: str,
    citations: list[dict] | None = None,
    db_path=None,
) -> dict:
    if role not in {"user", "assistant", "system"}:
        raise ValidationError("消息角色无效")
    if not isinstance(content, str):
        raise ValidationError("消息内容无效")
    citations = [] if citations is None else citations
    now = _now()
    with _connection(db_path) as conn:
        session = conn.execute(
            "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise NotFoundError("会话不存在")
        cursor = conn.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, task_type, citations_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, task_type, json.dumps(citations, ensure_ascii=False), now),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, session_id, role, content, task_type, citations_json, created_at "
            "FROM chat_messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _message_record(row)


def list_messages(session_id: str, db_path=None) -> list[dict]:
    with _connection(db_path) as conn:
        session = conn.execute(
            "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise NotFoundError("会话不存在")
        rows = conn.execute(
            "SELECT id, session_id, role, content, task_type, citations_json, created_at "
            "FROM chat_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [_message_record(row) for row in rows]
