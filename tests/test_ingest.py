from pathlib import Path
from hashlib import sha256

import pytest

from app.core.errors import AppError, NotFoundError, ValidationError
from app.knowledge.chunking import chunk_text, clean_text
from app.knowledge.validation import validate_upload
from tests.conftest import make_test_settings


def test_validate_accepts_utf8_txt_and_md():
    txt = validate_upload("lesson.txt", "第一段\n第二段".encode("utf-8"), 10 * 1024 * 1024)
    md = validate_upload("lesson.md", "# 标题\n内容".encode("utf-8"), 10 * 1024 * 1024)

    assert txt.extension == ".txt"
    assert md.extension == ".md"


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("lesson.pdf", b"data", "只支持 .txt 和 .md"),
        ("lesson.txt", b"\xff\xfe", "UTF-8"),
        ("lesson.txt", b"", "空文件"),
    ],
)
def test_validate_rejects_invalid_upload(filename, content, message):
    with pytest.raises(ValidationError, match=message):
        validate_upload(filename, content, 10 * 1024 * 1024)


def test_validate_rejects_file_over_10_mb():
    with pytest.raises(ValidationError, match="10 MB"):
        validate_upload("large.txt", b"x" * (10 * 1024 * 1024 + 1), 10 * 1024 * 1024)


def test_validate_uses_filename_boundary():
    upload = validate_upload("nested/../lesson.MD", b"content", 100)

    assert upload.filename == "lesson.MD"
    assert upload.extension == ".md"


def test_chunk_text_normalizes_whitespace_and_keeps_overlap():
    text = clean_text("  第一段  \n\n\n 第二段 \r\n 第三段 ")
    chunks = chunk_text(text, chunk_size=8, chunk_overlap=2)

    assert text == "第一段\n\n第二段\n\n第三段"
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)
    assert chunks[0][-2:] in chunks[1]


def test_chunk_text_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=4, chunk_overlap=4)


def test_chunk_text_keeps_long_paragraphs_within_chunk_size():
    chunks = chunk_text("开头\n\n" + "x" * 25 + "\n\n结尾", chunk_size=10, chunk_overlap=3)

    assert all(len(chunk) <= 10 for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)
    assert any(chunks[index][-3:] in chunks[index + 1] for index in range(len(chunks) - 1))


class FakeEmbedding:
    def embed_documents(self, texts):
        return [[float(index), 1.0] for index, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.0, 1.0]


class FakeVectorStore:
    def __init__(self):
        self.records = {}
        self.collection_deleted = False

    def upsert(self, ids, documents, metadatas, embeddings):
        for vector_id, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            self.records[vector_id] = {
                "document": document,
                "metadata": metadata,
                "embedding": embedding,
            }

    def delete(self, ids):
        for vector_id in ids:
            self.records.pop(vector_id, None)

    def delete_collection(self):
        self.collection_deleted = True
        self.records.clear()


def test_knowledge_base_crud_and_cascade(db_path):
    from app.storage.knowledge_base_store import (
        create_knowledge_base,
        delete_knowledge_base,
        get_knowledge_base,
        list_knowledge_bases,
        rename_knowledge_base,
    )

    knowledge_base = create_knowledge_base("测试资料", db_path)
    assert get_knowledge_base(knowledge_base["id"], db_path)["name"] == "测试资料"
    assert rename_knowledge_base(knowledge_base["id"], "新名称", db_path)["name"] == "新名称"
    assert len(list_knowledge_bases(db_path)) == 1
    with pytest.raises(ValidationError):
        create_knowledge_base("新名称", db_path)
    with pytest.raises(ValidationError):
        rename_knowledge_base(knowledge_base["id"], " ", db_path)

    delete_knowledge_base(knowledge_base["id"], db_path)
    with pytest.raises(NotFoundError):
        get_knowledge_base(knowledge_base["id"], db_path)


