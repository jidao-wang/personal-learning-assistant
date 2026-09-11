from __future__ import annotations

import json

from app.knowledge.retriever import format_context, retrieve
from app.memory.store import get_preferences
from app.storage.plan_store import create_plan


def missing_plan_fields(plan_input: dict) -> list[str]:
    required = ["goal", "deadline", "daily_minutes"]
    return [
        key for key in required
        if plan_input.get(key) in ("", None)
        or (isinstance(plan_input.get(key), str) and not plan_input[key].strip())
    ]


def generate_plan(
    knowledge_base_id: str,
    file_ids: list[str] | None,
    plan_input: dict,
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    missing = missing_plan_fields(plan_input)
    if missing:
        return {"status": "needs_input", "missing_fields": missing}

    selected_file_ids = list(file_ids or plan_input.get("file_ids") or [])
    contexts = retrieve(
        knowledge_base_id,
        "请提取制定学习计划所需的核心概念、章节和难点",
        file_ids=selected_file_ids or None,
        settings=settings,
        vector_store=vector_store,
    )
    preferences = get_preferences(db_path=db_path)
    input_payload = {
        "goal": plan_input["goal"],
        "deadline": plan_input["deadline"],
        "daily_minutes": plan_input["daily_minutes"],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是学习计划助手。请严格依据提供的学习资料和用户偏好，"
                "生成一份完整、可编辑的 Markdown 学习计划。只返回 Markdown，"
                "不要返回 JSON、代码围栏或每日任务数据库字段。"
            ),
        },
        {
            "role": "user",
            "content": (
                "计划要求：\n"
                + json.dumps(input_payload, ensure_ascii=False)
                + "\n\n用户偏好：\n"
                + json.dumps(preferences, ensure_ascii=False)
                + "\n\n选定资料：\n"
                + (format_context(contexts) or "当前没有检索到资料，请明确标注资料不足。")
            ),
        },
    ]
    content = (llm_client.chat(messages) or "").strip()
    if not content:
        raise ValueError("模型未生成有效学习计划")
    title = str(plan_input.get("title") or f"{plan_input['goal']}学习计划").strip()
    scope = {**input_payload, "file_ids": selected_file_ids}
    plan = create_plan(knowledge_base_id, title, content, scope, db_path=db_path)
    return {"status": "created", "plan_id": plan["id"], "content": content}
