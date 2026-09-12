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
