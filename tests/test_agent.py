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


def test_qa_strict_empty_result_does_not_create_llm(monkeypatch):
    from app.agent import nodes

    created = []

    def llm_factory():
        created.append(True)
        return type("FakeLLM", (), {"chat": lambda self, messages: "不应调用"})()

    def fake_answer_question(query, knowledge_base_id, policy, settings, llm_client, **kwargs):
        assert policy.value == "strict"
        assert not created
        return type(
            "AnswerResult",
            (),
            {
                "answer": "当前知识库中没有找到足够资料，无法只根据资料回答。",
                "citations": [],
            },
        )()

    monkeypatch.setattr(nodes, "answer_question", fake_answer_question)
    result = nodes.qa_node(
        {
            "user_input": "只根据资料回答未知问题",
            "knowledge_base_id": "kb-1",
            "request_options": {"retrieval_mode": "strict"},
            "settings": object(),
            "llm_factory": llm_factory,
            "path": [],
        }
    )

    assert result["answer"] == "当前知识库中没有找到足够资料，无法只根据资料回答。"
    assert created == []


def test_qa_strict_empty_retrieval_returns_material_insufficient_without_llm():
    from app.agent import nodes

    class EmptyVectorStore:
        def similarity_search_with_relevance_scores(self, query, k, filter=None):
            return []

    created = []

    def llm_factory():
        created.append(True)
        raise AssertionError("strict 空结果不应创建 LLM")

    result = nodes.qa_node(
        {
            "user_input": "只根据资料回答一个未收录的问题",
            "knowledge_base_id": "kb-1",
            "request_options": {"retrieval_mode": "strict"},
            "settings": type("Settings", (), {"top_k": 3, "score_threshold": 0.3})(),
            "llm_factory": llm_factory,
            "vector_store": EmptyVectorStore(),
            "path": [],
        }
    )

    assert result["answer"] == "当前知识库中没有找到足够资料，无法只根据资料回答。"
    assert result["citations"] == []
    assert created == []


def test_qa_forwards_file_ids_vector_store_and_mode_as_explicit_inputs(monkeypatch):
    from app.agent import nodes

    vector_store = object()
    captured = {}

    def fake_answer_question(query, knowledge_base_id, policy, settings, llm_client, **kwargs):
        captured.update(
            query=query,
            knowledge_base_id=knowledge_base_id,
            policy=policy,
            settings=settings,
            llm_client=llm_client,
            **kwargs,
        )
        return type("AnswerResult", (), {"answer": "ok", "citations": []})()

    monkeypatch.setattr(nodes, "answer_question", fake_answer_question)
    result = nodes.qa_node(
        {
            "user_input": "资料问题",
            "knowledge_base_id": "kb-1",
            "request_options": {
                "retrieval_mode": "general",
                "file_ids": ["file-1", "file-2"],
            },
            "settings": object(),
            "llm_client": object(),
            "vector_store": vector_store,
            "path": [],
        }
    )

    assert result["answer"] == "ok"
    assert captured["policy"].value == "general"
    assert captured["file_ids"] == ["file-1", "file-2"]
    assert captured["vector_store"] is vector_store


@pytest.mark.parametrize("tool_name", ["generate_review", "generate_plan", "get_progress"])
def test_default_future_tool_is_structured_error(tool_name):
    from app.agent.tools import run_tool

    result = run_tool(tool_name, {})

    assert result["status"] == "error"
    assert result["tool_name"] == tool_name
    assert "接入" in result["error"]


def test_tool_registry_can_be_replaced_by_tests(monkeypatch):
    from app.agent import tools

    monkeypatch.setitem(tools.TOOLS, "generate_review", lambda **kwargs: {"count": kwargs["count"]})

    assert tools.run_tool("generate_review", {"count": 5}) == {
        "status": "success",
        "tool_name": "generate_review",
        "result": {"count": 5},
    }


def test_qa_app_error_is_returned_without_breaking_node_contract(monkeypatch):
    from app.agent import nodes

    monkeypatch.setattr(
        nodes,
        "answer_question",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ConfigurationError("请先配置 DASHSCOPE_API_KEY: secret")
        ),
    )

    result = nodes.qa_node(
        {
            "user_input": "资料问题",
            "knowledge_base_id": "kb-1",
            "request_options": {},
            "settings": object(),
            "llm_client": object(),
            "path": [],
        }
    )

    assert result["answer"] == "请先在 .env 中配置 DASHSCOPE_API_KEY"
    assert result["error"] == result["answer"]
    assert result["workspace_type"] == "knowledge_base"
    assert result["workspace_id"] == "kb-1"


