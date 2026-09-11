from __future__ import annotations

from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.agent.graph import run_agent
from app.api.schemas import (
    ChatRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRenameRequest,
    PlanCreateRequest,
    PlanUpdateRequest,
    ReviewCreateRequest,
    ReviewDraftRequest,
    SessionCreateRequest,
)
from app.core.config import load_settings
from app.core.errors import AppError, ConfigurationError
from app.core.llm_client import LLMClient
from app.knowledge.ingest import (
    FileIngestResult,
    clear_knowledge_base,
    delete_file,
    delete_knowledge_base,
    ingest_file,
)
from app.plan.service import generate_plan, missing_plan_fields
from app.progress.service import get_progress
from app.review.schemas import validate_question_counts
from app.review.service import (
    generate_review,
    save_draft,
    submit_review,
)
from app.storage.chat_store import (
    add_message,
    create_session,
    get_session,
    list_messages,
    list_sessions,
)
from app.storage.knowledge_base_store import (
    create_knowledge_base,
    delete_knowledge_base as delete_knowledge_base_record,
    get_knowledge_base,
    get_file,
    list_files,
    list_knowledge_bases,
    rename_knowledge_base,
)
from app.storage.plan_store import get_plan, update_plan
from app.storage.review_store import (
    get_review_session,
    list_review_answers,
    list_review_questions,
)


router = APIRouter()


