import os
import tempfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


# Import-time application setup is redirected to a disposable directory.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="learning-assistant-api-")

from app.main import app  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import init_db  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.storage import chat_store  # noqa: E402
from app.storage.knowledge_base_store import create_knowledge_base  # noqa: E402


client = TestClient(app)


@pytest.fixture
def runtime(tmp_path):
    db_path = tmp_path / "api.sqlite3"
    init_db(db_path)
    settings = Settings(
        api_key="test-key",
        base_url="https://example.test/v1",
        chat_model="test-chat",
        embedding_model="test-embedding",
        embedding_dimension=None,
        timeout_seconds=1,
        temperature=0,
        chunk_size=20,
        chunk_overlap=3,
        top_k=3,
        score_threshold=0,
        max_file_size=10 * 1024 * 1024,
        data_dir=tmp_path,
        upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma",
        db_path=db_path,
        host="127.0.0.1",
        port=8000,
    )
    old_runtime = getattr(app.state, "runtime", None)
    app.state.runtime = SimpleNamespace(
        settings=settings,
        db_path=db_path,
        embedding_function=None,
        vector_store=None,
        llm_client=None,
        compiled_graph=None,
    )
    yield settings, db_path
    if old_runtime is None:
        del app.state.runtime
    else:
        app.state.runtime = old_runtime


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_chat_rejects_empty_message():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_create_and_list_knowledge_bases(runtime):
    created = client.post(
        "/api/knowledge-bases",
        json={"name": "API 测试知识库"},
    )
    assert created.status_code == 200
    knowledge_base_id = created.json()["id"]

    listed = client.get("/api/knowledge-bases")
    assert listed.status_code == 200
    assert any(item["id"] == knowledge_base_id for item in listed.json())


def test_knowledge_base_crud_and_file_listing(runtime, monkeypatch):
    created = client.post("/api/knowledge-bases", json={"name": "原名称"}).json()
    knowledge_base_id = created["id"]

    renamed = client.patch(
        f"/api/knowledge-bases/{knowledge_base_id}",
        json={"name": "新名称"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "新名称"
    assert client.get(f"/api/knowledge-bases/{knowledge_base_id}/files").json() == []

    monkeypatch.setattr(
        "app.api.routes.delete_file",
        lambda *args, **kwargs: None,
    )
    assert client.delete(f"/api/knowledge-bases/{knowledge_base_id}/files/file-1").status_code == 204
    monkeypatch.setattr(
        "app.api.routes.clear_knowledge_base",
        lambda *args, **kwargs: None,
    )
    assert client.delete(f"/api/knowledge-bases/{knowledge_base_id}/files").status_code == 204


def test_upload_reads_each_file_once_and_continues_after_failure(runtime, monkeypatch):
    calls = []

    def fake_ingest(knowledge_base_id, filename, content, settings, **kwargs):
        calls.append((filename, content))
        if filename == "bad.md":
            raise ValueError("embedding failed")
        return SimpleNamespace(
            file_id="file-good",
            filename=filename,
            status="ready",
            error_message="",
            chunk_count=1,
        )

    monkeypatch.setattr("app.api.routes.ingest_file", fake_ingest)
    knowledge_base_id = client.post(
        "/api/knowledge-bases", json={"name": "上传测试"}
    ).json()["id"]
    response = client.post(
        f"/api/knowledge-bases/{knowledge_base_id}/files",
        files=[
            ("files", ("good.md", b"good", "text/markdown")),
            ("files", ("bad.md", b"bad", "text/markdown")),
        ],
    )

    assert response.status_code == 200
    assert [item["filename"] for item in response.json()] == ["good.md", "bad.md"]
    assert response.json()[1]["status"] == "failed"
    assert calls == [("good.md", b"good"), ("bad.md", b"bad")]


def test_chat_persists_user_and_assistant_messages(runtime, monkeypatch):
    knowledge_base_id = client.post(
        "/api/knowledge-bases", json={"name": "聊天测试"}
    ).json()["id"]
    session_id = client.post(
        "/api/chat/sessions", json={"knowledge_base_id": knowledge_base_id}
    ).json()["id"]
    def fake_run_agent(*args, **kwargs):
        assert chat_store.list_messages(session_id, app.state.runtime.db_path) == []
        return {
            "task_type": "qa",
            "answer": "回答",
            "citations": [],
            "workspace_type": "",
            "workspace_id": "",
            "statistics": {},
        }

    monkeypatch.setattr("app.api.routes.run_agent", fake_run_agent)

    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "问题", "knowledge_base_id": knowledge_base_id},
    )
    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "task_type": "qa",
        "answer": "回答",
        "citations": [],
        "workspace_type": "",
        "workspace_id": "",
        "statistics": {},
    }
    messages = chat_store.list_messages(session_id, app.state.runtime.db_path)
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "问题"),
        ("assistant", "回答"),
    ]


def test_chat_without_session_creates_one_and_configuration_error_is_readable(runtime, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.run_agent",
        lambda *args, **kwargs: {
            "task_type": "chat",
            "answer": "请先在 .env 中配置 DASHSCOPE_API_KEY",
        },
    )
    response = client.post("/api/chat", json={"message": "你好"})
    assert response.status_code == 200
    assert response.json()["session_id"]
    assert "DASHSCOPE_API_KEY" in response.json()["answer"]


