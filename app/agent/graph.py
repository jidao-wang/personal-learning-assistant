from typing import Any

from app.agent.nodes import (
    chat_node,
    classify_route_node,
    error_node,
    plan_node,
    qa_node,
    review_node,
    route_after_classify,
    statistics_node,
)
from app.agent.state import AgentState
from app.core.config import load_settings
from app.core.errors import ConfigurationError
from app.storage import chat_store

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    END = START = StateGraph = None


def build_graph() -> Any:
    if StateGraph is None:
        raise ConfigurationError("未安装 langgraph，无法构建 Agent 图")
    graph = StateGraph(AgentState)
    graph.add_node("classify_route_node", classify_route_node)
    graph.add_node("chat_node", chat_node)
    graph.add_node("qa_node", qa_node)
    graph.add_node("review_node", review_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("statistics_node", statistics_node)
    graph.add_node("error_node", error_node)
    graph.add_edge(START, "classify_route_node")
    graph.add_conditional_edges(
        "classify_route_node",
        route_after_classify,
        {
            "chat_node": "chat_node",
            "qa_node": "qa_node",
            "review_node": "review_node",
            "plan_node": "plan_node",
            "statistics_node": "statistics_node",
            "error_node": "error_node",
        },
    )
    for node_name in (
        "chat_node",
        "qa_node",
        "review_node",
        "plan_node",
        "statistics_node",
        "error_node",
    ):
        graph.add_edge(node_name, END)
    return graph.compile()


def run_agent(
    user_input: str,
    session_id: str,
    knowledge_base_id: str | None = None,
    request_options: dict[str, Any] | None = None,
    db_path=None,
    settings=None,
    llm_client=None,
    vector_store=None,
    compiled_graph=None,
) -> dict[str, Any]:
    state: AgentState = {
        "user_input": user_input,
        "session_id": session_id,
        "knowledge_base_id": knowledge_base_id,
        "request_options": request_options or {},
        "messages": chat_store.list_messages(session_id, db_path),
        "path": [],
    }
    if settings is not None:
        state["settings"] = settings
    if llm_client is not None:
        state["llm_client"] = llm_client
    if vector_store is not None:
        state["vector_store"] = vector_store
    result = (compiled_graph or build_graph()).invoke(state)
    return {
        "task_type": result.get("task_type", "chat"),
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "workspace_type": result.get("workspace_type", ""),
        "workspace_id": result.get("workspace_id", ""),
        "statistics": result.get("statistics", {}),
        "path": result.get("path", []),
    }
