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


def _type_system_prompt(question_type: str, count: int) -> str:
    return (
        "你是严格依据学习资料出题的复习题生成器。"
        f"ONLY_TYPE={question_type}; COUNT={count}。"
        f"必须只生成 question_type={question_type} 的题目，恰好 {count} 道，"
        f"questions 数组长度必须等于 {count}。"
        '只返回 JSON 对象，格式为 {"questions":[...]}。'
        "每题字段必须使用：question_type、prompt、options、correct_answer、"
        "reference_answer、rubric、knowledge_point、source_chunk_ids。"
        "若是 choice：options 必须是 "
        '[{"label":"A","text":"..."},{"label":"B","text":"..."},'
        '{"label":"C","text":"..."},{"label":"D","text":"..."}]，correct_answer 为 A/B/C/D。'
        "若是 judgment：correct_answer 只能是 正确 或 错误，options 为空数组。"
        "若是 short_answer：rubric 必须非空，options 为空数组。"
        "source_chunk_ids 只能填写资料中的 chunk_id，不得编造。"
    )


def _parse_questions(
    raw_questions,
    requested: dict[str, int],
    allowed_chunk_ids: set[str],
) -> tuple[list[dict], str | None]:
    if not isinstance(raw_questions, list):
        return [], "模型未返回 questions 数组"

    parsed: list[dict] = []
    for raw_question in raw_questions:
        try:
            normalized = _normalize_raw_question(raw_question)
            question = GeneratedQuestion(**normalized)
        except Exception as exc:
            return [], f"题目格式无效：{exc}"

        source_chunk_ids = list(question.source_chunk_ids)
        if source_chunk_ids and not set(source_chunk_ids).issubset(allowed_chunk_ids):
            return [], "题目包含不属于当前资料的来源"
        parsed.append(_as_dict(question))

    buckets = {key: [] for key in requested}
    for question in parsed:
        qtype = question.get("question_type")
        if qtype in buckets:
            buckets[qtype].append(question)

    actual_counts = {key: len(buckets[key]) for key in requested}
    if any(actual_counts[key] < requested[key] for key in requested):
        detail = "、".join(
            f"{key}需要{requested[key]}道/有效{actual_counts[key]}道"
            for key in requested
            if requested[key] or actual_counts[key]
        )
        return [], f"模型生成的题目数量与请求不一致（{detail}）"

    selected: list[dict] = []
    for key in ("choice", "judgment", "short_answer"):
        if key in requested:
            selected.extend(buckets[key][: requested[key]])
    return selected, None


def _generate_one_type(
    question_type: str,
    count: int,
    context_payload: list[dict],
    allowed_chunk_ids: set[str],
    llm_client,
    max_attempts: int,
) -> list[dict]:
    requested = {question_type: count}
    attempts = max(1, int(max_attempts or 1))
    last_error = "模型生成的题目数量与请求不一致"
    messages = [
        {"role": "system", "content": _type_system_prompt(question_type, count)},
        {
            "role": "user",
            "content": "当前资料：\n" + json.dumps(context_payload, ensure_ascii=False),
        },
    ]

    for attempt in range(1, attempts + 1):
        result = llm_client.chat_json(messages)
        raw_questions = result.get("questions") if isinstance(result, dict) else None
        questions, error = _parse_questions(raw_questions, requested, allowed_chunk_ids)
        if error is None:
            # Force type in case model mislabels slightly after normalize.
            fixed = []
            for item in questions:
                item = dict(item)
                item["question_type"] = question_type
                fixed.append(item)
            return fixed[:count]

        last_error = error
        if attempt >= attempts:
            break
        messages = list(messages) + [
            {
                "role": "assistant",
                "content": json.dumps(
                    result if isinstance(result, dict) else {}, ensure_ascii=False
                )[:4000],
            },
            {
                "role": "user",
                "content": (
                    f"上一次输出不合格：{error}。"
                    f"请只生成 {count} 道 {question_type} 题，questions 长度必须为 {count}。"
                    "只返回 JSON。"
                ),
            },
        ]

    if "来源" in last_error:
        raise ValueError(last_error)
    raise ValueError(
        f"{last_error}。已自动重试 {attempts} 次仍失败（题型 {question_type}×{count}），"
        "请稍后再试或先减少该题型数量。"
    )


def generate_questions(
    contexts: list[dict],
    counts: dict[str, int],
    llm_client,
    max_attempts: int = 3,
) -> list[dict]:
    """Generate by question type so mixed defaults like 2/1/1 stay reliable."""
    requested = validate_question_counts(
        counts.get("choice", 0),
        counts.get("judgment", 0),
        counts.get("short_answer", 0),
    )
    allowed_chunk_ids = {
        item.get("chunk_id", "") for item in contexts if item.get("chunk_id")
    }
    context_payload = [
        {
            "source": item.get("source", ""),
            "chunk_id": item.get("chunk_id", ""),
            "file_id": item.get("file_id", ""),
            "text": item.get("text", ""),
        }
        for item in contexts
    ]

    questions: list[dict] = []
    for question_type in ("choice", "judgment", "short_answer"):
        count = requested[question_type]
        if count <= 0:
            continue
        questions.extend(
            _generate_one_type(
                question_type,
                count,
                context_payload,
                allowed_chunk_ids,
                llm_client,
                max_attempts=max_attempts,
            )
        )
    return questions
