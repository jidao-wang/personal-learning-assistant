from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from app.core.database import get_connection, init_db


DEFAULT_DB_PATH = Path("data/app.sqlite3")
QUESTION_TYPES = ("choice", "judgment", "short_answer")


def _db_path(db_path):
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _rows(db_path, knowledge_base_id):
    path = _db_path(db_path)
    init_db(path)
    query = (
        "SELECT rs.id AS review_session_id, rs.total_score, rq.question_type, "
        "rq.knowledge_point, rq.correct_answer, ra.answer_text, ra.score "
        "FROM review_sessions rs "
        "JOIN review_questions rq ON rq.review_session_id = rs.id "
        "JOIN review_answers ra ON ra.review_session_id = rs.id AND ra.question_id = rq.id "
        "WHERE rs.status = 'submitted'"
    )
    params = []
    if knowledge_base_id is not None:
        query += " AND rs.knowledge_base_id = ?"
        params.append(knowledge_base_id)
    with get_connection(path) as conn:
        return conn.execute(query, params).fetchall()


def _empty_type_stats():
    return {
        question_type: {"question_count": 0, "accuracy": 0.0, "average_score": 0.0}
        for question_type in QUESTION_TYPES
    }


def get_progress(
    knowledge_base_id: str | None = None,
    db_path=None,
) -> dict:
    rows = _rows(db_path, knowledge_base_id)
    by_type = defaultdict(list)
    scores = []
    weak_points = []
    seen_weak_points = set()
    session_ids = set()
    for row in rows:
        raw_score = row["score"]
        if raw_score is not None:
            score = float(raw_score)
        elif row["question_type"] == "choice":
            score = 100.0 if row["answer_text"].strip().upper() == row["correct_answer"].strip().upper() else 0.0
        elif row["question_type"] == "judgment":
            score = 100.0 if row["answer_text"].strip() == row["correct_answer"].strip() else 0.0
        else:
            score = 0.0
        question_type = row["question_type"]
        by_type[question_type].append(score)
        scores.append(score)
        session_ids.add(row["review_session_id"])
        if score < 60.0 and row["knowledge_point"] and row["knowledge_point"] not in seen_weak_points:
            seen_weak_points.add(row["knowledge_point"])
            weak_points.append(row["knowledge_point"])

    question_count = len(scores)
    correct_count = sum(score >= 60.0 for score in scores)
    result = {
        "review_count": len(session_ids),
        "question_count": question_count,
        "correct_count": correct_count,
        "accuracy": round(correct_count / question_count * 100, 2) if question_count else 0.0,
        "average_score": round(sum(scores) / question_count, 2) if question_count else 0.0,
        "wrong_count": question_count - correct_count,
        "weak_points": weak_points,
        "by_question_type": _empty_type_stats(),
        "draft_review_count": 0,
    }
    for question_type, values in by_type.items():
        if question_type not in result["by_question_type"]:
            continue
        count = len(values)
        result["by_question_type"][question_type] = {
            "question_count": count,
            "accuracy": round(sum(score >= 60.0 for score in values) / count * 100, 2),
            "average_score": round(sum(values) / count, 2),
        }
    return result
