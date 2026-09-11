from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.core.errors import AppError, NotFoundError
from app.knowledge.chunking import chunk_text
from app.knowledge.validation import ValidatedUpload, validate_upload
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
        store.upsert(
            ids=vector_ids,
            documents=chunks,
            metadatas=metadata,
            embeddings=embeddings,
        )
        stale_ids = [item["vector_id"] for item in old_chunk_records if item["vector_id"] not in vector_ids]
        if stale_ids:
            store.delete(ids=stale_ids)

        stored_path = _stored_path(settings, knowledge_base_id, file_id)
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
    except Exception as exc:
        return _upload_result(filename, exc)


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
    try:
        store = _vector_store(knowledge_base_id, settings, None, vector_store)
        vector_ids = [item["vector_id"] for item in chunk_records]
        if vector_ids:
            store.delete(ids=vector_ids)
        stored_path = Path(file_record["stored_path"])
        if stored_path.exists():
            stored_path.unlink()
        delete_file_record(file_id, db_path)
    except Exception as exc:
        raise AppError(f"删除文件失败：{exc}") from exc


def clear_knowledge_base(
    knowledge_base_id: str,
    settings,
    db_path: Path | None = None,
    vector_store=None,
) -> None:
    get_knowledge_base(knowledge_base_id, db_path)
    for file_record in list_files(knowledge_base_id, db_path):
        delete_file(knowledge_base_id, file_record["id"], settings, db_path, vector_store)
