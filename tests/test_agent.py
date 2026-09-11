import pytest

from app.core.errors import ConfigurationError, NotFoundError
from app.storage.knowledge_base_store import create_knowledge_base


def test_plain_greeting_routes_to_chat_without_knowledge_base():
    from app.agent.nodes import classify_task

    assert classify_task("你好", knowledge_base_id=None) == "chat"


def test_explicit_knowledge_question_routes_to_qa():
    from app.agent.nodes import classify_task

    assert classify_task("根据当前资料解释什么是 Agent", knowledge_base_id="kb-1") == "qa"


def test_review_plan_and_statistics_routes_are_distinct():
    from app.agent.nodes import classify_task

    assert classify_task("根据当前资料出 5 道题", "kb-1") == "review"
    assert classify_task("帮我制定学习计划", "kb-1") == "plan"
    assert classify_task("统计我的答题情况", "kb-1") == "statistics"


def test_force_chat_override_has_highest_priority():
    from app.agent.nodes import classify_task, parse_request_options

    options = parse_request_options("不要查资料，出 5 道题")

    assert options["retrieval_mode"] == "force_chat"
    assert classify_task("不要查资料，出 5 道题", "kb-1") == "chat"


def test_strict_and_general_overrides_are_parsed():
    from app.agent.nodes import parse_request_options

    assert parse_request_options("只根据资料回答")["retrieval_mode"] == "strict"
    assert parse_request_options("允许使用通用知识")["retrieval_mode"] == "general"


@pytest.mark.parametrize("user_input", [
    "根据当前资料解释 Agent",
    "根据当前资料出题",
    "帮我安排学习计划",
    "查看我的正确率",
])
def test_knowledge_dependent_tasks_without_knowledge_base_route_to_error(user_input):
    from app.agent.nodes import classify_route_node, route_after_classify

    state = classify_route_node({"user_input": user_input, "knowledge_base_id": None, "path": []})

    assert state["task_type"] in {"qa", "review", "plan", "statistics"}
    assert route_after_classify(state) == "error_node"
    assert "选择或创建知识库" in state["error"]


def test_plain_chat_does_not_call_retriever(monkeypatch):
    from app.agent import nodes

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("普通聊天不应该调用 RAG")

    class FakeLLM:
        def chat(self, messages):
            return "你好！"

    monkeypatch.setattr(nodes, "answer_question", fail_if_called)
    result = nodes.chat_node(
        {
            "user_input": "你好",
            "session_id": "session-1",
            "knowledge_base_id": None,
            "messages": [],
            "request_options": {},
            "path": [],
            "llm_client": FakeLLM(),
        }
    )

    assert result["task_type"] == "chat"
    assert result["answer"] == "你好！"
    assert called is False


def test_chat_without_model_configuration_returns_readable_error():
    from app.agent.nodes import chat_node

    result = chat_node(
        {
            "user_input": "你好",
            "knowledge_base_id": None,
            "messages": [],
            "request_options": {},
            "path": [],
            "settings": type("Settings", (), {"api_key": ""})(),
        }
    )

    assert result["task_type"] == "chat"
    assert "DASHSCOPE_API_KEY" in result["answer"]


def test_qa_uses_answer_service_and_forwards_retrieval_mode(monkeypatch):
    from app.agent import nodes

    calls = []

    def fake_answer_question(*args, **kwargs):
        calls.append((args, kwargs))
        return type(
            "AnswerResult",
            (),
            {"answer": "资料回答", "citations": [{"source": "a.md"}]},
        )()

    monkeypatch.setattr(nodes, "answer_question", fake_answer_question)
    result = nodes.qa_node(
        {
            "user_input": "只根据资料回答 Agent 是什么",
            "knowledge_base_id": "kb-1",
            "request_options": {"retrieval_mode": "strict"},
            "messages": [],
            "path": [],
            "settings": object(),
            "llm_client": object(),
        }
    )

    assert result["answer"] == "资料回答"
    assert result["citations"] == [{"source": "a.md"}]
    assert calls[0][0][1] == "kb-1"
    assert str(calls[0][0][2]) == "AnswerPolicy.STRICT"


