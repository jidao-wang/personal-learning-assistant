from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.core.errors import AppError, NotFoundError
from app.knowledge.chunking import chunk_text
from app.knowledge.validation import validate_upload
from app.storage.knowledge_base_store import (
    _now,
    delete_file_record,
    get_file,
    get_knowledge_base,
    list_chunk_records,
    list_files,
    replace_chunk_records,
    upsert_file,
)


@dataclass
class FileIngestResult:
    file_id: str | None
    filename: str
    status: str
    error_message: str = ""
    chunk_count: int = 0


def _stored_path(settings, knowledge_base_id: str, file_id: str) -> Path:
    return Path(settings.upload_dir) / knowledge_base_id / f"{file_id}.source"


def _vector_store(knowledge_base_id, settings, embedding_function, vector_store):
    if vector_store is not None:
        return vector_store
    from app.knowledge.vector_store import get_vector_store

    return get_vector_store(knowledge_base_id, settings, embedding_function)


def _upload_result(filename: str | None, error: Exception) -> FileIngestResult:
    return FileIngestResult(
        file_id=None,
        filename=filename or "",
        status="failed",
        error_message=str(error),
    )


def _snapshot_vectors(store, vector_ids: list[str]) -> dict | None:
    if not vector_ids:
        return {}
    records = getattr(store, "records", None)
    if isinstance(records, dict):
        return {
            vector_id: deepcopy(records[vector_id])
            for vector_id in vector_ids
            if vector_id in records
        }
    get = getattr(store, "get", None)
    if get is None:
        return None
    result = get(ids=vector_ids, include=["documents", "metadatas", "embeddings"])
    ids = result.get("ids", [])
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    embeddings = result.get("embeddings") or []
    return {
        vector_id: {
            "document": documents[index],
            "metadata": metadatas[index],
            "embedding": embeddings[index] if index < len(embeddings) else None,
        }
        for index, vector_id in enumerate(ids)
    }


def _upsert_vector_snapshot(store, snapshot: dict) -> None:
    if not snapshot:
        return
    records = [snapshot[vector_id] for vector_id in snapshot]
    store.upsert(
        ids=list(snapshot),
        documents=[record["document"] for record in records],
        metadatas=[record["metadata"] for record in records],
        embeddings=[record["embedding"] for record in records],
    )


def _delete_vector_collection(store) -> None:
    delete_collection = getattr(store, "delete_collection", None)
    if callable(delete_collection):
        delete_collection()
        return
    client = getattr(store, "_client", None)
    collection = getattr(store, "_collection", None)
    collection_name = getattr(collection, "name", None)
    if client is not None and collection_name:
        client.delete_collection(name=collection_name)


def _restore_file(path: Path, content: bytes | None) -> None:
    if content is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _rollback_ingest(
    *,
    store,
    vector_ids: list[str],
    stale_ids: list[str],
    old_vectors: dict | None,
    stored_path: Path,
    old_content: bytes | None,
    existing: dict | None,
    old_chunks: list[dict],
    file_id: str,
    db_path: Path | None,
) -> list[Exception]:
    errors = []
    try:
        store.delete(ids=list(dict.fromkeys(vector_ids + stale_ids)))
        if old_vectors is not None:
            _upsert_vector_snapshot(store, old_vectors)
    except Exception as exc:
        errors.append(exc)
    try:
        _restore_file(stored_path, old_content)
    except Exception as exc:
        errors.append(exc)
    try:
        if existing is None:
            delete_file_record(file_id, db_path)
        else:
            upsert_file(existing, db_path)
            replace_chunk_records(file_id, old_chunks, db_path)
    except NotFoundError:
        if existing is not None:
            errors.append(NotFoundError("无法恢复文件记录"))
    except Exception as exc:
        errors.append(exc)
    return errors


