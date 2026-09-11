from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.core.database import get_connection, init_db
from app.core.errors import NotFoundError


DEFAULT_DB_PATH = Path("data/app.sqlite3")


def _db_path(db_path):
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connection(db_path):
    path = _db_path(db_path)
    init_db(path)
    return get_connection(path)


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def _json(value, fallback):
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _session_row(row):
    if row is None:
        return None
    result = dict(row)
    result["scope"] = _json(result.pop("scope_json", "{}"), {})
    return result


def _question_row(row):
    result = dict(row)
    result["options"] = _json(result.pop("options_json", "[]"), [])
    result["source_chunk_ids"] = _json(result.pop("source_chunk_ids_json", "[]"), [])
    return result


def _answer_row(row):
    result = dict(row)
    result["citations"] = _json(result.pop("citations_json", "[]"), [])
    return result


def create_review_session(knowledge_base_id, scope, questions, db_path=None):
    if not isinstance(scope, dict):
        raise ValueError("复习范围必须是对象")
    if not questions:
        raise ValueError("复习题不能为空")
    session = {
        "id": str(uuid4()),
        "knowledge_base_id": knowledge_base_id,
        "status": "draft",
        "scope": scope,
        "total_score": None,
        "created_at": _now(),
        "submitted_at": None,
    }
    with _connection(db_path) as conn:
        try:
            conn.execute(
                "INSERT INTO review_sessions "
                "(id, knowledge_base_id, status, scope_json, total_score, created_at, submitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session["id"], knowledge_base_id, session["status"],
                    json.dumps(scope, ensure_ascii=False), None,
                    session["created_at"], None,
                ),
            )
            for position, question in enumerate(questions):
                conn.execute(
                    "INSERT INTO review_questions "
                    "(id, review_session_id, position, question_type, prompt, options_json, "
                    "correct_answer, reference_answer, rubric, knowledge_point, source_chunk_ids_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid4()), session["id"], position,
                        question["question_type"], question["prompt"],
                        json.dumps(question.get("options", []), ensure_ascii=False),
                        question["correct_answer"], question["reference_answer"],
                        question["rubric"], question.get("knowledge_point", ""),
                        json.dumps(question.get("source_chunk_ids", []), ensure_ascii=False),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise NotFoundError("知识库不存在") from exc
        conn.commit()
    return {**session, "questions": list_review_questions(session["id"], db_path)}


def get_review_session(review_session_id, db_path=None):
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM review_sessions WHERE id = ?", (review_session_id,)
        ).fetchone()
    if row is None:
        raise NotFoundError("复习记录不存在")
    return _session_row(row)


def list_review_questions(review_session_id, db_path=None):
    get_review_session(review_session_id, db_path)
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM review_questions WHERE review_session_id = ? ORDER BY position, id",
            (review_session_id,),
        ).fetchall()
    return [_question_row(row) for row in rows]


def list_review_answers(review_session_id, db_path=None):
    get_review_session(review_session_id, db_path)
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM review_answers WHERE review_session_id = ? ORDER BY id",
            (review_session_id,),
        ).fetchall()
    return [_answer_row(row) for row in rows]


def save_review_draft(review_session_id, answers, db_path=None):
    session = get_review_session(review_session_id, db_path)
    if session["status"] != "draft":
        raise ValueError("复习已经提交，不能修改答案")
    questions = {question["id"] for question in list_review_questions(review_session_id, db_path)}
    if not isinstance(answers, list):
        raise ValueError("答案必须是列表")
    for answer in answers:
        if answer.get("question_id") not in questions:
            raise ValueError("题目不存在")
        if "answer_text" not in answer:
            raise ValueError("答案内容不能为空")
    now = _now()
    with _connection(db_path) as conn:
        for answer in answers:
            conn.execute(
                "INSERT INTO review_answers "
                "(id, review_session_id, question_id, answer_text, score, status, feedback, citations_json, submitted_at) "
                "VALUES (?, ?, ?, ?, NULL, 'draft', '', '[]', NULL) "
                "ON CONFLICT(question_id) DO UPDATE SET "
                "answer_text=excluded.answer_text, score=NULL, status='draft', "
                "feedback='', citations_json='[]', submitted_at=NULL",
                (str(uuid4()), review_session_id, answer["question_id"], str(answer["answer_text"])),
            )
        conn.commit()
    return list_review_answers(review_session_id, db_path)


def _save_review_results(review_session_id, answers, db_path=None):
    session = get_review_session(review_session_id, db_path)
    if session["status"] != "draft":
        raise ValueError("复习已经提交，不能保存评分")
    now = _now()
    with _connection(db_path) as conn:
        for answer in answers:
            conn.execute(
                "INSERT INTO review_answers "
                "(id, review_session_id, question_id, answer_text, score, status, feedback, citations_json, submitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(question_id) DO UPDATE SET answer_text=excluded.answer_text, "
                "score=excluded.score, status=excluded.status, feedback=excluded.feedback, "
                "citations_json=excluded.citations_json, submitted_at=excluded.submitted_at",
                (
                    str(uuid4()), review_session_id, answer["question_id"],
                    answer.get("answer_text", ""), answer["score"], answer["status"],
                    answer.get("feedback", ""),
                    json.dumps(answer.get("citations", []), ensure_ascii=False), now,
                ),
            )
        conn.commit()


def mark_review_submitted(review_session_id, total_score, db_path=None):
    session = get_review_session(review_session_id, db_path)
    if session["status"] == "submitted":
        raise ValueError("复习已经提交")
    submitted_at = _now()
    with _connection(db_path) as conn:
        conn.execute(
            "UPDATE review_sessions SET status='submitted', total_score=?, submitted_at=? WHERE id=?",
            (float(total_score), submitted_at, review_session_id),
        )
        conn.commit()


def save_weak_point(knowledge_base_id, knowledge_point, source_chunk_ids, db_path=None):
    point = str(knowledge_point).strip()
    if not point:
        raise ValueError("知识点不能为空")
    incoming = list(dict.fromkeys(source_chunk_ids or []))
    now = _now()
    with _connection(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM weak_points WHERE knowledge_base_id=? AND knowledge_point=?",
            (knowledge_base_id, point),
        ).fetchone()
        old_ids = _json(existing["source_chunk_ids_json"], []) if existing else []
        merged_ids = list(dict.fromkeys(old_ids + incoming))
        if existing:
            conn.execute(
                "UPDATE weak_points SET occurrence_count=occurrence_count+1, last_seen=?, source_chunk_ids_json=? "
                "WHERE knowledge_base_id=? AND knowledge_point=?",
                (now, json.dumps(merged_ids, ensure_ascii=False), knowledge_base_id, point),
            )
        else:
            conn.execute(
                "INSERT INTO weak_points "
                "(id, knowledge_base_id, knowledge_point, occurrence_count, last_seen, source_chunk_ids_json) "
                "VALUES (?, ?, ?, 1, ?, ?)",
                (str(uuid4()), knowledge_base_id, point, now, json.dumps(merged_ids, ensure_ascii=False)),
            )
        row = conn.execute(
            "SELECT * FROM weak_points WHERE knowledge_base_id=? AND knowledge_point=?",
            (knowledge_base_id, point),
        ).fetchone()
        conn.commit()
    result = dict(row)
    result["source_chunk_ids"] = _json(result.pop("source_chunk_ids_json"), [])
    return result
