from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app.core.database import get_connection, init_db
from app.core.errors import ValidationError


DEFAULT_DB_PATH = Path("data/app.sqlite3")
_SENSITIVE_WORDS = (
    "api_key", "apikey", "password", "passwd", "token", "secret",
    "身份证", "手机号", "手机号码", "银行卡", "信用卡",
)


def _db_path(db_path) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connection(db_path):
    path = _db_path(db_path)
    init_db(path)
    return get_connection(path)


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def parse_preference_request(user_input: str) -> dict | None:
    text = (user_input or "").strip()
    match = re.match(r"^记住我(?:喜欢|希望)(.+)$", text, re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return {"key": "answer_style", "value": value} if value else None


def _contains_sensitive_value(value: str) -> bool:
    lowered = value.lower()
    if any(word in lowered for word in _SENSITIVE_WORDS):
        return True
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", value):
        return True
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", value):
        return True
    return bool(re.search(r"(?<!\d)\d{12,19}(?!\d)", value))


def save_preference(key: str, value: str, db_path=None) -> dict:
    key = str(key).strip()
    value = str(value).strip()
    if not key or not value:
        raise ValidationError("偏好内容不能为空")
    if _contains_sensitive_value(value):
        raise ValidationError("出于安全原因，不能保存敏感信息")
    updated_at = _now()
    with _connection(db_path) as conn:
        conn.execute(
            "INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, updated_at),
        )
        conn.commit()
    return {"key": key, "value": value, "updated_at": updated_at}


def get_preferences(db_path=None) -> dict[str, str]:
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_preferences ORDER BY key"
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}
