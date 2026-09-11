from types import SimpleNamespace

import pytest

from app.storage.knowledge_base_store import create_knowledge_base
from app.storage.review_store import (
    create_review_session,
    mark_review_submitted,
    save_review_draft,
)


def seed_submitted_and_draft_reviews(db_path):
    knowledge_base = create_knowledge_base("进度测试", db_path)
    questions = [
        {
            "question_type": "choice",
            "prompt": "问题一",
            "options": [
                {"label": "A", "text": "正确"},
                {"label": "B", "text": "错误"},
                {"label": "C", "text": "干扰"},
                {"label": "D", "text": "干扰"},
            ],
            "correct_answer": "A",
            "reference_answer": "A",
            "rubric": "选择正确选项",
            "knowledge_point": "概念一",
            "source_chunk_ids": [],
        },
        {
            "question_type": "judgment",
            "prompt": "问题二",
            "options": [],
            "correct_answer": "正确",
            "reference_answer": "正确",
            "rubric": "判断正误",
            "knowledge_point": "概念二",
            "source_chunk_ids": [],
        },
    ]
    submitted = create_review_session(
        knowledge_base["id"], {"file_ids": []}, questions, db_path=db_path
    )
    save_review_draft(
        submitted["id"],
        [
            {"question_id": submitted["questions"][0]["id"], "answer_text": "A"},
            {"question_id": submitted["questions"][1]["id"], "answer_text": "错误"},
        ],
        db_path=db_path,
    )
    mark_review_submitted(submitted["id"], 50.0, db_path=db_path)
    create_review_session(
        knowledge_base["id"], {"file_ids": []}, [questions[0]], db_path=db_path
    )
    return knowledge_base["id"]


def test_only_explicit_preference_is_saved(db_path):
    from app.memory.store import get_preferences, parse_preference_request, save_preference

    assert parse_preference_request("你好") is None
    parsed = parse_preference_request("记住我喜欢简洁回答")

    assert parsed == {"key": "answer_style", "value": "简洁回答"}
    saved = save_preference(parsed["key"], parsed["value"], db_path=db_path)

    assert saved["key"] == "answer_style"
    assert get_preferences(db_path=db_path) == {"answer_style": "简洁回答"}


def test_sensitive_preference_is_rejected(db_path):
    from app.core.errors import ValidationError
    from app.memory.store import save_preference

    with pytest.raises(ValidationError):
        save_preference("answer_style", "我的 api_key 是 secret-value", db_path=db_path)


def test_preference_update_uses_same_key(db_path):
    from app.memory.store import get_preferences, save_preference

    save_preference("answer_style", "简洁", db_path=db_path)
    save_preference("answer_style", "分点", db_path=db_path)

    assert get_preferences(db_path=db_path) == {"answer_style": "分点"}


def test_plan_requires_goal_deadline_and_daily_minutes():
    from app.plan.service import missing_plan_fields

    assert missing_plan_fields(
        {"goal": "掌握 Agent", "deadline": "", "daily_minutes": None}
    ) == ["deadline", "daily_minutes"]


def test_plan_does_not_call_model_when_fields_are_missing():
    from app.plan.service import generate_plan

    class FailingLLM:
        def chat(self, messages):
            raise AssertionError("缺少计划字段时不应调用模型")

    result = generate_plan(
        "kb-1",
        None,
        {"goal": "掌握 Agent", "deadline": "", "daily_minutes": None},
        SimpleNamespace(top_k=3, score_threshold=0.0),
        FailingLLM(),
    )

    assert result == {"status": "needs_input", "missing_fields": ["deadline", "daily_minutes"]}


def test_complete_plan_is_generated_from_context_and_persisted(monkeypatch, db_path):
    from app.memory.store import save_preference
    from app.plan.service import generate_plan
    from app.storage.plan_store import get_plan

    save_preference("answer_style", "分点回答", db_path=db_path)
    knowledge_base = create_knowledge_base("计划测试", db_path)
    captured = {}

    monkeypatch.setattr(
        "app.plan.service.retrieve",
        lambda *args, **kwargs: [{"source": "lesson.md", "chunk_id": "chunk-1", "text": "Agent 资料"}],
    )

    class FakeLLM:
        def chat(self, messages):
            captured["messages"] = messages
            return "# Agent 学习计划\n\n- 第 1 天：理解基础"

    result = generate_plan(
        knowledge_base["id"],
        ["file-1"],
        {"goal": "掌握 Agent", "deadline": "2026-10-01", "daily_minutes": 30},
        SimpleNamespace(top_k=3, score_threshold=0.0),
        FakeLLM(),
        db_path=db_path,
        vector_store=object(),
    )

    assert result["status"] == "created"
    assert result["content"].startswith("# Agent")
    assert get_plan(result["plan_id"], db_path=db_path)["content"] == result["content"]
    prompt = "\n".join(item["content"] for item in captured["messages"])
    assert "分点回答" in prompt
    assert "Agent 资料" in prompt