def test_sessions_can_be_created_listed_and_loaded(runtime):
    created = client.post("/api/chat/sessions", json={}).json()
    assert created["knowledge_base_id"] is None
    assert client.get("/api/chat/sessions").status_code == 200
    loaded = client.get(f"/api/chat/sessions/{created['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["messages"] == []


def test_review_routes_validate_counts_hide_answer_material_and_lock_submission(runtime, monkeypatch):
    knowledge_base_id = client.post(
        "/api/knowledge-bases", json={"name": "复习测试"}
    ).json()["id"]
    question = {
        "id": "question-1",
        "question_type": "choice",
        "prompt": "题目",
        "options": [{"label": label, "text": label} for label in "ABCD"],
        "correct_answer": "A",
        "reference_answer": "内部参考答案",
        "rubric": "内部评分标准",
        "knowledge_point": "知识点",
        "source_chunk_ids": [],
    }
    monkeypatch.setattr(
        "app.api.routes.generate_review",
        lambda *args, **kwargs: {
            "review_session_id": "review-1",
            "questions": [question],
            "scope": {"file_ids": []},
        },
    )
    created = client.post(
        "/api/reviews",
        json={"knowledge_base_id": knowledge_base_id, "choice_count": 1},
    )
    assert created.status_code == 200
    public_question = created.json()["questions"][0]
    assert public_question["prompt"] == "题目"
    assert "correct_answer" not in public_question
    assert "rubric" not in public_question
    assert "内部参考答案" not in created.text

    monkeypatch.setattr(
        "app.api.routes.get_review_session",
        lambda *args, **kwargs: {"id": "review-1", "status": "draft"},
    )
    monkeypatch.setattr(
        "app.api.routes.save_draft",
        lambda *args, **kwargs: [{"question_id": "question-1", "status": "draft"}],
    )
    draft = client.patch(
        "/api/reviews/review-1/draft",
        json={"answers": [{"question_id": "question-1", "answer_text": "A"}]},
    )
    assert draft.status_code == 200
    monkeypatch.setattr(
        "app.api.routes.submit_review",
        lambda *args, **kwargs: {
            "review_session_id": "review-1",
            "status": "submitted",
            "total_score": 100.0,
            "answers": [{"question_id": "question-1", "score": 100.0}],
        },
    )
    submitted = client.post("/api/reviews/review-1/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"


def test_review_count_validation_is_returned_as_app_error(runtime):
    response = client.post(
        "/api/reviews",
        json={"knowledge_base_id": "kb-1"},
    )
    assert response.status_code == 400
    assert response.json()["message"] == "至少选择一种题型"


def test_plan_routes_return_missing_fields_then_save_and_update(runtime, monkeypatch):
    knowledge_base_id = client.post(
        "/api/knowledge-bases", json={"name": "计划测试"}
    ).json()["id"]
    missing = client.post(
        "/api/plans",
        json={"knowledge_base_id": knowledge_base_id, "goal": "掌握 Agent"},
    )
    assert missing.status_code == 200
    assert missing.json() == {
        "status": "needs_input",
        "missing_fields": ["deadline", "daily_minutes"],
    }
    monkeypatch.setattr(
        "app.api.routes.generate_plan",
        lambda *args, **kwargs: {
            "status": "created", "plan_id": "plan-1", "content": "# 初稿"
        },
    )
    created = client.post(
        "/api/plans",
        json={
            "knowledge_base_id": knowledge_base_id,
            "goal": "掌握 Agent",
            "deadline": "2026-10-01",
            "daily_minutes": 30,
        },
    )
    assert created.status_code == 200
    assert created.json()["status"] == "created"
    monkeypatch.setattr(
        "app.api.routes.get_plan",
        lambda *args, **kwargs: {"id": "plan-1", "content": "# 初稿"},
    )
    assert client.get("/api/plans/plan-1").json()["content"] == "# 初稿"
    monkeypatch.setattr(
        "app.api.routes.update_plan",
        lambda *args, **kwargs: {"id": "plan-1", "content": "# 修订稿"},
    )
    assert client.patch("/api/plans/plan-1", json={"content": "# 修订稿"}).json()["content"] == "# 修订稿"


def test_progress_supports_selected_and_all_knowledge_bases(runtime, monkeypatch):
    captured = []

    def fake_progress(*args, **kwargs):
        captured.append(kwargs.get("knowledge_base_id"))
        return {"review_count": 1, "question_count": 2}

    monkeypatch.setattr("app.api.routes.get_progress", fake_progress)
    assert client.get("/api/progress?knowledge_base_id=kb-1").json()["review_count"] == 1
    assert client.get("/api/progress").json()["question_count"] == 2
    assert captured == ["kb-1", None]


def test_app_error_and_unknown_error_handlers_are_safe(runtime, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.list_knowledge_bases",
        lambda *args, **kwargs: (_ for _ in ()).throw(AppError("面向用户的错误")),
    )
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.get("/api/knowledge-bases")
    assert response.status_code == 400
    assert response.json() == {"message": "面向用户的错误"}

    monkeypatch.setattr(
        "app.api.routes.list_knowledge_bases",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("secret sk-abc123456789 C:\\private\\stack.py")
        ),
    )
    response = safe_client.get("/api/knowledge-bases")
    assert response.status_code == 500
    assert response.json() == {"message": "服务暂时不可用，请稍后重试。"}
