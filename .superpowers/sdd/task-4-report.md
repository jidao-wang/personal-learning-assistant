# Task 4 Report

## Implemented Files

- `app/agent/state.py`: typed `AgentState`, task types, and retrieval modes.
- `app/agent/nodes.py`: deterministic request-option parsing, route classification, chat/QA nodes, tool-backed review/plan/statistics nodes, and the missing-knowledge-base error node.
- `app/agent/tools.py`: explicit replaceable tool registry, metadata, structured tool results, and safe unavailable defaults for Task 5/6 tools.
- `app/agent/graph.py`: one LangGraph `StateGraph`, delayed LangGraph dependency handling, and `run_agent` history loading plus plain-dict output.
- `app/agent/__init__.py`: public graph entry points.
- `app/storage/chat_store.py`: SQLite session/message persistence using `sqlite3.Row`, ISO-second timestamps, JSON citations, and resource validation.
- `tests/test_agent.py`: route, override, node, registry, persistence, and graph-injection behavior tests.

## Routing

`classify_task` applies the required priority:

1. `force_chat`: `不要查资料`, `只聊天`, `不用知识库`.
2. Review: `出题`, `复习`, `测试`, `题目`, including spaced requests such as `出 5 道题`.
3. Plan: `学习计划`, `安排`, `规划`.
4. Statistics: `统计`, `进度`, `正确率`, `错题`, `薄弱`.
5. Explicit retrieval/knowledge terms: strict, general, or knowledge-base QA.
6. Question-like wording with a selected knowledge base: `什么是`, `如何`, `解释`, `区别`, `为什么`, `怎么`.
7. Otherwise regular chat.

When QA, review, plan, or statistics is selected without a knowledge base, classification remains explicit and `route_after_classify` selects `error_node`; the request is never silently changed to chat. The error asks the user to select or create a knowledge base.

Regular `chat_node` only calls the injected/default LLM client. It never calls `answer_question`. `qa_node` calls Task 3 `answer_question` with the parsed retrieval policy and forwards `file_ids`, vector-store injection, and all request options. Review/plan/progress behavior crosses only the registry boundary, with `request_options` passed through unchanged.

## Dependency Boundaries

- `langgraph` is imported inside a guarded module-level block. If absent, importing `app.agent` still works and `build_graph()` raises `ConfigurationError("未安装 langgraph，无法构建 Agent 图")`.
- `openai` remains lazily imported by the existing `LLMClient`; missing API key or package errors are returned by `chat_node` as readable answers rather than import-time failures.
- Tests inject fake LLMs, fake compiled graphs, and replace registry functions. No network calls or dependency installation are required.
- Task 5/6 modules are not imported or implemented. Their registry entries are safe placeholder functions and can be replaced with `register_tool`.
- `run_agent` loads persisted history through `chat_store.list_messages`, invokes the supplied or compiled graph, and returns only the required plain fields. It does not save user or assistant messages; that remains the future API layer's responsibility.

## Tests

RED phase:

- `pytest tests/test_agent.py -q`: 19 failures with the expected missing-module errors before production modules existed.

Final verification:

- `pytest tests/test_agent.py -q`: `20 passed in 0.29s`.
- `pytest tests/test_database.py tests/test_ingest.py tests/test_retrieval.py tests/test_agent.py -q`: `69 passed in 2.31s`.
- `python -m compileall -q app tests`: exit code `0`.
- Environment probe: `langgraph=False`, `openai=False`.

## Concerns

- Full real LangGraph execution could not be exercised because `langgraph` is not installed in the current environment. Construction failure is deliberate and readable; injected fake-graph execution is covered.
- Real model chat and retrieval require the existing runtime dependencies and configuration, so tests remain deterministic and offline.
- The default review/plan/statistics tools intentionally report unavailable until their future modules register concrete implementations.
