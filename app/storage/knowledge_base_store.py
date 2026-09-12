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


def get_chunk_records(
    knowledge_base_id: str,
    source_chunk_ids: list[str],
    db_path: Path | None = None,
) -> list[dict]:
    """Read the requested chunks directly, preserving the requested order."""
    requested = list(dict.fromkeys(source_chunk_ids or []))
    if not requested:
        return []
    placeholders = ", ".join("?" for _ in requested)
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT dc.*, f.original_name AS source "
            "FROM document_chunks dc LEFT JOIN files f ON f.id = dc.file_id "
            "WHERE dc.knowledge_base_id = ? "
            f"AND (dc.vector_id IN ({placeholders}) OR dc.id IN ({placeholders}))",
            (knowledge_base_id, *requested, *requested),
        ).fetchall()
    by_id = {}
    for row in rows:
        item = dict(row)
        by_id[item["vector_id"]] = item
        by_id[item["id"]] = item
    results = []
    for source_chunk_id in requested:
        item = by_id.get(source_chunk_id)
        if item is None:
            continue
        source = item.get("source") or ""
        results.append(
            {
                "text": item["content"],
                "source": source,
                "title": Path(source).stem if source else "",
                "chunk_id": item["vector_id"],
                "file_id": item["file_id"],
                "knowledge_base_id": knowledge_base_id,
                "score": 1.0,
            }
        )
    return results
