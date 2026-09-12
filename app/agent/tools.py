from typing import Any, Callable

from app.core.errors import AppError
from app.core.config import load_settings
from app.core.llm_client import LLMClient
from app.memory.store import parse_preference_request as _parse_preference_request
from app.memory.store import save_preference as _save_preference
from app.plan.service import generate_plan as _generate_plan
from app.plan.service import missing_plan_fields
from app.progress.service import get_progress as _get_progress
from app.review.service import generate_review as _generate_review


TOOLS: dict[str, Callable[..., Any]] = {}
TOOL_METADATA = {
    "search_knowledge_base": {"requires_confirmation": False},
    "generate_review": {"requires_confirmation": False},
    "generate_plan": {"requires_confirmation": False},
    "get_progress": {"requires_confirmation": False},
    "save_preference": {"requires_confirmation": False},
}


def _unavailable(tool_label: str, **kwargs: Any) -> dict[str, Any]:
    raise AppError(f"{tool_label}工具尚未接入，当前无法执行。")


def register_tool(name: str, function: Callable[..., Any]) -> None:
    TOOLS[name] = function


def _runtime(kwargs: dict[str, Any]):
    options = kwargs.get("request_options") or {}
    settings = kwargs.get("settings") or options.get("_settings") or load_settings()
    llm_client = kwargs.get("llm_client") or options.get("_llm_client")
    if llm_client is None:
        llm_client = LLMClient(settings)
    db_path = kwargs.get("db_path") or options.get("_db_path")
    vector_store = kwargs.get("vector_store") or options.get("_vector_store")
    return settings, llm_client, db_path, vector_store


def save_preference(**kwargs):
    if not kwargs:
        return _unavailable("偏好保存")
    key = kwargs.get("key")
    value = kwargs.get("value")
    if key is None or value is None:
        parsed = _parse_preference_request(kwargs.get("user_input", ""))
        if parsed is None:
            return _unavailable("偏好保存")
        key, value = parsed["key"], parsed["value"]
    options = kwargs.get("request_options") or {}
    return _save_preference(
        key,
        value,
        db_path=kwargs.get("db_path") or options.get("_db_path"),
    )


def get_progress(**kwargs):
    if not kwargs:
        return _unavailable("学习统计")
    options = kwargs.get("request_options") or {}
    return _get_progress(
        knowledge_base_id=kwargs.get("knowledge_base_id"),
        db_path=kwargs.get("db_path") or options.get("_db_path"),
    )


def generate_plan(**kwargs):
    if not kwargs:
        return _unavailable("学习计划")
    options = kwargs.get("request_options") or {}
    plan_input = options.get("plan") or {}
    if missing_plan_fields(plan_input):
        return _generate_plan(
            kwargs.get("knowledge_base_id"),
            plan_input.get("file_ids") or options.get("file_ids"),
            plan_input,
            None,
            None,
            db_path=kwargs.get("db_path") or options.get("_db_path"),
        )
    settings, llm_client, db_path, vector_store = _runtime(kwargs)
    return _generate_plan(
        kwargs.get("knowledge_base_id"),
        plan_input.get("file_ids") or options.get("file_ids"),
        plan_input,
        settings,
        llm_client,
        db_path=db_path,
        vector_store=vector_store,
    )


def generate_review(**kwargs):
    if not kwargs:
        return _unavailable("复习出题")
    options = kwargs.get("request_options") or {}
    counts = options.get("review") or options.get("counts") or {}
    settings, llm_client, db_path, vector_store = _runtime(kwargs)
    return _generate_review(
        kwargs.get("knowledge_base_id"),
        options.get("file_ids"),
        counts,
        settings,
        llm_client,
        db_path=db_path,
        vector_store=vector_store,
    )


def run_tool(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOLS:
        return {
            "status": "error",
            "tool_name": tool_name,
            "error": f"工具不存在：{tool_name}",
        }
    try:
        return {
            "status": "success",
            "tool_name": tool_name,
            "result": TOOLS[tool_name](**tool_args),
        }
    except Exception as exc:
        return {
            "status": "error",
            "tool_name": tool_name,
            "error": str(exc),
        }


register_tool("search_knowledge_base", lambda **kwargs: _unavailable("资料检索", **kwargs))
register_tool("save_preference", save_preference)
register_tool("get_progress", get_progress)
register_tool("generate_plan", generate_plan)
register_tool("generate_review", generate_review)
