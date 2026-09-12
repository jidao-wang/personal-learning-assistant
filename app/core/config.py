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
