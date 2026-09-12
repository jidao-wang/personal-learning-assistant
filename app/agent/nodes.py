import re
from typing import Any

from app.agent.state import AgentState
from app.agent.tools import run_tool
from app.core.config import load_settings
from app.core.errors import AppError, ConfigurationError
from app.core.llm_client import LLMClient
from app.knowledge.answer import AnswerPolicy, answer_question
from app.memory.store import parse_preference_request, save_preference


FORCE_CHAT_MARKERS = ("不要查资料", "只聊天", "不用知识库")
REVIEW_MARKERS = ("出题", "复习", "测试", "题目")
PLAN_MARKERS = ("学习计划", "安排", "规划")
STATISTICS_MARKERS = ("统计", "进度", "正确率", "错题", "薄弱")
QA_MARKERS = ("只根据资料", "允许使用通用知识", "根据资料", "知识库", "资料")
QUESTION_MARKERS = ("什么是", "如何", "解释", "区别", "为什么", "怎么")
REVIEW_TYPE_MARKERS = ("选择题", "判断题", "简答题")


def parse_request_options(user_input: str) -> dict[str, Any]:
    text = user_input or ""
    if any(marker in text for marker in FORCE_CHAT_MARKERS):
        mode = "force_chat"
    elif "只根据资料" in text:
        mode = "strict"
    elif "允许使用通用知识" in text:
        mode = "general"
    else:
        mode = "default"
    return {"retrieval_mode": mode}


def classify_task(user_input: str, knowledge_base_id: str | None) -> str:
    text = user_input or ""
    if any(marker in text for marker in FORCE_CHAT_MARKERS):
        return "chat"
    if (
        any(marker in text for marker in REVIEW_MARKERS)
        or any(marker in text for marker in REVIEW_TYPE_MARKERS)
        or re.search(r"出\s*\d*\s*道?\s*题", text)
    ):
        return "review"
    if any(marker in text for marker in PLAN_MARKERS):
        return "plan"
    if any(marker in text for marker in STATISTICS_MARKERS):
        return "statistics"
    if any(marker in text for marker in QA_MARKERS):
        return "qa"
    if knowledge_base_id and any(marker in text for marker in QUESTION_MARKERS):
        return "qa"
    return "chat"


def _append_path(state: AgentState, node_name: str) -> list[str]:
    return [*state.get("path", []), node_name]


def classify_route_node(state: AgentState) -> dict[str, Any]:
    parsed = parse_request_options(state.get("user_input", ""))
    options = {**parsed, **state.get("request_options", {})}
    task_type = classify_task(state.get("user_input", ""), state.get("knowledge_base_id"))
    result: dict[str, Any] = {
        "request_options": options,
        "retrieval_mode": options.get("retrieval_mode", "default"),
        "task_type": task_type,
        "path": _append_path(state, "classify_route_node"),
    }
    if task_type in {"qa", "review", "plan", "statistics"} and not state.get("knowledge_base_id"):
        result["error"] = "资料问答、复习、学习计划和学习统计需要先选择或创建知识库。"
    return result


def route_after_classify(state: AgentState) -> str:
    task_type = state.get("task_type", "chat")
    if task_type in {"qa", "review", "plan", "statistics"} and not state.get("knowledge_base_id"):
        return "error_node"
    return f"{task_type}_node"


class _LazyLLM:
    def __init__(self, factory):
        self._factory = factory
        self._client = None

    def chat(self, *args, **kwargs):
        if self._client is None:
            self._client = self._factory()
        return self._client.chat(*args, **kwargs)


def _llm(state: AgentState):
    client = state.get("llm_client")
    if client is not None:
        return _LazyLLM(lambda: client)
    if state.get("llm_factory") is not None:
        return _LazyLLM(state["llm_factory"])

    def create_client():
        settings = state.get("settings") or load_settings()
        if hasattr(settings, "api_key") and not settings.api_key.strip():
            raise ConfigurationError("请先在 .env 中配置 DASHSCOPE_API_KEY")
        return LLMClient(settings)

    return _LazyLLM(create_client)


def _settings(state: AgentState):
    return state.get("settings") or load_settings()


def _base_result(state: AgentState, node_name: str, task_type: str) -> dict[str, Any]:
    return {
        "task_type": task_type,
        "citations": [],
        "statistics": {},
        "path": _append_path(state, node_name),
    }


def chat_node(state: AgentState) -> dict[str, Any]:
    result = _base_result(state, "chat_node", "chat")
    parsed_preference = parse_preference_request(state.get("user_input", ""))
    if parsed_preference is not None:
        try:
            save_preference(
                parsed_preference["key"],
                parsed_preference["value"],
                db_path=state.get("db_path"),
            )
            result["answer"] = f"已记住你的偏好：{parsed_preference['value']}。"
        except AppError as exc:
            result["answer"] = str(exc)
            result["error"] = str(exc)
        result.update({"workspace_type": "chat", "workspace_id": state.get("session_id", "")})
        return result
    messages = [{"role": item["role"], "content": item["content"]} for item in state.get("messages", [])]
    messages.append({"role": "user", "content": state.get("user_input", "")})
    try:
        result["answer"] = _llm(state).chat(messages)
    except AppError as exc:
        result["answer"] = str(exc)
    except Exception as exc:
        result["answer"] = f"聊天服务暂时不可用：{exc}"
    result.update({"workspace_type": "chat", "workspace_id": state.get("session_id", "")})
    return result