def ingest_file(
    knowledge_base_id: str,
    filename: str | None,
    content: bytes,
    settings,
    db_path: Path | None = None,
    embedding_function=None,
    vector_store=None,
) -> FileIngestResult:
    try:
        upload = validate_upload(filename, content, settings.max_file_size)
    except Exception as exc:
        return _upload_result(filename, exc)

    try:
        get_knowledge_base(knowledge_base_id, db_path)
        chunks = chunk_text(upload.text, settings.chunk_size, settings.chunk_overlap)
        content_hash = sha256(content).hexdigest()
        existing = next(
            (item for item in list_files(knowledge_base_id, db_path)
             if item["original_name"] == upload.filename),
            None,
        )
        file_id = existing["id"] if existing else str(uuid4())
        stored_path = _stored_path(settings, knowledge_base_id, file_id)
        old_content = stored_path.read_bytes() if stored_path.exists() else None
        vectors = embedding_function
        if vectors is None:
            from app.knowledge.embeddings import DashScopeEmbeddingAdapter

            vectors = DashScopeEmbeddingAdapter(
                model=settings.embedding_model,
                api_key=settings.api_key,
                dimension=settings.embedding_dimension,
            )
        embeddings = vectors.embed_documents(chunks)
        store = _vector_store(knowledge_base_id, settings, vectors, vector_store)
        vector_ids = [f"{file_id}:{index}" for index in range(len(chunks))]
        metadata = [
            {
                "knowledge_base_id": knowledge_base_id,
                "file_id": file_id,
                "source": upload.filename,
                "title": Path(upload.filename).stem,
                "chunk_id": vector_id,
                "content_hash": content_hash,
                "index_version": "v1",
            }
            for vector_id in vector_ids
        ]
        old_chunk_records = list_chunk_records(file_id, db_path) if existing else []
        old_vector_ids = [item["vector_id"] for item in old_chunk_records]
        old_vectors = _snapshot_vectors(store, old_vector_ids)
        if old_vector_ids and old_vectors is None:
            raise AppError("无法获取旧向量，已取消覆盖")
        mutation_started = True
        store.upsert(
            ids=vector_ids,
            documents=chunks,
            metadatas=metadata,
            embeddings=embeddings,
        )
        stale_ids = [item["vector_id"] for item in old_chunk_records if item["vector_id"] not in vector_ids]
        if stale_ids:
            store.delete(ids=stale_ids)

        stored_path.parent.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(content)
        now = _now()
        file_record = {
            "id": file_id,
            "knowledge_base_id": knowledge_base_id,
            "original_name": upload.filename,
            "stored_path": str(stored_path),
            "extension": upload.extension,
            "size_bytes": upload.size_bytes,
            "content_hash": content_hash,
            "status": "ready",
            "error_message": "",
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        upsert_file(file_record, db_path)
        replace_chunk_records(
            file_id,
            [
                {
                    "id": str(uuid4()),
                    "knowledge_base_id": knowledge_base_id,
                    "file_id": file_id,
                    "chunk_index": index,
                    "vector_id": vector_id,
                    "content_hash": content_hash,
                    "content": chunk,
                    "created_at": now,
                }
                for index, (vector_id, chunk) in enumerate(zip(vector_ids, chunks))
            ],
            db_path,
        )
        return FileIngestResult(file_id, upload.filename, "ready", chunk_count=len(chunks))
    except NotFoundError:
        raise
    except Exception as exc:
        rollback_errors = _rollback_ingest(
            store=locals().get("store"),
            vector_ids=locals().get("vector_ids", []),
            stale_ids=locals().get("stale_ids", []),
            old_vectors=locals().get("old_vectors"),
            stored_path=locals().get("stored_path", Path()),
            old_content=locals().get("old_content"),
            existing=locals().get("existing"),
            old_chunks=locals().get("old_chunk_records", []),
            file_id=locals().get("file_id", ""),
            db_path=db_path,
        ) if locals().get("store") is not None and locals().get("mutation_started") else []
        message = str(exc)
        if rollback_errors:
            message += "；补偿失败：" + "；".join(str(error) for error in rollback_errors)
        return FileIngestResult(
            file_id=None,
            filename=filename or "",
            status="failed",
            error_message=message,
        )


def _file_for_knowledge_base(knowledge_base_id: str, file_id: str, db_path: Path | None) -> dict:
    file_record = get_file(file_id, db_path)
    if file_record["knowledge_base_id"] != knowledge_base_id:
        raise NotFoundError("文件不存在")
    return file_record


def delete_file(
    knowledge_base_id: str,
    file_id: str,
    settings,
    db_path: Path | None = None,
    vector_store=None,
) -> None:
    file_record = _file_for_knowledge_base(knowledge_base_id, file_id, db_path)
    chunk_records = list_chunk_records(file_id, db_path)
    stored_path = Path(file_record["stored_path"])
    old_content = stored_path.read_bytes() if stored_path.exists() else None
    vector_ids = [item["vector_id"] for item in chunk_records]
    try:
        store = _vector_store(knowledge_base_id, settings, None, vector_store)
        vector_snapshot = _snapshot_vectors(store, vector_ids)
        if vector_ids and vector_snapshot is None:
            raise AppError("无法获取待删除向量，已取消删除")
        if vector_ids:
            store.delete(ids=vector_ids)
        if stored_path.exists():
            stored_path.unlink()
        delete_file_record(file_id, db_path)
    except Exception as exc:
        rollback_errors = []
        try:
            if vector_ids and "vector_snapshot" in locals() and vector_snapshot is not None:
                _upsert_vector_snapshot(store, vector_snapshot)
            _restore_file(stored_path, old_content)
        except Exception as rollback_exc:
            rollback_errors.append(rollback_exc)
        try:
            upsert_file(file_record, db_path)
            replace_chunk_records(file_id, chunk_records, db_path)
        except Exception as rollback_exc:
            rollback_errors.append(rollback_exc)
        message = f"删除文件失败：{exc}"
        if rollback_errors:
            message += "；补偿失败：" + "；".join(str(error) for error in rollback_errors)
        raise AppError(message) from exc


def clear_knowledge_base(
    knowledge_base_id: str,
    settings,
    db_path: Path | None = None,
    vector_store=None,
) -> None:
    get_knowledge_base(knowledge_base_id, db_path)
    for file_record in list_files(knowledge_base_id, db_path):
        delete_file(knowledge_base_id, file_record["id"], settings, db_path, vector_store)
    if vector_store is not None:
        _delete_vector_collection(vector_store)