def _runtime(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        return runtime
    settings = load_settings()
    return SimpleNamespace(
        settings=settings,
        db_path=settings.db_path,
        embedding_function=None,
        vector_store=None,
        llm_client=None,
        compiled_graph=None,
    )


def _llm_client(runtime):
    if runtime.llm_client is not None:
        return runtime.llm_client
    if not runtime.settings.api_key.strip():
        raise ConfigurationError("请先在 .env 中配置 DASHSCOPE_API_KEY")
    return LLMClient(runtime.settings)


def _public_question(question: dict) -> dict:
    return {
        key: question[key]
        for key in ("id", "question_type", "prompt", "options", "knowledge_point")
        if key in question
    }


def _public_review(review_session_id: str, db_path) -> dict:
    session = get_review_session(review_session_id, db_path)
    questions = list_review_questions(review_session_id, db_path)
    return {
        **session,
        "questions": [_public_question(question) for question in questions],
        "answers": list_review_answers(review_session_id, db_path),
    }


def _as_ingest_dict(result: FileIngestResult | dict) -> dict:
    if is_dataclass(result):
        return asdict(result)
    if hasattr(result, "__dict__"):
        return vars(result).copy()
    return dict(result)


@router.get("/health")
@router.get("/api/health")
def health(request: Request) -> dict:
    """Liveness plus lightweight dependency/config signals for the UI banner."""
    runtime = _runtime(request)
    openai_installed = False
    try:
        import openai  # noqa: F401

        openai_installed = True
    except ImportError:
        openai_installed = False

    api_key_configured = bool(str(getattr(runtime.settings, "api_key", "") or "").strip())
    warnings: list[str] = []
    if not api_key_configured:
        warnings.append("未配置 DASHSCOPE_API_KEY（请在 .env 中填写）")
    if not openai_installed:
        warnings.append("未安装 openai 包（请执行：pip install openai）")
    return {
        "status": "OK",
        "openai_installed": openai_installed,
        "api_key_configured": api_key_configured,
        "llm_ready": openai_installed and api_key_configured,
        "warnings": warnings,
    }


@router.get("/api/knowledge-bases")
def knowledge_bases(request: Request):
    return list_knowledge_bases(_runtime(request).db_path)


@router.post("/api/knowledge-bases")
def create_knowledge_base_route(payload: KnowledgeBaseCreateRequest, request: Request):
    return create_knowledge_base(payload.name, _runtime(request).db_path)


@router.patch("/api/knowledge-bases/{knowledge_base_id}")
def rename_knowledge_base_route(
    knowledge_base_id: str,
    payload: KnowledgeBaseRenameRequest,
    request: Request,
):
    return rename_knowledge_base(knowledge_base_id, payload.name, _runtime(request).db_path)


@router.delete("/api/knowledge-bases/{knowledge_base_id}", status_code=204)
def delete_knowledge_base_route(knowledge_base_id: str, request: Request):
    runtime = _runtime(request)
    delete_knowledge_base(
        knowledge_base_id,
        runtime.settings,
        db_path=runtime.db_path,
        vector_store=runtime.vector_store,
    )
    return Response(status_code=204)


@router.get("/api/knowledge-bases/{knowledge_base_id}/files")
def knowledge_base_files(knowledge_base_id: str, request: Request):
    runtime = _runtime(request)
    get_knowledge_base(knowledge_base_id, runtime.db_path)
    return list_files(knowledge_base_id, runtime.db_path)


@router.post("/api/knowledge-bases/{knowledge_base_id}/files")
async def upload_knowledge_base_files(
    knowledge_base_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
):
    runtime = _runtime(request)
    get_knowledge_base(knowledge_base_id, runtime.db_path)
    results = []
    for upload in files:
        filename = upload.filename or ""
        try:
            content = await upload.read()
            result = ingest_file(
                knowledge_base_id,
                filename,
                content,
                runtime.settings,
                db_path=runtime.db_path,
                embedding_function=runtime.embedding_function,
                vector_store=runtime.vector_store,
            )
        except Exception as exc:
            result = FileIngestResult(
                file_id=None,
                filename=filename,
                status="failed",
                error_message=str(exc),
            )
        finally:
            await upload.close()
        results.append(_as_ingest_dict(result))
    return results


@router.delete("/api/knowledge-bases/{knowledge_base_id}/files/{file_id}", status_code=204)
def delete_knowledge_base_file(knowledge_base_id: str, file_id: str, request: Request):
    runtime = _runtime(request)
    delete_file(
        knowledge_base_id,
        file_id,
        runtime.settings,
        db_path=runtime.db_path,
        vector_store=runtime.vector_store,
    )
    return Response(status_code=204)


@router.delete("/api/knowledge-bases/{knowledge_base_id}/files", status_code=204)
def clear_knowledge_base_files(knowledge_base_id: str, request: Request):
    runtime = _runtime(request)
    clear_knowledge_base(
        knowledge_base_id,
        runtime.settings,
        db_path=runtime.db_path,
        vector_store=runtime.vector_store,
    )
    return Response(status_code=204)


@router.post("/api/chat/sessions")
def create_chat_session(payload: SessionCreateRequest, request: Request):
    return create_session(payload.knowledge_base_id, _runtime(request).db_path)


@router.get("/api/chat/sessions")
def chat_sessions(request: Request):
    return list_sessions(_runtime(request).db_path)


@router.get("/api/chat/sessions/{session_id}")
def chat_session(session_id: str, request: Request):
    db_path = _runtime(request).db_path
    return {**get_session(session_id, db_path), "messages": list_messages(session_id, db_path)}


@router.post("/api/chat")
def chat(payload: ChatRequest, request: Request):
    runtime = _runtime(request)
    db_path = runtime.db_path
    session_id = payload.session_id
    knowledge_base_id = payload.knowledge_base_id
    if session_id:
        session = get_session(session_id, db_path)
        if knowledge_base_id is not None and knowledge_base_id != session["knowledge_base_id"]:
            raise AppError("会话与知识库不匹配")
        knowledge_base_id = session["knowledge_base_id"]
    else:
        session = create_session(knowledge_base_id, db_path)
        session_id = session["id"]

    request_options: dict[str, Any] = {}
    if payload.review is not None:
        request_options["review"] = payload.review
    if payload.plan is not None:
        request_options["plan"] = payload.plan
    request_options["_db_path"] = db_path
    try:
        result = run_agent(
            payload.message,
            session_id,
            knowledge_base_id=knowledge_base_id,
            request_options=request_options,
            db_path=db_path,
            settings=runtime.settings,
            llm_client=runtime.llm_client,
            vector_store=runtime.vector_store,
            compiled_graph=runtime.compiled_graph,
        )
    except Exception:
        add_message(session_id, "user", payload.message, "chat", db_path=db_path)
        raise
    normalized = {
        "session_id": session_id,
        "task_type": result.get("task_type", "chat"),
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "workspace_type": result.get("workspace_type", ""),
        "workspace_id": result.get("workspace_id", ""),
        "statistics": result.get("statistics", {}),
    }
    add_message(session_id, "user", payload.message, "chat", db_path=db_path)
    add_message(
        session_id,
        "assistant",
        normalized["answer"],
        normalized["task_type"],
        citations=normalized["citations"],
        db_path=db_path,
    )
    return normalized


@router.post("/api/reviews")
def create_review(payload: ReviewCreateRequest, request: Request):
    runtime = _runtime(request)
    try:
        counts = validate_question_counts(
            payload.choice_count,
            payload.judgment_count,
            payload.short_answer_count,
        )
    except ValueError as exc:
        raise AppError(str(exc)) from exc
    try:
        result = generate_review(
            payload.knowledge_base_id,
            payload.file_ids,
            counts,
            runtime.settings,
            _llm_client(runtime),
            db_path=runtime.db_path,
            vector_store=runtime.vector_store,
        )
    except ValueError as exc:
        raise AppError(str(exc)) from exc
    return {
        **result,
        "questions": [_public_question(question) for question in result.get("questions", [])],
    }


@router.get("/api/reviews/{review_session_id}")
def get_review(review_session_id: str, request: Request):
    return _public_review(review_session_id, _runtime(request).db_path)


@router.patch("/api/reviews/{review_session_id}/draft")
def save_review_draft_route(
    review_session_id: str,
    payload: ReviewDraftRequest,
    request: Request,
):
    db_path = _runtime(request).db_path
    session = get_review_session(review_session_id, db_path)
    if session["status"] != "draft":
        raise AppError("复习已经提交，不能修改答案")
    answers = save_draft(review_session_id, payload.answers, db_path)
    return {"review_session_id": review_session_id, "status": "draft", "answers": answers}


@router.post("/api/reviews/{review_session_id}/submit")
def submit_review_route(review_session_id: str, request: Request):
    runtime = _runtime(request)
    return submit_review(
        review_session_id,
        runtime.settings,
        _llm_client(runtime),
        db_path=runtime.db_path,
        vector_store=runtime.vector_store,
    )


@router.post("/api/plans")
def create_learning_plan(payload: PlanCreateRequest, request: Request):
    runtime = _runtime(request)
    plan_input = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    missing = missing_plan_fields(plan_input)
    if missing:
        return {"status": "needs_input", "missing_fields": missing}
    try:
        return generate_plan(
            payload.knowledge_base_id,
            payload.file_ids,
            plan_input,
            runtime.settings,
            _llm_client(runtime),
            db_path=runtime.db_path,
            vector_store=runtime.vector_store,
        )
    except ValueError as exc:
        raise AppError(str(exc)) from exc


@router.get("/api/plans/{plan_id}")
def get_learning_plan(plan_id: str, request: Request):
    return get_plan(plan_id, _runtime(request).db_path)


@router.patch("/api/plans/{plan_id}")
def update_learning_plan(plan_id: str, payload: PlanUpdateRequest, request: Request):
    return update_plan(plan_id, payload.content, _runtime(request).db_path)


@router.get("/api/progress")
def progress(request: Request, knowledge_base_id: str | None = None):
    return get_progress(
        knowledge_base_id=knowledge_base_id,
        db_path=_runtime(request).db_path,
    )


def register_error_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=400, content={"message": str(exc)})

    @app.exception_handler(Exception)
    async def unknown_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"message": "服务暂时不可用，请稍后重试。"},
        )
