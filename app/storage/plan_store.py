from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.database import get_connection, init_db
from app.core.errors import NotFoundError, ValidationError


DEFAULT_DB_PATH = Path("data/app.sqlite3")


def _db_path(db_path) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connection(db_path):
    path = _db_path(db_path)
    init_db(path)
    return get_connection(path)


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _decode(row):
    if row is None:
        return None
    result = dict(row)
    try:
        result["scope"] = json.loads(result.pop("scope_json"))
    except (TypeError, json.JSONDecodeError):
        result["scope"] = {}
    return result


def create_plan(
    knowledge_base_id: str,
    title: str,
    content: str,
    scope: dict,
    db_path=None,
) -> dict:
    if not str(title).strip() or not str(content).strip():
        raise ValidationError("计划标题和内容不能为空")
    if not isinstance(scope, dict):
        raise ValidationError("计划范围必须是对象")
    now = _now()
    plan = {
        "id": str(uuid4()),
        "knowledge_base_id": knowledge_base_id,
        "title": str(title).strip(),
        "content": str(content),
        "scope": scope,
        "created_at": now,
        "updated_at": now,
    }
    with _connection(db_path) as conn:
        if conn.execute(
            "SELECT 1 FROM knowledge_bases WHERE id = ?", (knowledge_base_id,)
        ).fetchone() is None:
            raise NotFoundError("知识库不存在")
        conn.execute(
            "INSERT INTO learning_plans "
            "(id, knowledge_base_id, title, content, scope_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                plan["id"], plan["knowledge_base_id"], plan["title"], plan["content"],
                json.dumps(plan["scope"], ensure_ascii=False), plan["created_at"], plan["updated_at"],
            ),
        )
        conn.commit()
    return plan


def get_plan(plan_id: str, db_path=None) -> dict:
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM learning_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    if row is None:
        raise NotFoundError("学习计划不存在")
    return _decode(row)


def update_plan(plan_id: str, content: str, db_path=None) -> dict:
    if not str(content).strip():
        raise ValidationError("计划内容不能为空")
    updated_at = _now()
    with _connection(db_path) as conn:
        cursor = conn.execute(
            "UPDATE learning_plans SET content = ?, updated_at = ? WHERE id = ?",
            (str(content), updated_at, plan_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("学习计划不存在")
        conn.commit()
    return get_plan(plan_id, db_path)
