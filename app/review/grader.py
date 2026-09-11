from __future__ import annotations


def grade_choice(user_answer: str, correct_answer: str) -> tuple[float, str]:
    if (user_answer or "").strip().upper() == (correct_answer or "").strip().upper():
        return 100.0, "回答正确"
    return 0.0, "回答错误"


def _normalize_judgment(answer: str) -> str:
    value = (answer or "").strip()
    return {"对": "正确", "错": "错误"}.get(value, value)


def grade_judgment(user_answer: str, correct_answer: str) -> tuple[float, str]:
    if _normalize_judgment(user_answer) == _normalize_judgment(correct_answer):
        return 100.0, "回答正确"
    return 0.0, "回答错误"


def _intersect_citations(model_citations, supplied_citations):
    allowed = {
        (item.get("source"), item.get("chunk_id")): item
        for item in (supplied_citations or [])
        if isinstance(item, dict)
    }
    result = []
    seen = set()
    for citation in model_citations or []:
        if not isinstance(citation, dict):
            continue
        key = (citation.get("source"), citation.get("chunk_id"))
        if key in allowed and key not in seen:
            result.append(dict(allowed[key]))
            seen.add(key)
    return result


def grade_short_answer(
    question: dict,
    user_answer: str,
    context: str,
    llm_client,
    supplied_citations: list[dict] | None = None,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "你是严格的学习资料评分器。只能依据给定资料、参考答案和评分标准评分。"
                "返回 JSON：score（0 到 100 的数字）、feedback（简短中文说明）、"
                "citations（只能填写给定资料中的 source 和 chunk_id）。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"问题：{question['prompt']}\n"
                f"用户答案：{user_answer}\n"
                f"参考答案：{question['reference_answer']}\n"
                f"评分标准：{question['rubric']}\n"
                f"当前资料：\n{context}"
            ),
        },
    ]
    try:
        result = llm_client.chat_json(messages)
        score = max(0.0, min(100.0, float(result["score"])))
        feedback = str(result.get("feedback", ""))
        citations = _intersect_citations(result.get("citations", []), supplied_citations)
        return {
            "score": score,
            "feedback": feedback,
            "citations": citations,
            "status": "graded",
            "answer_text": user_answer,
        }
    except Exception as exc:
        return {
            "score": 0.0,
            "feedback": f"评分失败：{exc}",
            "citations": [],
            "status": "grading_failed",
            "answer_text": user_answer,
        }
