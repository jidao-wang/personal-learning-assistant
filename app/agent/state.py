from typing import Any, Literal, TypedDict


TaskType = Literal["chat", "qa", "review", "plan", "statistics"]
RetrievalMode = Literal["default", "force_chat", "strict", "general"]


class AgentState(TypedDict, total=False):
    user_input: str
    session_id: str
    knowledge_base_id: str | None
    request_options: dict[str, Any]
    retrieval_mode: RetrievalMode
    task_type: TaskType
    messages: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    workspace_type: str
    workspace_id: str
    statistics: dict[str, Any]
    error: str
    path: list[str]
    settings: Any
    llm_client: Any
    vector_store: Any
