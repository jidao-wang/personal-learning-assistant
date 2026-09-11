from __future__ import annotations

import sqlite3
from pathlib import Path

CREATE_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (knowledge_base_id, original_name),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    vector_id TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'chat',
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_sessions (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    total_score REAL,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_questions (
    id TEXT PRIMARY KEY,
    review_session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    question_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    correct_answer TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    rubric TEXT NOT NULL,
    knowledge_point TEXT NOT NULL DEFAULT '',
    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (review_session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_answers (
    id TEXT PRIMARY KEY,
    review_session_id TEXT NOT NULL,
    question_id TEXT NOT NULL UNIQUE,
    answer_text TEXT NOT NULL DEFAULT '',
    score REAL,
    status TEXT NOT NULL DEFAULT 'draft',
    feedback TEXT NOT NULL DEFAULT '',
    citations_json TEXT NOT NULL DEFAULT '[]',
    submitted_at TEXT,
    FOREIGN KEY (review_session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES review_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weak_points (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    knowledge_point TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL,
    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (knowledge_base_id, knowledge_point),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS learning_plans (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(CREATE_SQL)
        conn.commit()