def test_tool_registry_can_be_replaced_by_tests():
    from app.agent.tools import register_tool, run_tool

    register_tool("generate_review", lambda **kwargs: {"count": kwargs["count"]})

    assert run_tool("generate_review", {"count": 5}) == {
        "status": "success",
        "tool_name": "generate_review",
        "result": {"count": 5},
    }


def test_missing_tool_returns_structured_error():
    from app.agent.tools import run_tool

    result = run_tool("does_not_exist", {})

    assert result["status"] == "error"
    assert "工具不存在" in result["error"]


def test_error_node_explains_missing_knowledge_base():
    from app.agent.nodes import error_node

    result = error_node(
        {
            "error": "资料问答、复习、学习计划和学习统计需要先选择或创建知识库。",
            "path": [],
        }
    )

    assert "选择或创建知识库" in result["answer"]


def test_chat_store_persists_sessions_messages_and_citations(db_path):
    from app.storage.chat_store import (
        add_message,
        create_session,
        get_session,
        list_messages,
        list_sessions,
    )

    knowledge_base = create_knowledge_base("聊天测试", db_path)
    session = create_session(knowledge_base["id"], db_path)
    message = add_message(
        session["id"],
        "assistant",
        "回答",
        "qa",
        citations=[{"source": "lesson.md", "chunk_id": "chunk-1"}],
        db_path=db_path,
    )

    assert get_session(session["id"], db_path)["knowledge_base_id"] == knowledge_base["id"]
    assert list_sessions(db_path)[0]["id"] == session["id"]
    assert list_messages(session["id"], db_path) == [message]
    assert message["citations"] == [{"source": "lesson.md", "chunk_id": "chunk-1"}]


def test_chat_store_allows_session_without_knowledge_base(db_path):
    from app.storage.chat_store import create_session

    session = create_session(None, db_path)

    assert session["knowledge_base_id"] is None


def test_chat_store_validates_missing_resources(db_path):
    from app.storage.chat_store import add_message, get_session, list_messages

    with pytest.raises(NotFoundError):
        get_session("missing", db_path)
    with pytest.raises(NotFoundError):
        list_messages("missing", db_path)
    with pytest.raises(NotFoundError):
        add_message("missing", "user", "hello", "chat", db_path=db_path)


def test_run_agent_loads_history_and_returns_plain_result(monkeypatch, db_path):
    from app.agent import graph
    from app.storage.chat_store import add_message, create_session

    session = create_session(None, db_path)
    add_message(session["id"], "user", "之前的问题", "chat", db_path=db_path)
    captured = {}

    class FakeGraph:
        def invoke(self, state):
            captured.update(state)
            return {
                "task_type": "chat",
                "answer": "新的回答",
                "citations": [],
                "workspace_type": "chat",
                "workspace_id": session["id"],
                "statistics": {},
                "path": ["classify_route_node", "chat_node"],
                "internal_only": "not returned",
            }

    result = graph.run_agent(
        "新的问题",
        session["id"],
        db_path=db_path,
        compiled_graph=FakeGraph(),
    )

    assert captured["messages"][0]["content"] == "之前的问题"
    assert result == {
        "task_type": "chat",
        "answer": "新的回答",
        "citations": [],
        "workspace_type": "chat",
        "workspace_id": session["id"],
        "statistics": {},
        "path": ["classify_route_node", "chat_node"],
    }


def test_build_graph_reports_missing_langgraph_without_import_time_failure(monkeypatch):
    import app.agent.graph as graph_module

    monkeypatch.setattr(graph_module, "StateGraph", None)

    with pytest.raises(ConfigurationError, match="langgraph"):
        graph_module.build_graph()