def test_plan_can_be_edited_and_persisted(db_path):
    from app.storage.plan_store import create_plan, get_plan, update_plan

    knowledge_base = create_knowledge_base("编辑计划", db_path)
    plan = create_plan(knowledge_base["id"], "计划", "# 初稿", {"file_ids": []}, db_path)
    updated = update_plan(plan["id"], "# 修订稿", db_path)

    assert updated["content"] == "# 修订稿"
    assert get_plan(plan["id"], db_path)["content"] == "# 修订稿"


def test_progress_counts_only_submitted_reviews(db_path):
    from app.progress.service import get_progress

    knowledge_base_id = seed_submitted_and_draft_reviews(db_path)
    progress = get_progress(knowledge_base_id=knowledge_base_id, db_path=db_path)

    assert progress["review_count"] == 1
    assert progress["question_count"] == 2
    assert progress["correct_count"] == 1
    assert progress["accuracy"] == 50.0
    assert progress["average_score"] == 50.0
    assert progress["wrong_count"] == 1
    assert progress["draft_review_count"] == 0
    assert progress["weak_points"] == ["概念二"]
    assert progress["by_question_type"]["choice"] == {
        "question_count": 1,
        "accuracy": 100.0,
        "average_score": 100.0,
    }
    assert "plan_completion_rate" not in progress


def test_progress_can_aggregate_all_knowledge_bases(db_path):
    from app.progress.service import get_progress

    seed_submitted_and_draft_reviews(db_path)
    assert get_progress(db_path=db_path)["review_count"] == 1


def test_agent_preference_confirmation_does_not_call_chat(monkeypatch, db_path):
    from app.agent import nodes

    monkeypatch.setattr(nodes, "save_preference", lambda *args, **kwargs: {"key": args[0], "value": args[1]})
    monkeypatch.setattr(nodes, "_llm", lambda state: (_ for _ in ()).throw(AssertionError("不应调用聊天模型")))

    result = nodes.chat_node(
        {
            "user_input": "记住我希望回答分点",
            "session_id": "session-1",
            "request_options": {},
            "messages": [],
            "path": [],
            "db_path": db_path,
        }
    )

    assert "已记住" in result["answer"]
    assert result["workspace_type"] == "chat"


def test_preference_like_chat_without_remember_is_ordinary_chat(monkeypatch):
    from app.agent import nodes

    called = []
    monkeypatch.setattr(nodes, "save_preference", lambda *args, **kwargs: called.append(True))

    class FakeLLM:
        def chat(self, messages):
            return "普通回答"

    result = nodes.chat_node(
        {
            "user_input": "我喜欢简洁回答",
            "session_id": "session-1",
            "request_options": {},
            "messages": [],
            "path": [],
            "llm_client": FakeLLM(),
        }
    )

    assert result["answer"] == "普通回答"
    assert called == []


def test_plan_and_statistics_nodes_expose_their_workspaces(monkeypatch):
    from app.agent import nodes
    from app.agent import tools

    monkeypatch.setitem(tools.TOOLS, "generate_plan", lambda **kwargs: {"status": "created", "plan_id": "plan-1", "content": "# 计划"})
    monkeypatch.setitem(tools.TOOLS, "get_progress", lambda **kwargs: {"review_count": 2})

    base = {"knowledge_base_id": "kb-1", "request_options": {}, "user_input": "", "path": []}
    plan = nodes.plan_node({**base, "request_options": {"plan": {"goal": "g", "deadline": "d", "daily_minutes": 20}}})
    stats = nodes.statistics_node(base)

    assert plan["workspace_type"] == "plan"
    assert plan["workspace_id"] == "plan-1"
    assert stats["workspace_type"] == "statistics"
    assert stats["statistics"] == {"review_count": 2}
