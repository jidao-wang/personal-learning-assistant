import pytest

from app.core.errors import ConfigurationError
from app.knowledge.answer import AnswerPolicy, answer_question, build_answer_result
from app.knowledge.retriever import format_citations, format_context


def test_format_context_contains_only_actual_sources():
    results = [
        {
            "text": "Agent 是可以调用工具的程序。",
            "source": "lesson.md",
            "chunk_id": "chunk-0",
            "score": 0.91,
            "file_id": "file-1",
        }
    ]

    context = format_context(results)
    citations = format_citations(results)

    assert "lesson.md#chunk-0" in context
    assert citations == [
        {
            "source": "lesson.md",
            "chunk_id": "chunk-0",
            "file_id": "file-1",
            "score": 0.91,
        }
    ]


def test_strict_policy_rejects_empty_retrieval():
    result = build_answer_result(
        answer="",
        results=[],
        policy=AnswerPolicy.STRICT,
    )

    assert result.answer == "当前知识库中没有找到足够资料，无法只根据资料回答。"
    assert result.citations == []
    assert result.source_type == "knowledge_base"
    assert result.used_general_knowledge is False


def test_default_policy_marks_general_knowledge_explicitly():
    result = build_answer_result(
        answer="这是模型的通用解释。",
        results=[],
        policy=AnswerPolicy.DEFAULT,
    )

    assert "当前知识库没有命中" in result.answer
    assert result.source_type == "general_knowledge"
    assert result.used_general_knowledge is True


class FakeVectorStore:
    def __init__(self, results=None):
        self.results = [
            (
                type(
                    "Document",
                    (),
                    {
                        "page_content": "资料答案",
                        "metadata": {
                            "source": "lesson.md",
                            "title": "标题",
                            "chunk_id": "chunk-0",
                            "file_id": "file-1",
                            "knowledge_base_id": "kb-1",
                        },
                    },
                )(),
                0.88,
            )
        ] if results is None else results
        self.calls = []

    def similarity_search_with_relevance_scores(self, query, k, filter=None):
        self.calls.append((query, k, filter))
        return self.results


def test_retrieve_filters_by_selected_files():
    from app.knowledge.retriever import retrieve

    store = FakeVectorStore()
    results = retrieve(
        "kb-1",
        "问题",
        file_ids=["file-1"],
        settings=type("Settings", (), {"top_k": 3, "score_threshold": 0.3})(),
        vector_store=store,
    )

    assert results[0]["source"] == "lesson.md"
    assert store.calls == [("问题", 3, {"file_id": {"$in": ["file-1"]}})]


def test_retrieve_uses_falsey_injected_store(monkeypatch):
    from app.knowledge.retriever import retrieve

    class FalseyStore(FakeVectorStore):
        def __bool__(self):
            return False

    store = FalseyStore()
    monkeypatch.setattr(
        "app.knowledge.retriever.get_vector_store",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected store lookup")),
    )
    settings = type("Settings", (), {"top_k": 3, "score_threshold": 0.3})()

    results = retrieve("kb-1", "问题", settings=settings, vector_store=store)

    assert results[0]["text"] == "资料答案"


def test_retrieve_drops_scores_below_threshold_and_uses_isolated_store(monkeypatch):
    import app.knowledge.retriever as retriever_module

    store = FakeVectorStore(
        [
            (type("Document", (), {"page_content": "keep", "metadata": {"source": "a", "title": "A", "chunk_id": "c1", "file_id": "f1", "knowledge_base_id": "kb-1"}})(), 0.5),
            (type("Document", (), {"page_content": "drop", "metadata": {"source": "b", "title": "B", "chunk_id": "c2", "file_id": "f2", "knowledge_base_id": "kb-1"}})(), 0.2),
        ]
    )
    requested = []

    def fake_get_vector_store(knowledge_base_id, settings, embedding_function=None):
        requested.append(knowledge_base_id)
        return store

    monkeypatch.setattr(retriever_module, "get_vector_store", fake_get_vector_store)
    settings = type("Settings", (), {"top_k": 4, "score_threshold": 0.3})()

    results = retriever_module.retrieve(
        "kb-1", "问题", settings=settings, top_k=2, score_threshold=0.3
    )

    assert requested == ["kb-1"]
    assert [item["text"] for item in results] == ["keep"]
    assert set(results[0]) == {
        "text", "source", "title", "chunk_id", "file_id", "knowledge_base_id", "score"
    }
    assert store.calls == [("问题", 2, None)]


