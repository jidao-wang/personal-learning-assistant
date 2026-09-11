import pytest

from app.core.database import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    init_db(path)
    return path
