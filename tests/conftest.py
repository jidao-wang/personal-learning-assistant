import pytest

from app.core.config import Settings
from app.core.database import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    init_db(path)
    return path


def make_test_settings(tmp_path, db_path):
    return Settings(
        api_key="test",
        base_url="https://example.test/v1",
        chat_model="chat",
        embedding_model="embedding",
        embedding_dimension=None,
        timeout_seconds=1,
        temperature=0,
        chunk_size=20,
        chunk_overlap=3,
        top_k=3,
        score_threshold=0,
        max_file_size=10 * 1024 * 1024,
        data_dir=tmp_path,
        upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma",
        db_path=db_path,
        host="127.0.0.1",
        port=8000,
    )