@pytest.mark.parametrize(
    "exception",
    [
        ConfigurationError("AppError('/tmp/secret/app.sqlite3')"),
        ConfigurationError("API_KEY: secret-value"),
        ConfigurationError("relative/cache.sqlite3 contains private data"),
        RuntimeError("failed at /tmp/secret/app.sqlite3 with API_KEY: secret-value"),
    ],
)
def test_qa_unknown_errors_use_fixed_safe_message(monkeypatch, exception):
    from app.agent import nodes

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(nodes, "answer_question", fail)
    result = nodes.qa_node(
        {
            "user_input": "资料问题",
            "knowledge_base_id": "kb-1",
            "request_options": {},
            "settings": object(),
            "llm_client": object(),
            "path": [],
        }
    )

    assert result["answer"] == "资料问答暂时不可用，请检查配置或稍后重试。"
    assert result["error"] == result["answer"]
    assert "secret" not in result["answer"]
    assert "sqlite3" not in result["answer"]


def test_lazy_llm_forwards_args_and_kwargs():
    from app.agent.nodes import _LazyLLM

    calls = []

    class FakeLLM:
        def chat(self, *args, **kwargs):
            calls.append((args, kwargs))
            return "回答"

    client = _LazyLLM(lambda: FakeLLM())

    assert client.chat([{"role": "user", "content": "问题"}], temperature=0.0) == "回答"
    assert calls == [
        (([{"role": "user", "content": "问题"}],), {"temperature": 0.0})
    ]


def test_qa_unexpected_error_is_safe_and_does_not_leak_local_path(monkeypatch):
    from app.agent import nodes

    monkeypatch.setattr(
        nodes,
        "answer_question",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("failed at C:\\secret\\app.sqlite3 with api_key=secret")
        ),
    )

    result = nodes.qa_node(
        {
            "user_input": "资料问题",
            "knowledge_base_id": "kb-1",
            "request_options": {},
            "settings": object(),
            "llm_client": object(),
            "path": [],
        }
    )

    assert "资料问答暂时不可用" in result["answer"]
    assert "secret" not in result["answer"]
    assert "app.sqlite3" not in result["answer"]
    assert result["error"] == result["answer"]


def test_build_graph_registers_all_nodes_and_routes_with_fake_state_graph(monkeypatch):
    import app.agent.graph as graph_module

    class FakeStateGraph:
        def __init__(self, state_type):
            self.state_type = state_type
            self.nodes = []
            self.edges = []
            self.conditional = None

        def add_node(self, name, function):
            self.nodes.append((name, function))

        def add_edge(self, source, target):
            self.edges.append((source, target))

        def add_conditional_edges(self, source, router, destinations):
            self.conditional = (source, router, destinations)

        def compile(self):
            return self

    monkeypatch.setattr(graph_module, "StateGraph", FakeStateGraph)
    monkeypatch.setattr(graph_module, "START", "START")
    monkeypatch.setattr(graph_module, "END", "END")

    built = graph_module.build_graph()

    assert built.state_type is graph_module.AgentState
    assert {name for name, _ in built.nodes} == {
        "classify_route_node",
        "chat_node",
        "qa_node",
        "review_node",
        "plan_node",
        "statistics_node",
        "error_node",
    }
    expected_nodes = {
        "classify_route_node": graph_module.classify_route_node,
        "chat_node": graph_module.chat_node,
        "qa_node": graph_module.qa_node,
        "review_node": graph_module.review_node,
        "plan_node": graph_module.plan_node,
        "statistics_node": graph_module.statistics_node,
        "error_node": graph_module.error_node,
    }
    assert dict(built.nodes) == expected_nodes
    assert ("START", "classify_route_node") in built.edges
    assert built.conditional[0] == "classify_route_node"
    assert built.conditional[1] is graph_module.route_after_classify
    assert built.conditional[2] == {
        "chat_node": "chat_node",
        "qa_node": "qa_node",
        "review_node": "review_node",
        "plan_node": "plan_node",
        "statistics_node": "statistics_node",
        "error_node": "error_node",
    }
    assert all(callable(function) for function in dict(built.nodes).values())
    assert all((name, "END") in built.edges for name in built.conditional[2])


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
