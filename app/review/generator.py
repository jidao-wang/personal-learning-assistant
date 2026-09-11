from __future__ import annotations

import json

from app.review.schemas import GeneratedQuestion, validate_question_counts


def _as_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()



def _first_present(data: dict, *keys, default=None):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _normalize_options(raw_options):
    if raw_options is None:
        return []
    if isinstance(raw_options, dict):
        items = []
        for label, value in raw_options.items():
            if isinstance(value, dict):
                text = _first_present(value, "text", "content", "label_text", default=str(value))
            else:
                text = str(value)
            items.append({"label": str(label).strip(), "text": str(text).strip()})
        # Prefer A-D order when possible.
        order = {"A": 0, "B": 1, "C": 2, "D": 3}
        items.sort(key=lambda item: order.get(item["label"], 99))
        return items
    if isinstance(raw_options, list):
        normalized = []
        for index, item in enumerate(raw_options):
            if isinstance(item, dict):
                label = _first_present(item, "label", "key", "option", default=chr(ord("A") + index))
                text = _first_present(item, "text", "content", "value", default="")
                normalized.append({"label": str(label).strip(), "text": str(text).strip()})
            else:
                normalized.append({"label": chr(ord("A") + index), "text": str(item).strip()})
        return normalized
    return []


def _normalize_judgment_answer(value) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    true_values = {"正确", "对", "true", "yes", "y", "1", "t"}
    false_values = {"错误", "错", "false", "no", "n", "0", "f"}
    if text in true_values or lowered in true_values:
        return "正确"
    if text in false_values or lowered in false_values:
        return "错误"
    return text


def _normalize_raw_question(raw_question: dict) -> dict:
    if not isinstance(raw_question, dict):
        raise ValueError("题目格式无效")

    question_type = _first_present(
        raw_question,
        "question_type",
        "type",
        "qtype",
        "questionType",
        default="",
    )
    question_type = str(question_type or "").strip()
    type_map = {
        "choice": "choice",
        "multiple_choice": "choice",
        "单选": "choice",
        "选择题": "choice",
        "judgment": "judgment",
        "true_false": "judgment",
        "判断": "judgment",
        "判断题": "judgment",
        "short_answer": "short_answer",
        "short": "short_answer",
        "简答": "short_answer",
        "简答题": "short_answer",
    }
    question_type = type_map.get(question_type, type_map.get(question_type.lower(), question_type))

    prompt = _first_present(
        raw_question,
        "prompt",
        "question",
        "stem",
        "description",
        "content",
        "title",
        default="",
    )
    options = _normalize_options(
        _first_present(raw_question, "options", "choices", default=[])
    )
    correct_answer = _first_present(
        raw_question,
        "correct_answer",
        "answer",
        "correct",
        "key",
        default="",
    )
    reference_answer = _first_present(
        raw_question,
        "reference_answer",
        "explanation",
        "analysis",
        "solution",
        default="",
    )
    rubric = _first_present(
        raw_question,
        "rubric",
        "scoring_rubric",
        "criteria",
        "grading",
        default="",
    )
    knowledge_point = _first_present(
        raw_question,
        "knowledge_point",
        "knowledge",
        "topic",
        "point",
        "tag",
        default="",
    )
    source_chunk_ids = _first_present(
        raw_question,
        "source_chunk_ids",
        "chunk_ids",
        "sources",
        "source_ids",
        default=[],
    )
    if isinstance(source_chunk_ids, str):
        source_chunk_ids = [source_chunk_ids]
    if not isinstance(source_chunk_ids, list):
        source_chunk_ids = []
    source_chunk_ids = [str(item).strip() for item in source_chunk_ids if str(item).strip()]

    if question_type == "judgment":
        correct_answer = _normalize_judgment_answer(correct_answer)
        if not reference_answer:
            reference_answer = str(correct_answer)
        if not options:
            options = []
    elif question_type == "choice":
        correct_answer = str(correct_answer or "").strip()
        # Accept full option text as answer by mapping back to label.
        labels = {item["label"]: item["text"] for item in options}
        if correct_answer not in labels:
            for label, text in labels.items():
                if correct_answer == text:
                    correct_answer = label
                    break
        if not reference_answer:
            reference_answer = labels.get(correct_answer, str(correct_answer))
    elif question_type == "short_answer":
        correct_answer = str(correct_answer or reference_answer or "").strip()
        reference_answer = str(reference_answer or correct_answer).strip()
        rubric = str(rubric or reference_answer or correct_answer).strip()
        options = []

    return {
        "question_type": question_type,
        "prompt": str(prompt or "").strip(),
        "options": options,
        "correct_answer": str(correct_answer or "").strip(),
        "reference_answer": str(reference_answer or "").strip(),
        "rubric": str(rubric or "").strip(),
        "knowledge_point": str(knowledge_point or "综合").strip() or "综合",
        "source_chunk_ids": source_chunk_ids,
    }


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
        question = GeneratedQuestion(**_normalize_raw_question(raw_question))
        actual_counts[question.question_type] += 1
        source_chunk_ids = list(question.source_chunk_ids)
        if not set(source_chunk_ids).issubset(allowed_chunk_ids):
            raise ValueError("题目包含不属于当前资料的来源")
        questions.append(_as_dict(question))
    if actual_counts != requested:
        raise ValueError("模型生成的题目数量与请求不一致")
    return questions
