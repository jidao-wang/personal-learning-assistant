from typing import Any, Callable

from app.core.errors import AppError


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
register_tool("generate_review", lambda **kwargs: _unavailable("复习出题", **kwargs))
register_tool("generate_plan", lambda **kwargs: _unavailable("学习计划", **kwargs))
register_tool("get_progress", lambda **kwargs: _unavailable("学习统计", **kwargs))
register_tool("save_preference", lambda **kwargs: _unavailable("偏好保存", **kwargs))