def test_retrieve_preserves_explicit_zero_options():
    from app.knowledge.retriever import retrieve

    store = FakeVectorStore(
        [
            (type("Document", (), {"page_content": "低分也保留", "metadata": {"source": "a", "title": "A", "chunk_id": "c1", "file_id": "f1", "knowledge_base_id": "kb-1"}})(), 0.1),
        ]
    )
    settings = type("Settings", (), {"top_k": 5, "score_threshold": 0.8})()

    results = retrieve(
        "kb-1", "问题", top_k=0, score_threshold=0, settings=settings, vector_store=store
    )

    assert results[0]["text"] == "低分也保留"
    assert store.calls == [("问题", 0, None)]


class FakeLLM:
    def __init__(self, answer="模型回答"):
        self.answer = answer
        self.messages = []

    def chat(self, messages):
        self.messages.append(messages)
        return self.answer


def test_strict_empty_answer_does_not_call_model():
    llm = FakeLLM()
    store = FakeVectorStore([])
    settings = type("Settings", (), {"top_k": 3, "score_threshold": 0.3})()

    result = answer_question(
        "问题", "kb-1", AnswerPolicy.STRICT, settings, llm, vector_store=store
    )

    assert result.answer == "当前知识库中没有找到足够资料，无法只根据资料回答。"
    assert llm.messages == []


def test_general_empty_answer_is_marked_and_has_no_citations():
    llm = FakeLLM("通用回答")
    store = FakeVectorStore([])
    settings = type("Settings", (), {"top_k": 3, "score_threshold": 0.3})()

    result = answer_question(
        "问题", "kb-1", AnswerPolicy.GENERAL, settings, llm, vector_store=store
    )

    assert result.answer.startswith("当前知识库没有命中相关内容。以下是模型通用知识回答：")
    assert result.citations == []
    assert result.used_general_knowledge is True
    assert "资料上下文" not in llm.messages[0][-1]["content"]


def test_grounded_answer_uses_retrieved_context_for_answer_and_citations():
    llm = FakeLLM("基于资料的回答")
    store = FakeVectorStore()
    settings = type("Settings", (), {"top_k": 3, "score_threshold": 0.3})()

    result = answer_question(
        "问题", "kb-1", AnswerPolicy.DEFAULT, settings, llm, vector_store=store
    )

    prompt = "\n".join(message["content"] for message in llm.messages[0])
    assert "资料答案" in prompt
    assert "只依据提供的资料" in prompt
    assert result.answer == "基于资料的回答"
    assert result.citations == [
        {"source": "lesson.md", "chunk_id": "chunk-0", "file_id": "file-1", "score": 0.88}
    ]
    assert result.used_general_knowledge is False


def test_llm_client_can_initialize_without_key_but_fails_before_call():
    from app.core.llm_client import LLMClient

    settings = type(
        "Settings",
        (),
        {
            "api_key": "",
            "base_url": "https://example.test/v1",
            "chat_model": "chat",
            "timeout_seconds": 1,
            "temperature": 0.2,
        },
    )()
    client = LLMClient(settings)

    with pytest.raises(ConfigurationError, match="DASHSCOPE_API_KEY"):
        client.chat([])


def test_llm_client_reports_missing_openai_only_when_calling():
    from app.core.llm_client import LLMClient

    settings = type(
        "Settings",
        (),
        {
            "api_key": "test-key",
            "base_url": "https://example.test/v1",
            "chat_model": "chat",
            "timeout_seconds": 1,
            "temperature": 0.2,
        },
    )()
    client = LLMClient(settings)
    assert client.client is None

    with pytest.raises(ConfigurationError, match="openai"):
        client.chat([])


def test_llm_client_supports_injected_openai_compatible_client():
    from app.core.llm_client import LLMClient

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return type(
                "Response",
                (),
                {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "回答"})()})()]},
            )()

    completions = FakeCompletions()
    fake_openai_client = type(
        "OpenAIClient", (), {"chat": type("Chat", (), {"completions": completions})()}
    )()
    settings = type(
        "Settings",
        (),
        {
            "api_key": "test-key",
            "base_url": "https://example.test/v1",
            "chat_model": "chat",
            "timeout_seconds": 1,
            "temperature": 0.2,
        },
    )()
    client = LLMClient(settings)
    client.client = fake_openai_client

    assert client.chat([{"role": "user", "content": "问题"}]) == "回答"
    assert completions.calls == [
        {
            "model": "chat",
            "messages": [{"role": "user", "content": "问题"}],
            "temperature": 0.2,
        }
    ]