def qa_node(state: AgentState) -> dict[str, Any]:
    result = _base_result(state, "qa_node", "qa")
    try:
        options = state.get("request_options", {})
        policy = AnswerPolicy(
            options.get("retrieval_mode", state.get("retrieval_mode", "default"))
        )
        answer = answer_question(
            state.get("user_input", ""),
            state.get("knowledge_base_id"),
            policy,
            _settings(state),
            _llm(state),
            file_ids=options.get("file_ids"),
            vector_store=state.get("vector_store"),
        )
    except AppError as exc:
        message = _safe_qa_error(exc)
        result.update({"answer": message, "error": message})
        result.update(
            {
                "workspace_type": "knowledge_base",
                "workspace_id": state.get("knowledge_base_id", ""),
            }
        )
        return result
    except Exception as exc:
        message = _safe_qa_error(exc)
        result.update({"answer": message, "error": message})
        result.update(
            {
                "workspace_type": "knowledge_base",
                "workspace_id": state.get("knowledge_base_id", ""),
            }
        )
        return result
    result.update(
        {
            "answer": answer.answer,
            "citations": answer.citations,
            "workspace_type": "knowledge_base",
            "workspace_id": state.get("knowledge_base_id", ""),
        }
    )
    return result


def _safe_qa_error(exc: Exception) -> str:
    if isinstance(exc, ConfigurationError):
        message = str(exc)
        if "DASHSCOPE_API_KEY" in message and "配置" in message:
            return "请先在 .env 中配置 DASHSCOPE_API_KEY"
        if message == "未安装 openai，无法调用模型":
            return message
    return "资料问答暂时不可用，请检查配置或稍后重试。"


def _tool_node(
    state: AgentState,
    node_name: str,
    task_type: str,
    tool_name: str,
    workspace_type: str | None = None,
) -> dict[str, Any]:
    result = _base_result(state, node_name, task_type)
    tool_args = {
        "knowledge_base_id": state.get("knowledge_base_id"),
        "session_id": state.get("session_id"),
        "user_input": state.get("user_input", ""),
        "request_options": state.get("request_options", {}),
    }
    for key in ("settings", "llm_client", "db_path", "vector_store"):
        if state.get(key) is not None:
            tool_args[key] = state[key]
    tool_result = run_tool(tool_name, tool_args)
    if tool_result["status"] == "success":
        value = tool_result["result"]
        result["_tool_result"] = value
        if isinstance(value, dict):
            result.update(value)
            result.setdefault("answer", value.get("message", ""))
        else:
            result["answer"] = str(value)
    else:
        result["answer"] = f"{tool_result['error']}"
        result["error"] = tool_result["error"]
    result.setdefault("answer", "")
    result.update({
        "task_type": task_type,
        "workspace_type": workspace_type or "knowledge_base",
        "workspace_id": state.get("knowledge_base_id", ""),
    })
    if isinstance(tool_result.get("result"), dict) and tool_result["result"].get("status") == "created":
        result["workspace_id"] = tool_result["result"].get("plan_id", result["workspace_id"])
    return result


def review_node(state: AgentState) -> dict[str, Any]:
    result = _tool_node(
        state,
        "review_node",
        "review",
        "generate_review",
        workspace_type="review",
    )
    value = result.get("_tool_result")
    if isinstance(value, dict) and value.get("review_session_id"):
        result["workspace_id"] = value["review_session_id"]
    return result


def plan_node(state: AgentState) -> dict[str, Any]:
    result = _tool_node(state, "plan_node", "plan", "generate_plan", workspace_type="plan")
    value = result.get("_tool_result")
    if isinstance(value, dict) and value.get("status") == "needs_input":
        result["answer"] = "请补充：" + "、".join(value.get("missing_fields", []))
    return result


def statistics_node(state: AgentState) -> dict[str, Any]:
    result = _tool_node(state, "statistics_node", "statistics", "get_progress", workspace_type="statistics")
    if isinstance(result.get("_tool_result"), dict):
        result["statistics"] = result["_tool_result"]
    return result


def error_node(state: AgentState) -> dict[str, Any]:
    result = _base_result(state, "error_node", state.get("task_type", "chat"))
    result.update(
        {
            "answer": state.get("error", "当前请求无法处理。"),
            "error": state.get("error", "当前请求无法处理。"),
            "workspace_type": "knowledge_base",
            "workspace_id": state.get("knowledge_base_id") or "",
        }
    )
    return result
