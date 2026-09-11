from datetime import datetime
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.core.database import get_connection, init_db
from app.core.errors import NotFoundError, ValidationError


DEFAULT_DB_PATH = Path("data/app.sqlite3")


def _db_path(db_path: Path | None) -> Path:
    return db_path or DEFAULT_DB_PATH


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _row(row):
    return dict(row) if row is not None else None


def _connection(db_path: Path | None):
    path = _db_path(db_path)
    init_db(path)
    return get_connection(path)


def _require_name(name: str) -> str:
    value = name.strip() if isinstance(name, str) else ""
    if not value:
        raise ValidationError("知识库名称不能为空")
    return value


def create_knowledge_base(name: str, db_path: Path | None = None) -> dict:
    name = _require_name(name)
    now = _now()
    record = {"id": str(uuid4()), "name": name, "created_at": now, "updated_at": now}
    try:
        with _connection(db_path) as conn:
            conn.execute(
                "INSERT INTO knowledge_bases (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (record["id"], name, now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValidationError("知识库名称已存在") from exc
    return record


def list_knowledge_bases(db_path: Path | None = None) -> list[dict]:
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM knowledge_bases ORDER BY created_at, id"
        ).fetchall()
    return [_row(row) for row in rows]


def get_knowledge_base(knowledge_base_id: str, db_path: Path | None = None) -> dict:
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, created_at, updated_at FROM knowledge_bases WHERE id = ?",
            (knowledge_base_id,),
        ).fetchone()
    if row is None:
        raise NotFoundError("知识库不存在")
    return _row(row)


def rename_knowledge_base(knowledge_base_id: str, name: str, db_path: Path | None = None) -> dict:
    name = _require_name(name)
    now = _now()
    try:
        with _connection(db_path) as conn:
            cursor = conn.execute(
                "UPDATE knowledge_bases SET name = ?, updated_at = ? WHERE id = ?",
                (name, now, knowledge_base_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("知识库不存在")
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValidationError("知识库名称已存在") from exc
    return get_knowledge_base(knowledge_base_id, db_path)


def delete_knowledge_base(knowledge_base_id: str, db_path: Path | None = None) -> None:
    with _connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (knowledge_base_id,))
        if cursor.rowcount == 0:
            raise NotFoundError("知识库不存在")
        conn.commit()


def list_files(knowledge_base_id: str, db_path: Path | None = None) -> list[dict]:
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE knowledge_base_id = ? ORDER BY created_at, id",
            (knowledge_base_id,),
        ).fetchall()
    return [_row(row) for row in rows]


def get_file(file_id: str, db_path: Path | None = None) -> dict:
    with _connection(db_path) as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise NotFoundError("文件不存在")
    return _row(row)


def upsert_file(file_record: dict, db_path: Path | None = None) -> dict:
    fields = (
        "id", "knowledge_base_id", "original_name", "stored_path", "extension",
        "size_bytes", "content_hash", "status", "error_message", "created_at", "updated_at",
    )
    values = tuple(file_record[field] for field in fields)
    with _connection(db_path) as conn:
        conn.execute(
            "INSERT INTO files (" + ", ".join(fields) + ") VALUES (" + ", ".join("?" for _ in fields) + ") "
            "ON CONFLICT(knowledge_base_id, original_name) DO UPDATE SET "
            + ", ".join(f"{field}=excluded.{field}" for field in fields if field not in {"id", "created_at"}),
            values,
        )
        row = conn.execute(
            "SELECT * FROM files WHERE knowledge_base_id = ? AND original_name = ?",
            (file_record["knowledge_base_id"], file_record["original_name"]),
        ).fetchone()
        conn.commit()
    return _row(row)


def delete_file_record(file_id: str, db_path: Path | None = None) -> None:
    with _connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        if cursor.rowcount == 0:
            raise NotFoundError("文件不存在")
        conn.commit()


def clear_file_records(knowledge_base_id: str, db_path: Path | None = None) -> None:
    with _connection(db_path) as conn:
        conn.execute("DELETE FROM files WHERE knowledge_base_id = ?", (knowledge_base_id,))
        conn.commit()


def replace_chunk_records(file_id: str, chunks: list[dict], db_path: Path | None = None) -> None:
    with _connection(db_path) as conn:
        conn.execute("DELETE FROM document_chunks WHERE file_id = ?", (file_id,))
        for chunk in chunks:
            conn.execute(
                "INSERT INTO document_chunks "
                "(id, knowledge_base_id, file_id, chunk_index, vector_id, content_hash, content, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk["id"], chunk["knowledge_base_id"], chunk["file_id"], chunk["chunk_index"],
                    chunk["vector_id"], chunk["content_hash"], chunk["content"], chunk["created_at"],
                ),
            )
        conn.commit()


def list_chunk_records(file_id: str, db_path: Path | None = None) -> list[dict]:
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM document_chunks WHERE file_id = ? ORDER BY chunk_index",
            (file_id,),
        ).fetchall()
    return [_row(row) for row in rows]
