# 个人学习资料问答与复习助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地运行的个人学习资料问答与复习助手，允许用户上传自己的 `txt` / `md` 文件，在多个独立知识库中进行普通聊天、资料问答、复习作答、学习计划和学习进度统计。

**Architecture:** 浏览器原生 HTML/CSS/JavaScript 通过 FastAPI 调用后端；后端使用一个 LangGraph 主 Agent 按 `chat`、`qa`、`review`、`plan`、`statistics` 路由任务。知识库资料保存为应用副本，文本切片和 Embedding 写入按知识库隔离的 Chroma collection，业务记录、会话、显式用户偏好、复习结果和计划保存到原生 SQLite。

**Tech Stack:** Python 3.10、FastAPI、Pydantic、LangGraph、OpenAI 兼容聊天接口、DashScope Embedding、Chroma、SQLite、python-dotenv、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 只支持单用户本地运行，服务只绑定 `127.0.0.1`，不实现登录、局域网访问或公网部署。
- 用户必须先创建知识库，再上传自己的 UTF-8 `.txt` / `.md` 文件；单文件最大 `10 MB`，一次上传可以包含多个文件。
- `C:\ai agent\agent-learning` 只用于参考代码风格，运行时不得自动读取、复制或导入其中的资料。
- 每个知识库独立持久化，知识库之间不得互相检索；同一知识库同名文件覆盖，不同知识库允许同名。
- 删除文件、清空知识库和删除知识库只删除应用副本、SQLite 记录和 Chroma 向量，不删除用户电脑上的原文件。
- 整个系统只有一个 LangGraph 主 Agent；RAG、Memory、复习评分和统计是工具或节点能力，不拆成多个 Agent。
- 普通聊天不调用 RAG；资料问答依据当前知识库；无命中时按用户模式拒答或明确标注通用知识，不得伪造引用。
- 复习支持选择题、判断题和简答题任意单个、两两组合或三种组合；客观题自动评分，简答题由大模型依据当前资料、参考答案和评分标准评分。
- 学习计划是可编辑文档，不创建每日打卡记录，也不统计计划完成率。
- 使用 `dataclass + python-dotenv + Path` 配置、原生 `sqlite3` 和简单 SQL、`TypedDict + StateGraph + 节点函数 + 条件路由`。
- 前端使用原生 HTML/CSS/JavaScript，不引入 React、Vue、Next.js、SQLAlchemy、Redis、Celery、消息队列或 PDF/DOCX/OCR 解析。
- API Key 只从 `.env` 读取；`.env`、上传资料、SQLite 数据库、Chroma 目录和运行日志不得提交到 GitHub。
- 所有模型和 Embedding 调用在确定性测试中使用 mock；没有真实 API Key 时，应用可以启动并提供健康检查和普通结构校验，但不能假装完成模型任务。

---

## 文件结构总览

实现完成后，工作区应保持以下职责边界：

```text
个人学习资料问答与复习助手/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── state.py
│   │   └── tools.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── errors.py
│   │   └── llm_client.py
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── answer.py
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── ingest.py
│   │   ├── retriever.py
│   │   ├── validation.py
│   │   └── vector_store.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py
│   ├── plan/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── progress/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── review/
│   │   ├── __init__.py
│   │   ├── grader.py
│   │   ├── generator.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── chat_store.py
│   │   ├── knowledge_base_store.py
│   │   ├── plan_store.py
│   │   └── review_store.py
├── data/
│   └── .gitkeep
├── eval/
│   ├── golden_questions.jsonl
│   └── run_eval.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── sample_learning.md
│   ├── test_agent.py
│   ├── test_api.py
│   ├── test_database.py
│   ├── test_ingest.py
│   ├── test_memory_plan_progress.py
│   ├── test_review.py
│   └── test_retrieval.py
├── web/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── .env.example
├── README.md
├── requirements.txt
└── pytest.ini
```

`data/` 只保存运行时数据。`tests/fixtures/sample_learning.md` 是测试专用的小资料，不代表应用默认知识库，也不读取 `agent-learning`。

### 共享接口约定

后续任务使用以下稳定接口，函数名、参数名和返回字段必须保持一致：

```python
# app.core.config
def load_settings(env_file: str | None = None) -> Settings:
    raise NotImplementedError

# app.core.database
def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    raise NotImplementedError


def init_db(db_path: Path | None = None) -> None:
    raise NotImplementedError

# app.knowledge.validation
def validate_upload(filename: str | None, content: bytes, max_size: int) -> ValidatedUpload:
    raise NotImplementedError

# app.knowledge.chunking
def clean_text(text: str) -> str:
    raise NotImplementedError


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    raise NotImplementedError

# app.knowledge.retriever
def retrieve(
    knowledge_base_id: str,
    query: str,
    file_ids: list[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> list[dict]:
    raise NotImplementedError

# app.agent.graph
def run_agent(
    user_input: str,
    session_id: str,
    knowledge_base_id: str | None,
    request_options: dict | None = None,
) -> dict:
    raise NotImplementedError
```

所有仓储函数都接收可选 `db_path: Path | None = None`，这样测试可以使用临时数据库，不会写入项目的运行数据。

---

### Task 1: 初始化工程、配置和 SQLite 数据边界

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `pytest.ini`
- Create: `data/.gitkeep`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `app/core/errors.py`
- Create: `app/core/database.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_database.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: no application modules; only `python-dotenv`, `dataclasses`, `pathlib`, `sqlite3`.
- Produces: `Settings`, `load_settings`, `get_connection`, `init_db`, and the SQLite tables used by all later tasks.

- [ ] **Step 1: Write the failing configuration and schema tests**

Create `tests/test_database.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
pytest tests/test_database.py -q
```

Expected: FAIL because `app.core.config` and `app.core.database` do not exist.

- [ ] **Step 3: Add the minimal dependency and configuration files**

Create `requirements.txt` with the first-party runtime and test dependencies:

```text
fastapi
uvicorn
python-dotenv
python-multipart
pydantic
openai
langgraph
langchain-chroma
chromadb
dashscope
pytest
httpx
```

Create `.env.example`:

```dotenv
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-max
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=
TIMEOUT_SECONDS=60
CHAT_TEMPERATURE=0.2
CHUNK_SIZE=800
CHUNK_OVERLAP=120
TOP_K=5
SCORE_THRESHOLD=0.35
DATA_DIR=data
HOST=127.0.0.1
PORT=8000
```

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 4: Implement `Settings` without importing the user's learning project**

Create `app/core/config.py`:

```python
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    api_key: str
    base_url: str
    chat_model: str
    embedding_model: str
    embedding_dimension: int | None
    timeout_seconds: float
    temperature: float
    chunk_size: int
    chunk_overlap: int
    top_k: int
    score_threshold: float
    max_file_size: int
    data_dir: Path
    upload_dir: Path
    chroma_dir: Path
    db_path: Path
    host: str
    port: int


def load_settings(env_file: str | None = None) -> Settings:
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv()

    data_dir = Path(os.getenv("DATA_DIR", "data")).resolve()
    embedding_dimension_text = os.getenv("EMBEDDING_DIMENSION", "").strip()

    return Settings(
        api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).strip(),
        chat_model=os.getenv("CHAT_MODEL", "qwen-max").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4").strip(),
        embedding_dimension=(
            int(embedding_dimension_text) if embedding_dimension_text else None
        ),
        timeout_seconds=float(os.getenv("TIMEOUT_SECONDS", "60")),
        temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "120")),
        top_k=int(os.getenv("TOP_K", "5")),
        score_threshold=float(os.getenv("SCORE_THRESHOLD", "0.35")),
        max_file_size=10 * 1024 * 1024,
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        chroma_dir=data_dir / "chroma",
        db_path=data_dir / "app.sqlite3",
        host=os.getenv("HOST", "127.0.0.1").strip(),
        port=int(os.getenv("PORT", "8000")),
    )
```

The application must not make `api_key` mandatory during import or health-check tests. Model-dependent services must raise a readable `ConfigurationError` only when a model call is actually requested.

- [ ] **Step 5: Implement the SQLite schema and connection helper**

Create `app/core/errors.py`:

```python
class AppError(Exception):
    """面向用户的可理解错误。"""


class ConfigurationError(AppError):
    """配置错误。"""


class NotFoundError(AppError):
    """资源不存在。"""


class ValidationError(AppError):
    """输入校验失败。"""
```

Create `app/core/database.py` with `sqlite3.Row`, foreign keys and these tables:

```python
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
```

`get_connection` must create the parent directory, set `row_factory = sqlite3.Row`, execute `PRAGMA foreign_keys = ON`, and return the connection. `init_db` must execute `CREATE_SQL` once per call and commit.

- [ ] **Step 6: Add temporary-database fixtures and run the tests**

Create `tests/conftest.py`:

```python
import pytest

from app.core.database import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    init_db(path)
    return path
