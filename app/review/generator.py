from __future__ import annotations

import json

from app.review.schemas import GeneratedQuestion, validate_question_counts


def _as_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def generate_questions(
    contexts: list[dict],
    counts: dict[str, int],
    llm_client,
) -> list[dict]:
    requested = validate_question_counts(
        counts.get("choice", 0),
        counts.get("judgment", 0),
        counts.get("short_answer", 0),
    )
    allowed_chunk_ids = {item.get("chunk_id", "") for item in contexts if item.get("chunk_id")}
    context_payload = [
        {
            "source": item.get("source", ""),
            "chunk_id": item.get("chunk_id", ""),
            "file_id": item.get("file_id", ""),
            "text": item.get("text", ""),
        }
        for item in contexts
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是严格依据学习资料出题的复习题生成器。"
                f"必须精确生成 choice={requested['choice']}、"
                f"judgment={requested['judgment']}、"
                f"short_answer={requested['short_answer']} 道题。"
                "只返回 JSON 对象，格式为 {\"questions\":[...] }。"
                "choice 必须恰好有 A、B、C、D 四个选项；judgment 的答案只能是正确或错误；"
                "short_answer 必须有非空 rubric。source_chunk_ids 只能填写下方资料提供的 chunk_id，"
                "不得编造、改写或填写资料之外的来源。"
            ),
        },
        {
            "role": "user",
            "content": "当前资料：\n" + json.dumps(context_payload, ensure_ascii=False),
        },
    ]
    result = llm_client.chat_json(messages)
    raw_questions = result.get("questions") if isinstance(result, dict) else None
    if not isinstance(raw_questions, list):
        raise ValueError("模型生成的题目数量与请求不一致")
    if len(raw_questions) != sum(requested.values()):
        raise ValueError("模型生成的题目数量与请求不一致")

    questions = []
    actual_counts = {key: 0 for key in requested}
    for raw_question in raw_questions:
        question = GeneratedQuestion(**raw_question)
        actual_counts[question.question_type] += 1
        source_chunk_ids = list(question.source_chunk_ids)
        if not set(source_chunk_ids).issubset(allowed_chunk_ids):
            raise ValueError("题目包含不属于当前资料的来源")
        questions.append(_as_dict(question))
    if actual_counts != requested:
        raise ValueError("模型生成的题目数量与请求不一致")
    return questions
