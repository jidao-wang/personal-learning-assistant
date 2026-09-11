from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import register_error_handlers, router
from app.core.config import Settings, load_settings
from app.core.database import init_db


@dataclass
class AppRuntime:
    settings: Settings
    db_path: Path
    embedding_function: object | None = None
    vector_store: object | None = None
    llm_client: object | None = None
    compiled_graph: object | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    init_db(settings.db_path)
    application = FastAPI(title="个人学习资料问答与复习助手")
    application.state.runtime = AppRuntime(settings=settings, db_path=settings.db_path)
    application.include_router(router)
    register_error_handlers(application)

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        application.mount("/static", StaticFiles(directory=web_dir), name="static")

        @application.get("/", include_in_schema=False)
        def index():
            return FileResponse(web_dir / "index.html")

    return application


app = create_app()