def test_ingest_writes_ready_file_and_chunk_records(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_chunk_records

    knowledge_base = create_knowledge_base("测试资料", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()

    result = ingest_file(
        knowledge_base["id"],
        "lesson.md",
        "# Agent\n\n这是第一段学习资料。\n\n这是第二段。".encode("utf-8"),
        settings,
        db_path=db_path,
        embedding_function=FakeEmbedding(),
        vector_store=vector_store,
    )

    assert result.status == "ready"
    assert result.chunk_count >= 1
    assert len(vector_store.records) == result.chunk_count
    assert list_chunk_records(result.file_id, db_path)
    assert (settings.upload_dir / knowledge_base["id"] / f"{result.file_id}.source").exists()


def test_same_name_overwrite_removes_old_vector_content(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_files

    knowledge_base = create_knowledge_base("覆盖测试", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()

    first = ingest_file(
        knowledge_base["id"], "same.txt", "旧内容".encode("utf-8"), settings, db_path=db_path,
        embedding_function=FakeEmbedding(), vector_store=vector_store,
    )
    second = ingest_file(
        knowledge_base["id"], "same.txt", "新内容".encode("utf-8"), settings, db_path=db_path,
        embedding_function=FakeEmbedding(), vector_store=vector_store,
    )

    assert second.file_id == first.file_id
    assert all("旧内容" not in item["document"] for item in vector_store.records.values())
    assert any("新内容" in item["document"] for item in vector_store.records.values())
    assert len(list_files(knowledge_base["id"], db_path)) == 1


def test_invalid_overwrite_keeps_previous_ready_version(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_files

    knowledge_base = create_knowledge_base("失败隔离", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    first = ingest_file(
        knowledge_base["id"], "same.txt", "旧内容".encode("utf-8"), settings, db_path=db_path,
        embedding_function=FakeEmbedding(), vector_store=vector_store,
    )
    failed = ingest_file(
        knowledge_base["id"], "same.pdf", "新内容".encode("utf-8"), settings, db_path=db_path,
        embedding_function=FakeEmbedding(), vector_store=vector_store,
    )

    assert failed.status == "failed"
    assert failed.file_id is None
    assert list_files(knowledge_base["id"], db_path)[0]["id"] == first.file_id
    assert any("旧内容" in item["document"] for item in vector_store.records.values())


def test_knowledge_bases_have_independent_vectors(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base

    first = create_knowledge_base("甲", db_path)
    second = create_knowledge_base("乙", db_path)
    settings = make_test_settings(tmp_path, db_path)
    first_vectors = FakeVectorStore()
    second_vectors = FakeVectorStore()

    ingest_file(first["id"], "same.txt", "甲内容".encode("utf-8"), settings, db_path=db_path,
                embedding_function=FakeEmbedding(), vector_store=first_vectors)
    ingest_file(second["id"], "same.txt", "乙内容".encode("utf-8"), settings, db_path=db_path,
                embedding_function=FakeEmbedding(), vector_store=second_vectors)

    assert first_vectors.records != second_vectors.records
    assert all(item["metadata"]["knowledge_base_id"] == first["id"] for item in first_vectors.records.values())
    assert all(item["metadata"]["knowledge_base_id"] == second["id"] for item in second_vectors.records.values())


def test_delete_file_removes_application_copy_records_and_vectors(tmp_path, db_path):
    from app.knowledge.ingest import delete_file, ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_files, list_chunk_records

    knowledge_base = create_knowledge_base("删除测试", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    result = ingest_file(knowledge_base["id"], "lesson.txt", "内容".encode("utf-8"), settings, db_path=db_path,
                         embedding_function=FakeEmbedding(), vector_store=vector_store)
    stored_path = settings.upload_dir / knowledge_base["id"] / f"{result.file_id}.source"

    delete_file(knowledge_base["id"], result.file_id, settings, db_path=db_path, vector_store=vector_store)

    assert not stored_path.exists()
    assert not list_files(knowledge_base["id"], db_path)
    assert not list_chunk_records(result.file_id, db_path)
    assert not vector_store.records


def test_delete_knowledge_base_removes_copies_records_and_vectors(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import (
        create_knowledge_base,
        delete_knowledge_base,
        get_knowledge_base,
        list_files,
    )

    knowledge_base = create_knowledge_base("删除知识库", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    results = [
        ingest_file(
            knowledge_base["id"], filename, content.encode("utf-8"), settings,
            db_path=db_path, embedding_function=FakeEmbedding(), vector_store=vector_store,
        )
        for filename, content in [("one.txt", "第一份"), ("two.md", "第二份")]
    ]
    stored_paths = [
        settings.upload_dir / knowledge_base["id"] / f"{result.file_id}.source"
        for result in results
    ]

    delete_knowledge_base(
        knowledge_base["id"], db_path, settings=settings, vector_store=vector_store,
    )

    with pytest.raises(NotFoundError):
        get_knowledge_base(knowledge_base["id"], db_path)
    assert not list_files(knowledge_base["id"], db_path)
    assert not vector_store.records
    assert vector_store.collection_deleted
    assert all(not path.exists() for path in stored_paths)


def test_upsert_file_returns_existing_logical_record_on_name_conflict(db_path):
    from app.storage.knowledge_base_store import create_knowledge_base, upsert_file

    knowledge_base = create_knowledge_base("文件记录", db_path)
    first = {
        "id": "first",
        "knowledge_base_id": knowledge_base["id"],
        "original_name": "same.txt",
        "stored_path": "first.source",
        "extension": ".txt",
        "size_bytes": 1,
        "content_hash": "a",
        "status": "ready",
        "error_message": "",
        "created_at": "2026-09-11T10:00:00",
        "updated_at": "2026-09-11T10:00:00",
    }
    second = {**first, "id": "second", "stored_path": "second.source", "content_hash": "b"}

    assert upsert_file(first, db_path)["id"] == "first"
    assert upsert_file(second, db_path)["id"] == "first"


def test_embedding_failure_does_not_replace_previous_version(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_files

    class BrokenEmbedding(FakeEmbedding):
        def embed_documents(self, texts):
            raise RuntimeError("embedding unavailable")

    knowledge_base = create_knowledge_base("嵌入失败", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    first = ingest_file(knowledge_base["id"], "same.txt", "旧内容".encode("utf-8"), settings,
                        db_path=db_path, embedding_function=FakeEmbedding(), vector_store=vector_store)
    failed = ingest_file(knowledge_base["id"], "same.txt", "新内容".encode("utf-8"), settings,
                         db_path=db_path, embedding_function=BrokenEmbedding(), vector_store=vector_store)

    assert failed.status == "failed"
    assert list_files(knowledge_base["id"], db_path)[0]["id"] == first.file_id
    assert any("旧内容" in item["document"] for item in vector_store.records.values())


def test_post_vector_persistence_failure_restores_old_version(tmp_path, db_path, monkeypatch):
    import app.knowledge.ingest as ingest_module
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_chunk_records, list_files

    knowledge_base = create_knowledge_base("后置失败", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    first = ingest_file(
        knowledge_base["id"], "same.txt", "旧内容".encode("utf-8"), settings,
        db_path=db_path, embedding_function=FakeEmbedding(), vector_store=vector_store,
    )
    stored_path = settings.upload_dir / knowledge_base["id"] / f"{first.file_id}.source"
    old_chunks = list_chunk_records(first.file_id, db_path)
    original_replace = ingest_module.replace_chunk_records
    calls = 0

    def fail_once(file_id, chunks, db_path=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("chunk persistence failed")
        return original_replace(file_id, chunks, db_path)

    monkeypatch.setattr(ingest_module, "replace_chunk_records", fail_once)
    failed = ingest_file(
        knowledge_base["id"], "same.txt", "新内容".encode("utf-8"), settings,
        db_path=db_path, embedding_function=FakeEmbedding(), vector_store=vector_store,
    )

    assert failed.status == "failed"
    assert stored_path.read_bytes() == "旧内容".encode("utf-8")
    assert list_files(knowledge_base["id"], db_path)[0]["content_hash"] == sha256("旧内容".encode("utf-8")).hexdigest()
    assert list_chunk_records(first.file_id, db_path) == old_chunks
    assert any("旧内容" in item["document"] for item in vector_store.records.values())
    assert all("新内容" not in item["document"] for item in vector_store.records.values())


def test_delete_file_sqlite_failure_restores_external_resources(tmp_path, db_path, monkeypatch):
    import app.knowledge.ingest as ingest_module
    from app.knowledge.ingest import delete_file, ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, get_file

    knowledge_base = create_knowledge_base("删除补偿", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    result = ingest_file(
        knowledge_base["id"], "lesson.txt", "内容".encode("utf-8"), settings, db_path=db_path,
        embedding_function=FakeEmbedding(), vector_store=vector_store,
    )
    stored_path = settings.upload_dir / knowledge_base["id"] / f"{result.file_id}.source"
    original_delete = ingest_module.delete_file_record

    def fail_once(file_id, db_path=None):
        monkeypatch.setattr(ingest_module, "delete_file_record", original_delete)
        raise RuntimeError("sqlite delete failed")

    monkeypatch.setattr(ingest_module, "delete_file_record", fail_once)
    with pytest.raises(AppError, match="删除文件失败"):
        delete_file(knowledge_base["id"], result.file_id, settings, db_path=db_path, vector_store=vector_store)

    assert stored_path.read_bytes() == "内容".encode("utf-8")
    assert get_file(result.file_id, db_path)["id"] == result.file_id
    assert vector_store.records

    delete_file(knowledge_base["id"], result.file_id, settings, db_path=db_path, vector_store=vector_store)
    assert not stored_path.exists()
    assert not vector_store.records


def test_ingest_missing_knowledge_base_raises_not_found(tmp_path, db_path):
    from app.knowledge.ingest import ingest_file

    with pytest.raises(NotFoundError, match="知识库不存在"):
        ingest_file(
            "missing", "lesson.txt", "内容".encode("utf-8"), make_test_settings(tmp_path, db_path),
            db_path=db_path, embedding_function=FakeEmbedding(), vector_store=FakeVectorStore(),
        )


def test_delete_file_rejects_file_from_another_knowledge_base(tmp_path, db_path):
    from app.core.errors import NotFoundError
    from app.knowledge.ingest import delete_file, ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base

    first = create_knowledge_base("甲删除", db_path)
    second = create_knowledge_base("乙删除", db_path)
    settings = make_test_settings(tmp_path, db_path)
    result = ingest_file(first["id"], "lesson.txt", b"content", settings, db_path=db_path,
                         embedding_function=FakeEmbedding(), vector_store=FakeVectorStore())

    with pytest.raises(NotFoundError):
        delete_file(second["id"], result.file_id, settings, db_path=db_path, vector_store=FakeVectorStore())


def test_clear_knowledge_base_removes_files_copies_records_and_vectors(tmp_path, db_path):
    from app.knowledge.ingest import clear_knowledge_base, ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base, list_files

    knowledge_base = create_knowledge_base("清空测试", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()
    results = [
        ingest_file(
            knowledge_base["id"], filename, content.encode("utf-8"), settings,
            db_path=db_path, embedding_function=FakeEmbedding(), vector_store=vector_store,
        )
        for filename, content in [("one.txt", "第一份"), ("two.md", "第二份")]
    ]
    stored_paths = [
        settings.upload_dir / knowledge_base["id"] / f"{result.file_id}.source"
        for result in results
    ]

    clear_knowledge_base(knowledge_base["id"], settings, db_path=db_path, vector_store=vector_store)

    assert not list_files(knowledge_base["id"], db_path)
    assert not vector_store.records
    assert all(not path.exists() for path in stored_paths)


def test_vector_store_uses_one_collection_per_knowledge_base(tmp_path, monkeypatch):
    import app.knowledge.vector_store as vector_store_module

    created = []

    class FakeChroma:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(vector_store_module, "Chroma", FakeChroma)
    settings = make_test_settings(tmp_path, tmp_path / "app.sqlite3")

    vector_store_module.get_vector_store("kb-one", settings, embedding_function=FakeEmbedding())
    vector_store_module.get_vector_store("kb-two", settings, embedding_function=FakeEmbedding())

    assert [item["collection_name"] for item in created] == ["kb_kbone", "kb_kbtwo"]
    assert all(item["persist_directory"] == str(settings.chroma_dir) for item in created)
    assert all(item["collection_metadata"] == {"hnsw:space": "cosine"} for item in created)