```

Run:

```powershell
pytest tests/test_database.py -q
```

Expected: PASS.

- [ ] **Step 7: Expand `.gitignore` and commit the foundation**

Append these entries to `.gitignore`:

```gitignore
data/*
!data/.gitkeep
*.log
```

Run:

```powershell
git add requirements.txt .env.example pytest.ini data/.gitkeep app tests .gitignore
git commit -m "feat: add application foundation and sqlite schema"
```

---

### Task 2: 知识库管理、文件上传、切片和 Chroma 持久化

**Files:**
- Create: `app/storage/__init__.py`
- Create: `app/storage/knowledge_base_store.py`
- Create: `app/knowledge/__init__.py`
- Create: `app/knowledge/validation.py`
- Create: `app/knowledge/chunking.py`
- Create: `app/knowledge/embeddings.py`
- Create: `app/knowledge/vector_store.py`
- Create: `app/knowledge/ingest.py`
- Create: `tests/fixtures/sample_learning.md`
- Create: `tests/test_ingest.py`
- Modify: `app/core/database.py`

**Interfaces:**
- Consumes: `Settings`, SQLite tables from Task 1.
- Produces: CRUD for knowledge bases and files, safe upload validation, deterministic chunking, `DashScopeEmbeddingAdapter`, per-knowledge-base Chroma access, and `ingest_file`.

- [ ] **Step 1: Write validation and chunking tests**

Create `tests/test_ingest.py`:

```python
from pathlib import Path

import pytest

from app.core.errors import ValidationError
from app.knowledge.chunking import chunk_text, clean_text
from app.knowledge.validation import validate_upload


def test_validate_accepts_utf8_txt_and_md():
    txt = validate_upload("lesson.txt", "第一段\n第二段".encode("utf-8"), 10 * 1024 * 1024)
    md = validate_upload("lesson.md", "# 标题\n内容".encode("utf-8"), 10 * 1024 * 1024)

    assert txt.extension == ".txt"
    assert md.extension == ".md"


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("lesson.pdf", b"data", "只支持 .txt 和 .md"),
        ("lesson.txt", b"\xff\xfe", "UTF-8"),
        ("lesson.txt", b"", "空文件"),
    ],
)
def test_validate_rejects_invalid_upload(filename, content, message):
    with pytest.raises(ValidationError, match=message):
        validate_upload(filename, content, 10 * 1024 * 1024)


def test_validate_rejects_file_over_10_mb():
    with pytest.raises(ValidationError, match="10 MB"):
        validate_upload("large.txt", b"x" * (10 * 1024 * 1024 + 1), 10 * 1024 * 1024)


def test_chunk_text_normalizes_whitespace_and_keeps_overlap():
    text = clean_text("  第一段  \n\n\n 第二段 \r\n 第三段 ")
    chunks = chunk_text(text, chunk_size=8, chunk_overlap=2)

    assert text == "第一段\n\n第二段\n\n第三段"
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)
    assert chunks[0][-2:] in chunks[1]
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
pytest tests/test_ingest.py -q
```

Expected: FAIL because the knowledge modules do not exist.

- [ ] **Step 3: Implement upload validation with a safe filename boundary**

Create `app/knowledge/validation.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ValidationError


@dataclass
class ValidatedUpload:
    filename: str
    extension: str
    text: str
    size_bytes: int


def validate_upload(
    filename: str | None,
    content: bytes,
    max_size: int,
) -> ValidatedUpload:
    if not filename or not filename.strip():
        raise ValidationError("文件名不能为空")

    safe_name = Path(filename).name
    extension = Path(safe_name).suffix.lower()
    if extension not in {".txt", ".md"}:
        raise ValidationError("只支持 .txt 和 .md 文件")

    if len(content) > max_size:
        raise ValidationError("单个文件不能超过 10 MB")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("文件必须使用 UTF-8 编码") from exc

    text = text.replace("\x00", "").strip()
    if not text:
        raise ValidationError("空文件或清洗后没有有效文本")

    return ValidatedUpload(
        filename=safe_name,
        extension=extension,
        text=text,
        size_bytes=len(content),
    )
```

文件永远保存到由 UUID 生成的内部路径，例如 `data/uploads/<knowledge_base_id>/<file_id>.source`，不把用户文件名直接拼接为路径。

- [ ] **Step 4: Implement deterministic text cleaning and chunking**

Create `app/knowledge/chunking.py`:

```python
import re


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text)]
    return "\n\n".join(part for part in paragraphs if part)


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")

    cleaned = clean_text(text)
    if len(cleaned) <= chunk_size:
        return [cleaned]

    paragraphs = cleaned.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            overlap = current[-chunk_overlap:] if chunk_overlap else ""
            current = f"{overlap}\n\n{paragraph}".strip()
        else:
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end])
                if end == len(paragraph):
                    break
                start = end - chunk_overlap
            current = ""

    if current:
        chunks.append(current)

    return [chunk.strip() for chunk in chunks if chunk.strip()]
```

The implementation may preserve Markdown headings in the chunk content. It must not silently discard headings because they are useful citation context.

- [ ] **Step 5: Implement knowledge-base and file repository functions**

Create `app/storage/knowledge_base_store.py` with these exact functions:

```python
def create_knowledge_base(name: str, db_path: Path | None = None) -> dict:
    raise NotImplementedError


def list_knowledge_bases(db_path: Path | None = None) -> list[dict]:
    raise NotImplementedError


def get_knowledge_base(knowledge_base_id: str, db_path: Path | None = None) -> dict:
    raise NotImplementedError


def rename_knowledge_base(knowledge_base_id: str, name: str, db_path: Path | None = None) -> dict:
    raise NotImplementedError


def delete_knowledge_base(knowledge_base_id: str, db_path: Path | None = None) -> None:
    raise NotImplementedError


def list_files(knowledge_base_id: str, db_path: Path | None = None) -> list[dict]:
    raise NotImplementedError


def get_file(file_id: str, db_path: Path | None = None) -> dict:
    raise NotImplementedError


def upsert_file(file_record: dict, db_path: Path | None = None) -> dict:
    raise NotImplementedError


def delete_file_record(file_id: str, db_path: Path | None = None) -> None:
    raise NotImplementedError


def clear_file_records(knowledge_base_id: str, db_path: Path | None = None) -> None:
    raise NotImplementedError


def replace_chunk_records(file_id: str, chunks: list[dict], db_path: Path | None = None) -> None:
    raise NotImplementedError


def list_chunk_records(file_id: str, db_path: Path | None = None) -> list[dict]:
    raise NotImplementedError
```

Use UUID strings, ISO timestamps with seconds, parameterized SQL and `INSERT ... ON CONFLICT`. `create_knowledge_base` must reject a blank name and duplicate name with `ValidationError`. `delete_knowledge_base` must rely on foreign-key cascade for SQLite rows; Chroma cleanup is performed by `ingest.py` or the API service before the row is removed.

- [ ] **Step 6: Implement the Embedding adapter and per-knowledge-base vector store**

Create `app/knowledge/embeddings.py`:

```python
from http import HTTPStatus
from typing import Sequence

import dashscope


class DashScopeEmbeddingAdapter:
    def __init__(self, model: str, api_key: str, dimension: int | None = None) -> None:
        self.model = model
        self.dimension = dimension
        dashscope.api_key = api_key

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = dashscope.TextEmbedding.call(
            model=self.model,
            input=list(texts),
        )
        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(f"Embedding 失败：{response.code} {response.message}")
        embeddings = sorted(
            response.output["embeddings"],
            key=lambda item: item["text_index"],
        )
        vectors = [item["embedding"] for item in embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding 返回数量与输入文本数量不一致")
        if self.dimension and any(len(vector) != self.dimension for vector in vectors):
            raise RuntimeError("Embedding 返回维度与 EMBEDDING_DIMENSION 不一致")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]
```

Create `app/knowledge/vector_store.py`:

```python
from langchain_chroma import Chroma

from app.core.config import Settings
from app.knowledge.embeddings import DashScopeEmbeddingAdapter


def collection_name(knowledge_base_id: str) -> str:
    return f"kb_{knowledge_base_id.replace('-', '')}"


def get_vector_store(
    knowledge_base_id: str,
    settings: Settings,
    embedding_function=None,
) -> Chroma:
    embedding = embedding_function or DashScopeEmbeddingAdapter(
        model=settings.embedding_model,
        api_key=settings.api_key,
        dimension=settings.embedding_dimension,
    )
    return Chroma(
        collection_name=collection_name(knowledge_base_id),
        persist_directory=str(settings.chroma_dir),
        embedding_function=embedding,
        collection_metadata={"hnsw:space": "cosine"},
    )
```

Do not create one global collection for all knowledge bases.

- [ ] **Step 7: Implement file ingestion with overwrite, delete and failure isolation**

Create `app/knowledge/ingest.py` with:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileIngestResult:
    file_id: str | None
    filename: str
    status: str
    error_message: str = ""
    chunk_count: int = 0


def ingest_file(
    knowledge_base_id: str,
    filename: str | None,
    content: bytes,
    settings,
    db_path: Path | None = None,
    embedding_function=None,
    vector_store=None,
) -> FileIngestResult:
    raise NotImplementedError


def delete_file(
    knowledge_base_id: str,
    file_id: str,
    settings,
    db_path: Path | None = None,
    vector_store=None,
) -> None:
    raise NotImplementedError


def clear_knowledge_base(
    knowledge_base_id: str,
    settings,
    db_path: Path | None = None,
    vector_store=None,
) -> None:
    raise NotImplementedError
```

The flow is:

```text
validate bytes
→ clean and chunk text
→ calculate SHA-256
→ embed all chunks
→ upsert new vectors with metadata
→ remove stale vector IDs for the same file
→ write the internal application copy
→ replace SQLite file/chunk records with status=ready
```

Use stable vector IDs `f"{file_id}:{chunk_index}"`. The metadata for every vector must include `knowledge_base_id`, `file_id`, `source`, `title`, `chunk_id`, `content_hash` and `index_version`. For same-name overwrite, keep or create one logical file record for `(knowledge_base_id, original_name)`, remove all old chunk records before inserting the new chunk records, and ensure a failed validation does not remove the previous ready version. A failed file in a multi-file request returns `status="failed"` and does not abort processing of other files.

When deleting, remove vector IDs first, then delete the stored application copy and SQLite records. If either storage cleanup fails, raise an `AppError`; the API must not return a success response.

- [ ] **Step 8: Add ingestion tests with fake Embedding and vector-store objects**

Add to `tests/test_ingest.py`:

```python
class FakeEmbedding:
    def embed_documents(self, texts):
        return [[float(index), 1.0] for index, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.0, 1.0]


class FakeVectorStore:
    def __init__(self):
        self.records = {}

    def upsert(self, ids, documents, metadatas, embeddings):
        for vector_id, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            self.records[vector_id] = {
                "document": document,
                "metadata": metadata,
                "embedding": embedding,
            }

    def delete(self, ids):
        for vector_id in ids:
            self.records.pop(vector_id, None)


def test_ingest_writes_ready_file_and_chunk_records(tmp_path, db_path):
    from app.core.config import Settings
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("测试资料", db_path)
    settings = Settings(
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
    vector_store = FakeVectorStore()

    result = ingest_file(
        knowledge_base["id"],
        "lesson.md",
        b"# Agent\n\n这是第一段学习资料。\n\n这是第二段。",
        settings,
        db_path=db_path,
        embedding_function=FakeEmbedding(),
        vector_store=vector_store,
    )

    assert result.status == "ready"
    assert result.chunk_count >= 1
    assert len(vector_store.records) == result.chunk_count


def test_same_name_overwrite_removes_old_vector_content(
    tmp_path,
    db_path,
):
    from app.core.config import Settings
    from app.knowledge.ingest import ingest_file
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("覆盖测试", db_path)
    settings = make_test_settings(tmp_path, db_path)
    vector_store = FakeVectorStore()

    ingest_file(
        knowledge_base["id"],
        "same.txt",
        b"旧内容",
        settings,
        db_path=db_path,
        embedding_function=FakeEmbedding(),
        vector_store=vector_store,
    )
    ingest_file(
        knowledge_base["id"],
        "same.txt",
        b"新内容",
        settings,
        db_path=db_path,
        embedding_function=FakeEmbedding(),
        vector_store=vector_store,
    )

    assert all("旧内容" not in item["document"] for item in vector_store.records.values())
    assert any("新内容" in item["document"] for item in vector_store.records.values())
```

Define `make_test_settings` once in `tests/conftest.py` and import it in the test instead of duplicating a settings constructor.

- [ ] **Step 9: Run the task tests and commit**

Run:

```powershell
pytest tests/test_ingest.py -q
```

Expected: PASS, including invalid format, size, encoding, overwrite and independent failure behavior.

Commit:

```powershell
git add app/storage app/knowledge tests
git commit -m "feat: add persistent knowledge base ingestion"
```

---

### Task 3: RAG 检索、引用和通用知识边界

**Files:**
- Create: `app/core/llm_client.py`
- Create: `app/knowledge/retriever.py`
- Create: `app/knowledge/answer.py`
- Create: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: per-knowledge-base Chroma store and `document_chunks` records from Task 2.
- Produces: `OpenAI` compatible chat client, retrieved chunk dictionaries, formatted citations, strict/default/general answer behavior.

- [ ] **Step 1: Write deterministic retrieval and answer-policy tests**

Create `tests/test_retrieval.py`:

```python
from app.knowledge.answer import AnswerPolicy, build_answer_result
from app.knowledge.retriever import format_context, format_citations


def test_format_context_contains_only_actual_sources():
    results = [
        {
            "text": "Agent 是可以调用工具的程序。",
            "source": "lesson.md",
            "chunk_id": "chunk-0",
            "score": 0.91,
            "file_id": "file-1",
        }
    ]

    context = format_context(results)
    citations = format_citations(results)

    assert "lesson.md#chunk-0" in context
    assert citations == [
        {
            "source": "lesson.md",
            "chunk_id": "chunk-0",
            "file_id": "file-1",
            "score": 0.91,
        }
    ]


def test_strict_policy_rejects_empty_retrieval():
    result = build_answer_result(
        answer="",
        results=[],
        policy=AnswerPolicy.STRICT,
    )

    assert result.answer == "当前知识库中没有找到足够资料，无法只根据资料回答。"
    assert result.citations == []
    assert result.source_type == "knowledge_base"
    assert result.used_general_knowledge is False


def test_default_policy_marks_general_knowledge_explicitly():
    result = build_answer_result(
        answer="这是模型的通用解释。",
        results=[],
        policy=AnswerPolicy.DEFAULT,
    )

    assert "当前知识库没有命中" in result.answer
    assert result.source_type == "general_knowledge"
    assert result.used_general_knowledge is True
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
pytest tests/test_retrieval.py -q
```

Expected: FAIL because the retrieval and answer modules do not exist.

- [ ] **Step 3: Implement the OpenAI-compatible client**

Create `app/core/llm_client.py`:

```python
import json
from typing import Any

from openai import OpenAI

from app.core.errors import ConfigurationError


class LLMClient:
    def __init__(self, settings) -> None:
        if not settings.api_key.strip():
            raise ConfigurationError("请先在 .env 中配置 DASHSCOPE_API_KEY")
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )
        self.model = settings.chat_model
        self.temperature = settings.temperature

    def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature if temperature is None else temperature,
        )
        content = response.choices[0].message.content
        return (content or "").strip()

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        content = self.chat(messages, temperature=0)
        content = content.strip()
        if content.startswith("```"):
            content = content.removeprefix("```json").removesuffix("```").strip()
        return json.loads(content)
```

Do not log the API key, full request headers or complete private document context.

- [ ] **Step 4: Implement retrieval with optional knowledge-base file filtering**

Create `app/knowledge/retriever.py`:

```python
def retrieve(
    knowledge_base_id: str,
    query: str,
    file_ids: list[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
    settings=None,
    vector_store=None,
) -> list[dict]:
    raise NotImplementedError
```

The implementation must:

1. Use `get_vector_store(knowledge_base_id, settings)` when `vector_store` is not injected.
2. Pass `k=top_k or settings.top_k`.
3. Pass `filter={"file_id": {"$in": file_ids}}` only when `file_ids` is non-empty.
4. Call `similarity_search_with_relevance_scores`.
5. Drop scores below `score_threshold or settings.score_threshold`.
6. Return dictionaries with exactly these keys: `text`, `source`, `title`, `chunk_id`, `file_id`, `knowledge_base_id`, `score`.

Create `format_context(results)` and `format_citations(results)`:

```python
def format_context(results: list[dict]) -> str:
    return "\n\n".join(
        f"[来源: {item['source']}#{item['chunk_id']}]\n{item['text']}"
        for item in results
    )


def format_citations(results: list[dict]) -> list[dict]:
    return [
        {
            "source": item["source"],
            "chunk_id": item["chunk_id"],
            "file_id": item["file_id"],
            "score": float(item["score"]),
        }
        for item in results
    ]
```

- [ ] **Step 5: Implement answer policy and prompt boundaries**

Create `app/knowledge/answer.py`:

```python
from dataclasses import dataclass
from enum import Enum


class AnswerPolicy(str, Enum):
    DEFAULT = "default"
    STRICT = "strict"
    GENERAL = "general"


@dataclass
class AnswerResult:
    answer: str
    citations: list[dict]
    source_type: str
    used_general_knowledge: bool


def build_answer_result(
    answer: str,
    results: list[dict],
    policy: AnswerPolicy,
) -> AnswerResult:
    if results:
        return AnswerResult(
            answer=answer,
            citations=format_citations(results),
            source_type="knowledge_base",
            used_general_knowledge=False,
        )

    if policy == AnswerPolicy.STRICT:
        return AnswerResult(
            answer="当前知识库中没有找到足够资料，无法只根据资料回答。",
            citations=[],
            source_type="knowledge_base",
            used_general_knowledge=False,
        )

    return AnswerResult(
        answer=f"当前知识库没有命中相关内容。以下是模型通用知识回答：\n{answer}",
        citations=[],
        source_type="general_knowledge",
        used_general_knowledge=True,
    )
```

Add `answer_question(query, knowledge_base_id, policy, settings, llm_client, file_ids=None, vector_store=None)`. When results exist, prompt the model to answer only from the supplied context and say when the context is insufficient. When results are empty and policy is `STRICT`, do not call the model. When policy is `DEFAULT` or `GENERAL`, call the model without citations and wrap the response with the explicit general-knowledge marker. The API response must use citations built from retrieval results, never citations returned by the model.

- [ ] **Step 6: Add mock retrieval tests**

Add:

```python
class FakeVectorStore:
    def similarity_search_with_relevance_scores(self, query, k, filter=None):
        return [
            (
                type(
                    "Document",
                    (),
                    {
                        "page_content": "资料答案",
                        "metadata": {
                            "source": "lesson.md",
                            "title": "标题",
                            "chunk_id": "chunk-0",
                            "file_id": "file-1",
                            "knowledge_base_id": "kb-1",
                        },
                    },
                )(),
                0.88,
            )
        ]


def test_retrieve_filters_by_selected_files(monkeypatch):
    from app.knowledge.retriever import retrieve

    store = FakeVectorStore()
    results = retrieve(
        "kb-1",
        "问题",
        file_ids=["file-1"],
        settings=type("Settings", (), {"top_k": 3, "score_threshold": 0.3})(),
        vector_store=store,
    )

    assert results[0]["source"] == "lesson.md"
```

Use a spy or extend the fake store if the test needs to assert the exact `filter` argument.

- [ ] **Step 7: Run tests and commit**

Run:

```powershell
pytest tests/test_retrieval.py -q
```

Expected: PASS without a real API key or network request.

Commit:

```powershell
git add app/core/llm_client.py app/knowledge tests/test_retrieval.py
git commit -m "feat: add grounded retrieval and citation policy"
```

---

### Task 4: LangGraph 单主 Agent、会话持久化和聊天路由

**Files:**
- Create: `app/storage/chat_store.py`
- Create: `app/agent/__init__.py`
- Create: `app/agent/state.py`
- Create: `app/agent/tools.py`
- Create: `app/agent/nodes.py`
- Create: `app/agent/graph.py`
- Create: `tests/test_agent.py`

**Interfaces:**
- Consumes: Task 1 chat tables, Task 3 answer service, and later review/plan/progress services through tool call boundaries.
- Produces: one compiled LangGraph, deterministic task classification, explicit retrieval override parsing, tool registry, and persisted chat messages.

- [ ] **Step 1: Write route and override tests**

Create `tests/test_agent.py`:

```python
from app.agent.nodes import classify_task, parse_request_options


def test_plain_greeting_routes_to_chat_without_knowledge_base():
    assert classify_task("你好", knowledge_base_id=None) == "chat"


def test_explicit_knowledge_question_routes_to_qa():
    assert classify_task(
        "根据当前资料解释什么是 Agent",
        knowledge_base_id="kb-1",
    ) == "qa"


def test_review_plan_and_statistics_routes_are_distinct():
    assert classify_task("根据当前资料出 5 道题", "kb-1") == "review"
    assert classify_task("帮我制定学习计划", "kb-1") == "plan"
    assert classify_task("统计我的答题情况", "kb-1") == "statistics"


def test_no_rag_override_wins_over_knowledge_words():
    options = parse_request_options("不要查资料，解释什么是 Agent")

    assert options["retrieval_mode"] == "force_chat"
    assert classify_task(
        "不要查资料，解释什么是 Agent",
        knowledge_base_id="kb-1",
    ) == "chat"


def test_strict_and_general_overrides_are_parsed():
    assert parse_request_options("只根据资料回答")["retrieval_mode"] == "strict"
    assert parse_request_options("允许使用通用知识")["retrieval_mode"] == "general"
```

- [ ] **Step 2: Run the route tests to verify failure**

Run:

```powershell
pytest tests/test_agent.py -q
```

Expected: FAIL because the Agent modules do not exist.

- [ ] **Step 3: Define the typed Agent state**

Create `app/agent/state.py`:

```python
from typing import Any, Literal, TypedDict


TaskType = Literal["chat", "qa", "review", "plan", "statistics"]
RetrievalMode = Literal["default", "force_chat", "strict", "general"]


class AgentState(TypedDict, total=False):
    user_input: str
    session_id: str
    knowledge_base_id: str | None
    request_options: dict[str, Any]
    retrieval_mode: RetrievalMode
    task_type: TaskType
    messages: list[dict[str, str]]
    answer: str
    citations: list[dict]
    workspace_type: str
    workspace_id: str
    statistics: dict[str, Any]
    error: str
    path: list[str]
```

- [ ] **Step 4: Implement deterministic classification and override parsing**

Create `app/agent/nodes.py` functions:

```python
def parse_request_options(user_input: str) -> dict[str, Any]:
    raise NotImplementedError


def classify_task(user_input: str, knowledge_base_id: str | None) -> str:
    raise NotImplementedError


def classify_route_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def route_after_classify(state: AgentState) -> str:
    raise NotImplementedError


def chat_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def qa_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def review_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def plan_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def statistics_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError


def error_node(state: AgentState) -> dict[str, Any]:
    raise NotImplementedError
```

Classification priority must be:

```text
1. parse "不要查资料/只聊天/不用知识库" as force_chat
2. recognize review keywords: 出题、复习、测试、题目
3. recognize plan keywords: 学习计划、安排、规划
4. recognize statistics keywords: 统计、进度、正确率、错题、薄弱
5. recognize strict/general/knowledge keywords as qa
6. with a selected knowledge base, question-like "什么是/如何/解释/区别/根据资料" is qa
7. otherwise chat
```

If `knowledge_base_id` is absent and the chosen task is `qa`, `review`, `plan` or `statistics`, route to `error_node` with a message that explicitly asks the user to select or create a knowledge base. Do not silently downgrade these tasks to chat.

- [ ] **Step 5: Implement the explicit tool registry**

Create `app/agent/tools.py`:

```python
from typing import Any, Callable


TOOLS: dict[str, Callable[..., Any]] = {}
TOOL_METADATA = {
    "search_knowledge_base": {"requires_confirmation": False},
    "generate_review": {"requires_confirmation": False},
    "generate_plan": {"requires_confirmation": False},
    "get_progress": {"requires_confirmation": False},
    "save_preference": {"requires_confirmation": False},
}


def register_tool(name: str, function: Callable[..., Any]) -> None:
    TOOLS[name] = function


def run_tool(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOLS:
        return {
            "status": "error",
            "tool_name": tool_name,
            "error": f"工具不存在：{tool_name}",
        }
    try:
        return {
            "status": "success",
            "tool_name": tool_name,
            "result": TOOLS[tool_name](**tool_args),
        }
    except Exception as exc:
        return {
            "status": "error",
            "tool_name": tool_name,
            "error": str(exc),
        }
```

Register concrete functions at graph construction time or module initialization, but keep the registry explicit so tests can replace a tool without modifying the route logic.

- [ ] **Step 6: Implement the graph and the chat store**

Create `app/storage/chat_store.py`:

```python
def create_session(
    knowledge_base_id: str | None,
    db_path=None,
) -> dict:
    raise NotImplementedError


def get_session(session_id: str, db_path=None) -> dict:
    raise NotImplementedError


def list_sessions(db_path=None) -> list[dict]:
    raise NotImplementedError
def add_message(
    session_id: str,
    role: str,
    content: str,
    task_type: str,
    citations: list[dict] | None = None,
    db_path=None,
) -> dict:
    raise NotImplementedError


def list_messages(session_id: str, db_path=None) -> list[dict]:
    raise NotImplementedError
```

Create `app/agent/graph.py` in the same shape as the existing LangGraph exercises:

```python
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.state import AgentState


def build_graph() -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("classify_route_node", classify_route_node)
    graph.add_node("chat_node", chat_node)
    graph.add_node("qa_node", qa_node)
    graph.add_node("review_node", review_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("statistics_node", statistics_node)
    graph.add_node("error_node", error_node)
    graph.add_edge(START, "classify_route_node")
    graph.add_conditional_edges(
        "classify_route_node",
        route_after_classify,
        {
            "chat_node": "chat_node",
            "qa_node": "qa_node",
            "review_node": "review_node",
            "plan_node": "plan_node",
            "statistics_node": "statistics_node",
            "error_node": "error_node",
        },
    )
    for node_name in (
        "chat_node",
        "qa_node",
        "review_node",
        "plan_node",
        "statistics_node",
        "error_node",
    ):
        graph.add_edge(node_name, END)
    return graph.compile()
```

`run_agent` must initialize `messages` from `chat_store.list_messages`, invoke the compiled graph, and return a plain dictionary containing `task_type`, `answer`, `citations`, `workspace_type`, `workspace_id`, `statistics` and `path`. The API layer saves the user message before invocation and the assistant message after invocation.

- [ ] **Step 7: Add graph behavior tests with mocks**

Add:

```python
def test_plain_chat_does_not_call_retriever(monkeypatch):
    from app.agent import nodes

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("普通聊天不应该调用 RAG")

    monkeypatch.setattr(nodes, "answer_question", fail_if_called)
    result = nodes.chat_node(
        {
            "user_input": "你好",
            "session_id": "session-1",
            "knowledge_base_id": None,
            "messages": [],
            "request_options": {},
            "path": [],
        }
    )

    assert result["task_type"] == "chat"
    assert called is False


def test_missing_knowledge_base_is_clear_error():
    from app.agent.nodes import error_node

    result = error_node(
        {
            "error": "资料问答、复习、学习计划和学习统计需要先选择知识库。",
            "path": [],
        }
    )

    assert "选择知识库" in result["answer"]
```

Use monkeypatched `LLMClient` or an injected fake for `chat_node`; no real network calls are allowed.

- [ ] **Step 8: Run tests and commit**

Run:

```powershell
pytest tests/test_agent.py -q
```

Expected: PASS, including the “不要查资料” override and no-RAG greeting path.

Commit:

```powershell
git add app/agent app/storage/chat_store.py tests/test_agent.py
git commit -m "feat: add single-agent task routing and chat sessions"
```

---

### Task 5: 复习题生成、独立作答工作区和评分闭环

**Files:**
- Create: `app/review/__init__.py`
- Create: `app/review/schemas.py`
- Create: `app/review/generator.py`
- Create: `app/review/grader.py`
- Create: `app/review/service.py`
- Create: `app/storage/review_store.py`
- Create: `tests/test_review.py`

**Interfaces:**
- Consumes: selected knowledge-base chunks, `LLMClient`, review SQLite tables.
- Produces: validated question sets, draft saving, one-time submission, objective grading, short-answer grading, weak-point persistence.

- [ ] **Step 1: Write question validation and objective grading tests**

Create `tests/test_review.py`:

```python
from app.review.grader import grade_choice, grade_judgment
from app.review.schemas import QuestionType, validate_question_counts


def test_user_can_choose_one_two_or_three_question_types():
    assert validate_question_counts(5, 0, 0) == {"choice": 5, "judgment": 0, "short_answer": 0}
    assert validate_question_counts(2, 3, 0) == {"choice": 2, "judgment": 3, "short_answer": 0}
    assert validate_question_counts(2, 2, 1) == {"choice": 2, "judgment": 2, "short_answer": 1}


def test_at_least_one_question_is_required():
    try:
        validate_question_counts(0, 0, 0)
    except ValueError as exc:
        assert "至少选择一种题型" in str(exc)
    else:
        raise AssertionError("应该拒绝空题型配置")


def test_objective_questions_are_scored_without_llm():
    assert grade_choice("A", "A") == (100.0, "回答正确")
    assert grade_choice("B", "A") == (0.0, "回答错误")
    assert grade_judgment("正确", "正确") == (100.0, "回答正确")
    assert grade_judgment("错误", "正确") == (0.0, "回答错误")
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
pytest tests/test_review.py -q
```

Expected: FAIL because the review modules do not exist.

- [ ] **Step 3: Define review schemas and counts**

Create `app/review/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


QuestionType = Literal["choice", "judgment", "short_answer"]


class GeneratedOption(BaseModel):
    label: str = Field(min_length=1, max_length=4)
    text: str = Field(min_length=1, max_length=500)


class GeneratedQuestion(BaseModel):
    question_type: QuestionType
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[GeneratedOption] = []
    correct_answer: str
    reference_answer: str
    rubric: str
    knowledge_point: str
    source_chunk_ids: list[str] = []


def validate_question_counts(
    choice_count: int,
    judgment_count: int,
    short_answer_count: int,
) -> dict[str, int]:
    counts = {
        "choice": choice_count,
        "judgment": judgment_count,
        "short_answer": short_answer_count,
    }
    if any(count < 0 for count in counts.values()):
        raise ValueError("题目数量不能为负数")
    if sum(counts.values()) == 0:
        raise ValueError("至少选择一种题型")
    return counts
```

Use `Field(default_factory=list)` instead of a mutable literal in the actual Pydantic model:

```python
options: list[GeneratedOption] = Field(default_factory=list)
source_chunk_ids: list[str] = Field(default_factory=list)
```

Validate that choice questions contain exactly four options, judgment questions have a correct answer in `正确/错误`, and short-answer questions have a non-empty rubric.

- [ ] **Step 4: Implement deterministic and model-based grading**

Create `app/review/grader.py`:

```python
def grade_choice(user_answer: str, correct_answer: str) -> tuple[float, str]:
    if user_answer.strip().upper() == correct_answer.strip().upper():
        return 100.0, "回答正确"
    return 0.0, "回答错误"


def grade_judgment(user_answer: str, correct_answer: str) -> tuple[float, str]:
    normalized_user = user_answer.strip().replace("对", "正确").replace("错", "错误")
    normalized_correct = correct_answer.strip().replace("对", "正确").replace("错", "错误")
    if normalized_user == normalized_correct:
        return 100.0, "回答正确"
    return 0.0, "回答错误"


def grade_short_answer(
    question: dict,
    user_answer: str,
    context: str,
    llm_client,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "你是严格的学习资料评分器。只能依据给定资料、参考答案和评分标准评分。"
                "返回 JSON：score（0 到 100 的数字）、feedback（简短中文说明）、"
                "citations（只能填写给定资料中的 source 和 chunk_id）。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"问题：{question['prompt']}\n"
                f"用户答案：{user_answer}\n"
                f"参考答案：{question['reference_answer']}\n"
                f"评分标准：{question['rubric']}\n"
                f"当前资料：\n{context}"
            ),
        },
    ]
    result = llm_client.chat_json(messages)
    score = max(0.0, min(100.0, float(result["score"])))
    return {
        "score": score,
        "feedback": str(result.get("feedback", "")),
        "citations": result.get("citations", []),
        "status": "graded",
    }
```

Before saving model citations, intersect them with the actual source chunk IDs supplied to the prompt. If the model fails, return `status="grading_failed"` with a readable error and keep the user answer.

- [ ] **Step 5: Implement model-driven question generation**

Create `app/review/generator.py`:

```python
def generate_questions(
    contexts: list[dict],
    counts: dict[str, int],
    llm_client,
) -> list[dict]:
    raise NotImplementedError
```

The prompt must require exactly the requested number of each type and JSON in this shape:

```json
{
  "questions": [
    {
      "question_type": "choice",
      "prompt": "问题",
      "options": [
        {"label": "A", "text": "选项一"},
        {"label": "B", "text": "选项二"},
        {"label": "C", "text": "选项三"},
        {"label": "D", "text": "选项四"}
      ],
      "correct_answer": "A",
      "reference_answer": "A",
      "rubric": "选择正确选项",
      "knowledge_point": "知识点",
      "source_chunk_ids": ["file-1:0"]
    }
  ]
}
```

The prompt must say that `source_chunk_ids` can only contain IDs from the supplied context. Parse the response through `GeneratedQuestion`, validate exact counts, and raise `ValueError("模型生成的题目数量与请求不一致")` when counts do not match.

- [ ] **Step 6: Implement the review store and service**

Create `app/storage/review_store.py` with:

```python
def create_review_session(
    knowledge_base_id: str,
    scope: dict,
    questions: list[dict],
    db_path=None,
) -> dict:
    raise NotImplementedError


def get_review_session(review_session_id: str, db_path=None) -> dict:
    raise NotImplementedError


def list_review_questions(review_session_id: str, db_path=None) -> list[dict]:
    raise NotImplementedError


def save_review_draft(
    review_session_id: str,
    answers: list[dict],
    db_path=None,
) -> list[dict]:
    raise NotImplementedError


def mark_review_submitted(
    review_session_id: str,
    total_score: float,
    db_path=None,
) -> None:
    raise NotImplementedError


def save_weak_point(
    knowledge_base_id: str,
    knowledge_point: str,
    source_chunk_ids: list[str],
    db_path=None,
) -> dict:
    raise NotImplementedError
```

Create `app/review/service.py`:

```python
def generate_review(
    knowledge_base_id: str,
    file_ids: list[str] | None,
    counts: dict[str, int],
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    raise NotImplementedError


def save_draft(
    review_session_id: str,
    answers: list[dict],
    db_path=None,
) -> list[dict]:
    raise NotImplementedError


def submit_review(
    review_session_id: str,
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    raise NotImplementedError
```

`generate_review` retrieves context using a fixed query `"请提取当前资料中适合复习的核心概念、易错点和定义"` and the selected `file_ids`. `submit_review` must reject a session already marked `submitted`, save objective scores directly, retrieve context for every short-answer question using its source chunk IDs or the session file scope, call `grade_short_answer`, calculate `round(sum(scores) / question_count, 2)`, save weak points for incorrect or below-60 answers, and then lock the session.

- [ ] **Step 7: Add review tests with fake LLM and vector store**

Add:

```python
import pytest


class FakeVectorStoreWithContext:
    def similarity_search_with_relevance_scores(self, query, k, filter=None):
        return [
            (
                type(
                    "Document",
                    (),
                    {
                        "page_content": "Agent 可以根据任务调用工具。",
                        "metadata": {
                            "source": "lesson.md",
                            "title": "Agent",
                            "chunk_id": "file-1:0",
                            "file_id": "file-1",
                            "knowledge_base_id": "kb-1",
                        },
                    },
                )(),
                0.9,
            )
        ]


class FakeReviewLLM:
    def chat_json(self, messages):
        if "评分器" in messages[0]["content"]:
            return {
                "score": 80,
                "feedback": "覆盖了主要概念，但缺少一个关键条件。",
                "citations": [{"source": "lesson.md", "chunk_id": "file-1:0"}],
            }
        return {
            "questions": [
                {
                    "question_type": "choice",
                    "prompt": "Agent 的核心能力是什么？",
                    "options": [
                        {"label": "A", "text": "调用工具"},
                        {"label": "B", "text": "只输出固定文本"},
                        {"label": "C", "text": "删除资料"},
                        {"label": "D", "text": "关闭程序"},
                    ],
                    "correct_answer": "A",
                    "reference_answer": "A",
                    "rubric": "选择正确选项",
                    "knowledge_point": "Agent",
                    "source_chunk_ids": ["file-1:0"],
                }
            ]
        }


def test_generate_review_can_create_one_question_type(db_path, tmp_path):
    from app.core.config import Settings
    from app.review.service import generate_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("复习测试", db_path)
    settings = make_test_settings(tmp_path, db_path)

    result = generate_review(
        knowledge_base["id"],
        file_ids=None,
        counts={"choice": 1, "judgment": 0, "short_answer": 0},
        settings=settings,
        llm_client=FakeReviewLLM(),
        db_path=db_path,
        vector_store=FakeVectorStoreWithContext(),
    )

    assert result["review_session_id"]
    assert len(result["questions"]) == 1
    assert result["questions"][0]["question_type"] == "choice"


def test_submit_review_scores_objective_answers_and_locks_session(
    db_path,
    tmp_path,
):
    from app.core.config import Settings
    from app.review.service import submit_review
    from app.storage.review_store import (
        create_review_session,
        save_review_draft,
    )

    review = create_review_session(
        "kb-1",
        {"file_ids": []},
        [
            {
                "question_type": "choice",
                "prompt": "Agent 的核心能力是什么？",
                "options": [
                    {"label": "A", "text": "调用工具"},
                    {"label": "B", "text": "只输出固定文本"},
                    {"label": "C", "text": "删除资料"},
                    {"label": "D", "text": "关闭程序"},
                ],
                "correct_answer": "A",
                "reference_answer": "A",
                "rubric": "选择正确选项",
                "knowledge_point": "Agent",
                "source_chunk_ids": ["file-1:0"],
            }
        ],
        db_path=db_path,
    )
    question_id = review["questions"][0]["id"]
    save_review_draft(
        review["id"],
        [{"question_id": question_id, "answer_text": "A"}],
        db_path=db_path,
    )

    result = submit_review(
        review["id"],
        settings=make_test_settings(tmp_path, db_path),
        llm_client=FakeReviewLLM(),
        db_path=db_path,
        vector_store=FakeVectorStoreWithContext(),
    )

    assert result["total_score"] == 100.0
    assert result["status"] == "submitted"
    with pytest.raises(ValueError, match="已经提交"):
        submit_review(
            review["id"],
            settings=make_test_settings(tmp_path, db_path),
            llm_client=FakeReviewLLM(),
            db_path=db_path,
            vector_store=FakeVectorStoreWithContext(),
        )
```

The test uses only the deterministic choice grader; the fake LLM is passed to keep the service signature identical to the short-answer path.

- [ ] **Step 8: Run tests and commit**

Run:

```powershell
pytest tests/test_review.py -q
```

Expected: PASS for single type, two-type and three-type count validation, objective scoring, short-answer mock scoring, weak-point persistence and submission locking.

Commit:

```powershell
git add app/review app/storage/review_store.py tests/test_review.py
git commit -m "feat: add review workspace and grading loop"
```

---

### Task 6: 显式偏好 Memory、学习计划和实际学习进度

**Files:**
- Create: `app/memory/__init__.py`
- Create: `app/memory/store.py`
- Create: `app/plan/__init__.py`
- Create: `app/plan/service.py`
- Create: `app/storage/plan_store.py`
- Create: `app/progress/__init__.py`
- Create: `app/progress/service.py`
- Create: `tests/test_memory_plan_progress.py`
- Modify: `app/agent/tools.py`
- Modify: `app/agent/nodes.py`

**Interfaces:**
- Consumes: SQLite preference, plan, review and weak-point data.
- Produces: explicit preference saving, plan generation/edit/save, current/all knowledge-base progress statistics.

- [ ] **Step 1: Write preference, plan and progress tests**

Create `tests/test_memory_plan_progress.py`:

```python
from app.storage.knowledge_base_store import create_knowledge_base
from app.storage.review_store import (
    create_review_session,
    mark_review_submitted,
    save_review_draft,
)


def seed_submitted_and_draft_reviews(db_path):
    knowledge_base = create_knowledge_base("进度测试", db_path)
    questions = [
        {
            "question_type": "choice",
            "prompt": "问题一",
            "options": [
                {"label": "A", "text": "正确"},
                {"label": "B", "text": "错误"},
                {"label": "C", "text": "干扰"},
                {"label": "D", "text": "干扰"},
            ],
            "correct_answer": "A",
            "reference_answer": "A",
            "rubric": "选择正确选项",
            "knowledge_point": "概念一",
            "source_chunk_ids": [],
        },
        {
            "question_type": "judgment",
            "prompt": "问题二",
            "options": [],
            "correct_answer": "正确",
            "reference_answer": "正确",
            "rubric": "判断正误",
            "knowledge_point": "概念二",
            "source_chunk_ids": [],
        },
    ]
    submitted = create_review_session(
        knowledge_base["id"],
        {"file_ids": []},
        questions,
        db_path=db_path,
    )
    save_review_draft(
        submitted["id"],
        [
            {
                "question_id": submitted["questions"][0]["id"],
                "answer_text": "A",
            },
            {
                "question_id": submitted["questions"][1]["id"],
                "answer_text": "错误",
            },
        ],
        db_path=db_path,
    )
    mark_review_submitted(submitted["id"], 50.0, db_path=db_path)
    create_review_session(
        knowledge_base["id"],
        {"file_ids": []},
        [questions[0]],
        db_path=db_path,
    )
    return knowledge_base["id"]


def test_only_explicit_preference_is_saved(db_path):
    from app.memory.store import parse_preference_request, save_preference

    assert parse_preference_request("你好") is None
    parsed = parse_preference_request("记住我喜欢简洁回答")

    assert parsed == {"key": "answer_style", "value": "简洁回答"}
    save_preference(parsed["key"], parsed["value"], db_path=db_path)


def test_plan_requires_goal_deadline_and_daily_minutes():
    from app.plan.service import missing_plan_fields

    assert missing_plan_fields(
        {"goal": "掌握 Agent", "deadline": "", "daily_minutes": None}
    ) == ["deadline", "daily_minutes"]


def test_progress_counts_only_submitted_reviews(db_path):
    from app.progress.service import get_progress

    knowledge_base_id = seed_submitted_and_draft_reviews(db_path)
    progress = get_progress(knowledge_base_id=knowledge_base_id, db_path=db_path)

    assert progress["review_count"] == 1
    assert progress["question_count"] == 2
    assert progress["draft_review_count"] == 0
    assert "plan_completion_rate" not in progress
```

Implement `seed_submitted_and_draft_reviews` with the review store, using one submitted session and one draft session. It must not rely on a model.

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
pytest tests/test_memory_plan_progress.py -q
```

Expected: FAIL because memory, plan and progress modules do not exist.

- [ ] **Step 3: Implement explicit preference storage**

Create `app/memory/store.py`:

```python
import re
from datetime import datetime


def parse_preference_request(user_input: str) -> dict | None:
    text = user_input.strip()
    match = re.match(r"记住我(?:喜欢|希望)(.+)", text)
    if not match:
        return None
    return {"key": "answer_style", "value": match.group(1).strip()}


def save_preference(key: str, value: str, db_path=None) -> dict:
    raise NotImplementedError


def get_preferences(db_path=None) -> dict[str, str]:
    raise NotImplementedError
```

`save_preference` must reject values containing `api_key`, `password`, `token`, `secret`, 身份证, 手机号, 银行卡 or other obvious secrets. It must use `ON CONFLICT(key) DO UPDATE`. Ordinary chat messages must never call `save_preference`.

- [ ] **Step 4: Implement plan generation and persistence**

Create `app/storage/plan_store.py`:

```python
def create_plan(
    knowledge_base_id: str,
    title: str,
    content: str,
    scope: dict,
    db_path=None,
) -> dict:
    raise NotImplementedError


def get_plan(plan_id: str, db_path=None) -> dict:
    raise NotImplementedError


def update_plan(plan_id: str, content: str, db_path=None) -> dict:
    raise NotImplementedError
```

Create `app/plan/service.py`:

```python
def missing_plan_fields(plan_input: dict) -> list[str]:
    required = ["goal", "deadline", "daily_minutes"]
    return [
        key for key in required
        if plan_input.get(key) in ("", None)
    ]


def generate_plan(
    knowledge_base_id: str,
    file_ids: list[str] | None,
    plan_input: dict,
    settings,
    llm_client,
    db_path=None,
    vector_store=None,
) -> dict:
    raise NotImplementedError
```

If fields are missing, return `{"status": "needs_input", "missing_fields": [...]}` without calling the model. If complete, retrieve selected/current knowledge-base context, include `get_preferences()` in the prompt, ask for a complete editable Markdown document, save it and return an object with `status="created"`, the persisted `plan_id` and the generated Markdown `content`. Do not create daily-task rows or completion fields.

- [ ] **Step 5: Implement progress queries**

Create `app/progress/service.py`:

```python
def get_progress(
    knowledge_base_id: str | None = None,
    db_path=None,
) -> dict:
    raise NotImplementedError
```

Use only `review_sessions.status = 'submitted'` and their `review_answers` rows. Return:

```python
{
    "review_count": 0,
    "question_count": 0,
    "correct_count": 0,
    "accuracy": 0.0,
    "average_score": 0.0,
    "wrong_count": 0,
    "weak_points": [],
    "by_question_type": {
        "choice": {"question_count": 0, "accuracy": 0.0, "average_score": 0.0},
        "judgment": {"question_count": 0, "accuracy": 0.0, "average_score": 0.0},
        "short_answer": {"question_count": 0, "accuracy": 0.0, "average_score": 0.0},
    },
}
```

When `knowledge_base_id` is `None`, aggregate all knowledge bases. Never include chat count, file count, plan count or plan completion rate.

- [ ] **Step 6: Register tools and connect Agent nodes**

Register these functions in `app/agent/tools.py`:

```python
register_tool("save_preference", save_preference)
register_tool("get_progress", get_progress)
register_tool("generate_plan", generate_plan)
register_tool("generate_review", generate_review)
```

Update `plan_node` to parse structured `request_options["plan"]`, call `generate_plan`, and return a `workspace_type="plan"` and `workspace_id` on success. If the service returns `needs_input`, return a follow-up question listing only missing fields. Update `statistics_node` to return the progress dictionary. Update `chat_node` so a message matching `parse_preference_request` saves the explicit preference and confirms it; messages that merely contain a preference-like sentence without “记住” remain ordinary chat.

- [ ] **Step 7: Run tests and commit**

Run:

```powershell
pytest tests/test_memory_plan_progress.py tests/test_agent.py -q
```

Expected: PASS for explicit memory, missing plan fields, plan persistence, current/all knowledge-base progress and Agent integration.

Commit:

```powershell
git add app/memory app/plan app/progress app/storage/plan_store.py app/agent tests
git commit -m "feat: add preferences plans and learning progress"
```

---

### Task 7: FastAPI API、独立工作区前端、评测和交付文档

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/schemas.py`
- Create: `app/api/routes.py`
- Create: `app/main.py`
- Create: `web/index.html`
- Create: `web/app.js`
- Create: `web/styles.css`
- Create: `eval/golden_questions.jsonl`
- Create: `eval/run_eval.py`
- Create: `tests/test_api.py`
- Create: `tests/fixtures/sample_learning.md`
- Create: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: all services and the LangGraph graph from Tasks 1–6.
- Produces: localhost web application, documented JSON APIs, independent review/plan/progress workspaces, deterministic API tests and a GitHub-safe repository.

- [ ] **Step 1: Define API schemas and write endpoint tests first**

Create `app/api/schemas.py`:

```python
from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class KnowledgeBaseRenameRequest(KnowledgeBaseCreateRequest):
    """重命名知识库时复用同一名称校验。"""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    knowledge_base_id: str | None = None
    review: dict | None = None
    plan: dict | None = None


class SessionCreateRequest(BaseModel):
    knowledge_base_id: str | None = None


class ReviewCreateRequest(BaseModel):
    knowledge_base_id: str
    file_ids: list[str] = Field(default_factory=list)
    choice_count: int = Field(default=0, ge=0, le=50)
    judgment_count: int = Field(default=0, ge=0, le=50)
    short_answer_count: int = Field(default=0, ge=0, le=50)


class ReviewDraftRequest(BaseModel):
    answers: list[dict]


class PlanCreateRequest(BaseModel):
    knowledge_base_id: str
    file_ids: list[str] = Field(default_factory=list)
    goal: str = ""
    deadline: str = ""
    daily_minutes: int | None = Field(default=None, ge=1, le=1440)
    extra_requirements: str = ""


class PlanUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
```

Create `tests/test_api.py` with the first endpoint contract:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_chat_rejects_empty_message():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_create_and_list_knowledge_bases():
    created = client.post(
        "/api/knowledge-bases",
        json={"name": "API 测试知识库"},
    )
    assert created.status_code == 200
    knowledge_base_id = created.json()["id"]

    listed = client.get("/api/knowledge-bases")
    assert listed.status_code == 200
    assert any(item["id"] == knowledge_base_id for item in listed.json())
```

Configure the test app through `app.dependency_overrides` or a test settings factory so it uses a temporary SQLite/Chroma location. Do not let API tests write the real `data/` directory.

- [ ] **Step 2: Run API tests to verify failure**

Run:

```powershell
pytest tests/test_api.py -q
```

Expected: FAIL because `app.main` and API routes do not exist.

- [ ] **Step 3: Implement the API routes**

Create `app/api/routes.py` with these endpoints:

```text
GET    /health
GET    /api/knowledge-bases
POST   /api/knowledge-bases
PATCH  /api/knowledge-bases/{knowledge_base_id}
DELETE /api/knowledge-bases/{knowledge_base_id}
GET    /api/knowledge-bases/{knowledge_base_id}/files
POST   /api/knowledge-bases/{knowledge_base_id}/files
DELETE /api/knowledge-bases/{knowledge_base_id}/files/{file_id}
DELETE /api/knowledge-bases/{knowledge_base_id}/files
POST   /api/chat/sessions
GET    /api/chat/sessions
GET    /api/chat/sessions/{session_id}
POST   /api/chat
POST   /api/reviews
GET    /api/reviews/{review_session_id}
PATCH  /api/reviews/{review_session_id}/draft
POST   /api/reviews/{review_session_id}/submit
POST   /api/plans
GET    /api/plans/{plan_id}
PATCH  /api/plans/{plan_id}
GET    /api/progress
```

Specific route behavior:

1. `POST /api/knowledge-bases/{id}/files` accepts `files: list[UploadFile] = File(...)`, reads each file once, calls `ingest_file`, returns a list of independent `FileIngestResult` dictionaries, and continues after a per-file validation or embedding failure.
2. `POST /api/chat/sessions` creates a new session bound to the selected knowledge base. The frontend calls it whenever the selector changes.
3. `POST /api/chat` saves the user message, invokes `run_agent`, saves the assistant result and returns:

```json
{
  "session_id": "session-id",
  "task_type": "qa",
  "answer": "回答",
  "citations": [],
  "workspace_type": "",
  "workspace_id": "",
  "statistics": {}
}
```

4. `POST /api/reviews` converts the three counts through `validate_question_counts`, calls `generate_review`, and returns questions without exposing internal prompt text.
5. `PATCH /api/reviews/{id}/draft` saves answers only while the session is `draft`; `POST /submit` locks it and returns per-question results.
6. `POST /api/plans` returns `status="needs_input"` and missing fields when required plan information is absent; otherwise it creates a saved plan.
7. `GET /api/progress?knowledge_base_id=` supports either a selected knowledge base or all knowledge bases when the parameter is omitted.

Register an `AppError` handler that returns status `400` and `{"message": str(exc)}`. For unknown errors, return a generic message without stack traces, API keys or local paths.

- [ ] **Step 4: Implement the FastAPI application entry point**

Create `app/main.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import load_settings
from app.core.database import init_db


settings = load_settings()
init_db(settings.db_path)

app = FastAPI(title="个人学习资料问答与复习助手")
app.include_router(router)

web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(web_dir / "index.html")
```

The module must not call an external model during import. Running without `.env` must still allow `/health`; model-dependent endpoints return a readable configuration error.

- [ ] **Step 5: Build the native HTML workspace**

Create `web/index.html` with five navigation buttons or links and five view sections:

```text
聊天
知识库
复习
学习计划
学习进度
```

The chat view must show a knowledge-base selector with `无知识库`, a message list, a message input and send button. The knowledge-base view must show create/rename/delete controls, a multi-file input, per-file status rows, delete-file controls, clear-library control and current file list. The review view must contain separate numeric inputs for choice/judgment/short-answer counts, multi-file scope checkboxes, question controls and a unified submit button. The plan view must contain goal, deadline, daily minutes, file scope, generated Markdown editor and save button. The progress view must contain current/all knowledge-base selector and the required metrics.

Use stable `id` attributes that the JavaScript relies on:

```text
knowledge-base-select
chat-messages
chat-input
send-chat
knowledge-base-list
file-input
file-list
review-choice-count
review-judgment-count
review-short-count
review-form
plan-content
progress-scope
progress-metrics
```

The review and plan workspaces are separate sections with independent controls. Chat only displays a link or button to open the returned workspace ID; it does not embed the full answer form inside the chat message.

- [ ] **Step 6: Implement small fetch helpers and workspace behavior**

Create `web/app.js` with:

```javascript
const state = {
  knowledgeBaseId: null,
  sessionId: null,
  reviewSessionId: null,
  planId: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}
```

Implement these functions:

```javascript
async function loadKnowledgeBases() {}
async function createKnowledgeBase() {}
async function switchKnowledgeBase(knowledgeBaseId) {}
async function uploadFiles(fileList) {}
async function sendChat() {}
async function openReviewWorkspace(reviewSessionId) {}
async function submitReview() {}
async function generatePlan() {}
async function savePlan() {}
async function loadProgress() {}
```

Required behavior:

1. Switching the selector creates a new chat session and refreshes the file list.
2. Choosing `无知识库` creates a session with `knowledge_base_id=null` and permits ordinary chat.
3. Upload results render one status row per file; a failed file does not hide successful files.
4. Chat responses with `workspace_type="review"` or `"plan"` switch to the corresponding workspace and load it.
5. Review answers stay in the review form until unified submit; objective results show immediately after submission, and short-answer feedback displays `status="grading_failed"` clearly when applicable.
6. Plan content is editable Markdown text, saved through `PATCH /api/plans/{id}`.
7. Progress view only renders returned metrics and never invents plan completion statistics.

- [ ] **Step 7: Add readable, restrained CSS**

Create `web/styles.css` with a compact utility layout:

```css
:root {
  font-family: Arial, "Microsoft YaHei", sans-serif;
  color: #1f2933;
  background: #f5f7fa;
}

body {
  margin: 0;
}

button,
input,
textarea,
select {
  font: inherit;
}

.app-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  padding: 20px;
  background: #17202a;
  color: #ffffff;
}

.main-content {
  min-width: 0;
  padding: 24px;
}

.workspace {
  display: none;
  max-width: 1100px;
}

.workspace.active {
  display: block;
}

.message-list,
.file-list,
.question-list {
  display: grid;
  gap: 12px;
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
  }

  .main-content {
    padding: 16px;
  }
}
```

Keep sections full-width and functional. Use buttons with familiar symbols where a symbol is enough, but keep text labels for actions that would otherwise be ambiguous. Do not nest decorative cards or add marketing hero content.

- [ ] **Step 8: Add synthetic evaluation data and a no-network runner**

Create `eval/golden_questions.jsonl` using generic fixture fields, for example:

```json
{"id":"chat-001","mode":"chat","question":"你好","expected_task_type":"chat","requires_citation":false}
{"id":"qa-001","mode":"qa","question":"根据当前资料解释核心概念","expected_task_type":"qa","requires_citation":true}
{"id":"qa-002","mode":"strict","question":"只根据资料回答不存在的内容","expected_task_type":"qa","requires_refusal":true}
{"id":"review-001","mode":"review","question":"生成选择题和简答题","expected_task_type":"review","requires_workspace":true}
{"id":"plan-001","mode":"plan","question":"制定学习计划","expected_task_type":"plan","requires_workspace":true}
{"id":"stats-001","mode":"statistics","question":"统计答题情况","expected_task_type":"statistics","requires_statistics":true}
```

Create `eval/run_eval.py` that reads JSONL, invokes deterministic route functions and prints a summary table. It must not require an API key or make network calls:

```python
import json
from pathlib import Path

from app.agent.nodes import classify_task


def main() -> None:
    path = Path(__file__).with_name("golden_questions.jsonl")
    passed = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        total += 1
        actual = classify_task(case["question"], "kb-1")
        ok = actual == case["expected_task_type"]
        passed += int(ok)
        print(f"{case['id']}: {'PASS' if ok else 'FAIL'} actual={actual}")
    print(f"passed={passed}/{total}")


if __name__ == "__main__":
    main()
```

Keep the evaluation cases synthetic and small; do not copy files or questions from `agent-learning`.

- [ ] **Step 9: Complete README and GitHub security checks**

Create `README.md` with:

```markdown
# 个人学习资料问答与复习助手

## 功能

- 上传 txt/md 资料并维护多个独立知识库
- 普通聊天和带引用的资料问答
- 选择题、判断题、简答题复习与评分
- 学习计划编辑保存
- 基于真实答题记录的学习进度统计

## 启动

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 在 .env 中填写 DASHSCOPE_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。

## 数据和安全

应用只读取用户在页面上传的 txt/md 文件。运行时数据在 `data/`，API Key 在 `.env`，这些内容不会提交到 GitHub。删除应用中的文件不会删除电脑上的原文件。

## 架构

FastAPI → LangGraph 单主 Agent → chat/qa/review/plan/statistics；SQLite 保存业务记录，Chroma 按知识库持久化向量。
```

Before the final commit, run these checks:

```powershell
git status --short
git ls-files | Select-String -Pattern '(\.env$|app\.sqlite3|chroma|data/uploads|memory\.db)'
rg -n "DASHSCOPE_API_KEY|sk-[A-Za-z0-9]" --glob '!docs/**' --glob '!*.pyc' .
```

Expected:

- `git status --short` contains only intended source/docs files.
- `git ls-files` returns no `.env`, database, Chroma or uploaded-file path.
- `rg` finds only configuration names and README instructions, never a real secret.

- [ ] **Step 10: Run the complete verification suite**

Run:

```powershell
pytest -q
python eval/run_eval.py
python -m compileall app tests eval
```

Expected:

- All deterministic tests pass.
- Evaluation prints `passed=<total>/<total>`.
- `compileall` exits with status `0`.

For a manual smoke test with a configured key:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then verify:

1. Create two knowledge bases.
2. Upload the same filename with different content to both.
3. Delete one file and confirm its old content is no longer retrieved.
4. Switch to `无知识库` and send `你好`; inspect that no retrieval call appears in the debug log.
5. Generate a review with one, two and three selected question types.
6. Save a draft, submit it, inspect objective and short-answer results, then confirm a second submit is rejected.
7. Generate and edit a plan.
8. Open current/all progress and confirm only submitted review data is counted.

- [ ] **Step 11: Commit the complete MVP**

Run:

```powershell
git add app web eval tests README.md requirements.txt .env.example .gitignore pytest.ini
git commit -m "feat: deliver personal learning assistant mvp"
```

---

## Self-Review Before Execution

### Spec coverage

- User-uploaded UTF-8 `.txt` / `.md`, 10 MB limit, multi-file upload, independent failure: Task 2 and Task 7.
- Multiple persistent isolated knowledge bases, same-name overwrite, single-file/clear/full deletion: Task 1, Task 2 and Task 7.
- `无知识库`, chat/qa override and no fabricated citations: Task 3 and Task 4.
- One LangGraph main Agent with five task types: Task 4.
- Review question type combinations, online answer form, draft, objective grading, short-answer model grading, weak points: Task 5 and Task 7.
- Explicit preference Memory, plan missing-field follow-up, edit/save, no daily completion rate: Task 6 and Task 7.
- Current/all knowledge-base progress from submitted answers only: Task 6 and Task 7.
- Local-only binding, API-key isolation, no runtime import of `agent-learning`: Global Constraints, Task 1 and Task 7.
- Deterministic tests, synthetic evaluation, README and GitHub safety checks: Task 1, Task 3, Task 4 and Task 7.

### Placeholder scan

No production file may contain `TODO`, `TBD`, `pass` as the implementation body, or a fake success response for an unconfigured model.

### Type consistency

- `knowledge_base_id` is `str | None` at chat/session boundaries and `str` for RAG, review, plan and progress operations that require a selected knowledge base.
- `file_ids` is always `list[str] | None`; an empty list means all ready files in the selected knowledge base.
- `review_questions.question_type` uses `"choice"`, `"judgment"` or `"short_answer"` in every layer.
- `review_answers.score` is a `float` from `0.0` to `100.0`.
- `workspace_type` uses `"review"` or `"plan"` and `workspace_id` contains the corresponding SQLite record ID.
- Retrieval citations are always derived from actual result dictionaries and use `source`, `chunk_id`, `file_id` and `score`.

Plan complete and saved to `docs/superpowers/plans/2026-09-11-personal-learning-assistant.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task and review between tasks.
2. **Inline Execution** - execute the tasks in this session with checkpoints.

Choose one execution approach before implementation begins.
