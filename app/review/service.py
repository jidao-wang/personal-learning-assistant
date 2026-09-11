from __future__ import annotations

from app.knowledge.retriever import format_citations, format_context, retrieve
from app.review.generator import generate_questions
from app.review.grader import grade_choice, grade_judgment, grade_short_answer
from app.review.schemas import validate_question_counts
from app.storage.review_store import (
    claim_review_submission,
    create_review_session,
    finalize_review_submission,
    get_review_session,
    list_review_answers,
    list_review_questions,
    release_review_submission,
    save_review_draft,
)
from app.storage.knowledge_base_store import get_chunk_records


REVIEW_QUERY = "请提取当前资料中适合复习的核心概念、易错点和定义"


def generate_review(
    knowledge_base_id: str,
    file_ids: list[str] | None,
    counts: dict[str, int],
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    requested = validate_question_counts(
        counts.get("choice", 0), counts.get("judgment", 0), counts.get("short_answer", 0)
    )
    scope = {"file_ids": list(file_ids or [])}
    contexts = retrieve(
        knowledge_base_id, REVIEW_QUERY, file_ids=file_ids, settings=settings, vector_store=vector_store
    )
    questions = generate_questions(contexts, requested, llm_client)
    session = create_review_session(knowledge_base_id, scope, questions, db_path)
    return {
        "review_session_id": session["id"],
        "questions": session["questions"],
        "scope": scope,
    }


def save_draft(review_session_id: str, answers: list[dict], db_path=None) -> list[dict]:
    return save_review_draft(review_session_id, answers, db_path)


def _short_answer_context(question, session, settings, vector_store, db_path):
    source_ids = list(dict.fromkeys(question.get("source_chunk_ids") or []))
    if source_ids:
        results = get_chunk_records(
            session["knowledge_base_id"], source_ids, db_path
        )
        if len(results) != len(source_ids):
            raise ValueError("题目来源不存在或不属于当前知识库")
        return results
    scope_file_ids = session["scope"].get("file_ids") or []
    return retrieve(
        session["knowledge_base_id"],
        question["prompt"],
        file_ids=scope_file_ids or None,
        settings=settings,
        vector_store=vector_store,
    )


def submit_review(
    review_session_id: str,
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    if not claim_review_submission(review_session_id, db_path):
        status = get_review_session(review_session_id, db_path)["status"]
        if status == "submitted":
            raise ValueError("复习已经提交")
        if status == "submitting":
            raise ValueError("复习正在提交，请勿重复提交")
        raise ValueError("复习无法提交")
    try:
        session = get_review_session(review_session_id, db_path)
        questions = list_review_questions(review_session_id, db_path)
        if not questions:
            raise ValueError("复习题不能为空")
        draft_answers = {
            answer["question_id"]: answer
            for answer in list_review_answers(review_session_id, db_path)
        }
        results = []
        scores = []
        weak_points = []
        for question in questions:
            draft = draft_answers.get(question["id"], {})
            answer_text = draft.get("answer_text", "")
            if not answer_text.strip():
                result = {
                    "answer_text": "", "score": 0.0, "status": "unanswered",
                    "feedback": "未作答", "citations": [],
                }
            elif question["question_type"] == "choice":
                score, feedback = grade_choice(answer_text, question["correct_answer"])
                result = {
                    "answer_text": answer_text, "score": score,
                    "status": "graded", "feedback": feedback, "citations": [],
                }
            elif question["question_type"] == "judgment":
                score, feedback = grade_judgment(answer_text, question["correct_answer"])
                result = {
                    "answer_text": answer_text, "score": score,
                    "status": "graded", "feedback": feedback, "citations": [],
                }
            elif question["question_type"] == "short_answer":
                try:
                    context_results = _short_answer_context(
                        question, session, settings, vector_store, db_path
                    )
                    result = grade_short_answer(
                        question, answer_text, format_context(context_results), llm_client,
                        supplied_citations=format_citations(context_results),
                    )
                except Exception as exc:
                    result = {
                        "answer_text": answer_text, "score": 0.0,
                        "status": "grading_failed", "feedback": f"评分失败：{exc}",
                        "citations": [],
                    }
            else:
                raise ValueError("题型不受支持")
            result["question_id"] = question["id"]
            scores.append(float(result["score"]))
            if result["score"] < 60.0 or (
                question["question_type"] in {"choice", "judgment"} and result["score"] < 100.0
            ):
                if question.get("knowledge_point"):
                    weak_points.append(question)
            results.append(result)

        total_score = round(sum(scores) / len(questions), 2)
        finalize_review_submission(
            review_session_id, results, total_score, weak_points, db_path
        )
        return {
            "review_session_id": review_session_id,
            "status": "submitted",
            "total_score": total_score,
            "answers": results,
        }
    except Exception:
        release_review_submission(review_session_id, db_path)
        raise
