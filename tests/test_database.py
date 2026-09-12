from pathlib import Path

from app.core.config import Settings, load_settings
from app.core.database import get_connection, init_db


def test_load_settings_uses_explicit_environment_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DASHSCOPE_API_KEY=test-key",
                "DASHSCOPE_BASE_URL=https://example.test/v1",
                "CHAT_MODEL=test-chat",
                "EMBEDDING_MODEL=test-embedding",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(env_file))

    assert isinstance(settings, Settings)
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://example.test/v1"
    assert settings.chat_model == "test-chat"
    assert settings.embedding_model == "test-embedding"
    assert settings.max_file_size == 10 * 1024 * 1024


def test_init_db_creates_all_business_tables(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"

    init_db(db_path)

    with get_connection(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "knowledge_bases",
        "files",
        "document_chunks",
        "chat_sessions",
        "chat_messages",
        "user_preferences",
        "review_sessions",
        "review_questions",
        "review_answers",
        "weak_points",
        "learning_plans",
    }.issubset(tables)


def test_connection_returns_rows_by_column_name(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    init_db(db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO knowledge_bases (id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("kb-1", "测试知识库", "2026-09-11T10:00:00", "2026-09-11T10:00:00"),
        )
        row = conn.execute(
            "SELECT id, name FROM knowledge_bases WHERE id = ?",
            ("kb-1",),
        ).fetchone()

    assert row["id"] == "kb-1"
    assert row["name"] == "测试知识库"
