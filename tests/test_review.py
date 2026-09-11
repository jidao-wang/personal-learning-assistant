import sqlite3
import threading

import pytest

from app.core.errors import NotFoundError
from app.review.grader import grade_choice, grade_judgment, grade_short_answer
from app.review.generator import generate_questions
from app.review.schemas import GeneratedQuestion, validate_question_counts
from app.storage.review_store import (
    create_review_session,
    get_review_session,
    list_review_questions,
    mark_review_submitted,
    save_review_draft,
    save_weak_point,
)


def make_document(text, chunk_id, file_id="file-1", source="lesson.md"):
    return type(
        "Document",
        (),
        {
            "page_content": text,
            "metadata": {
                "source": source,
                "title": source.rsplit(".", 1)[0],
                "chunk_id": chunk_id,
                "file_id": file_id,
                "knowledge_base_id": "kb-1",
            },
        },
    )()


class FakeVectorStoreWithContext:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or [
            (
                make_document("Agent 可以根据任务调用工具。", "file-1:0"),
                0.9,
            )
        ]

    def similarity_search_with_relevance_scores(self, query, k, filter=None):
        self.calls.append((query, k, filter))
        return self.results


class FakeReviewLLM:
    def chat_json(self, messages):
        if "评分器" in messages[0]["content"]:
            return {
                "score": 80,
                "feedback": "覆盖了主要概念，但缺少一个关键条件。",
                "citations": [
                    {"source": "lesson.md", "chunk_id": "file-1:0"},
                    {"source": "fake.md", "chunk_id": "fake:0"},
                ],
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


def make_question(question_type="choice", **overrides):
    value = {
        "question_type": question_type,
        "prompt": "Agent 的核心能力是什么？",
        "options": [
            {"label": "A", "text": "调用工具"},
            {"label": "B", "text": "只输出固定文本"},
            {"label": "C", "text": "删除资料"},
            {"label": "D", "text": "关闭程序"},
        ] if question_type == "choice" else [],
        "correct_answer": "A" if question_type == "choice" else "正确",
        "reference_answer": "A" if question_type == "choice" else "参考答案",
        "rubric": "选择正确选项" if question_type == "choice" else "必须说明关键条件",
        "knowledge_point": "Agent",
        "source_chunk_ids": ["file-1:0"],
    }
    value.update(overrides)
    return value


def make_review_settings(tmp_path, db_path):
    from app.core.config import Settings

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


def seed_file_chunk(
    knowledge_base_id,
    db_path,
    file_id="file-1",
    filename="lesson.md",
    vector_id="file-1:1",
    content="目标来源内容",
):
    from app.storage.knowledge_base_store import replace_chunk_records, upsert_file

    timestamp = "2026-01-01T00:00:00"
    upsert_file(
        {
            "id": file_id,
            "knowledge_base_id": knowledge_base_id,
            "original_name": filename,
            "stored_path": "unused.source",
            "extension": ".md",
            "size_bytes": len(content.encode("utf-8")),
            "content_hash": "hash",
            "status": "ready",
            "error_message": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        db_path,
    )
    replace_chunk_records(
        file_id,
        [
            {
                "id": f"record-{vector_id}",
                "knowledge_base_id": knowledge_base_id,
                "file_id": file_id,
                "chunk_index": 1,
                "vector_id": vector_id,
                "content_hash": "hash",
                "content": content,
                "created_at": timestamp,
            }
        ],
        db_path,
    )


def seed_file_chunks(knowledge_base_id, db_path, file_id="file-1"):
    from app.storage.knowledge_base_store import replace_chunk_records, upsert_file

    timestamp = "2026-01-01T00:00:00"
    upsert_file(
        {
            "id": file_id,
            "knowledge_base_id": knowledge_base_id,
            "original_name": "lesson.md",
            "stored_path": "unused.source",
            "extension": ".md",
            "size_bytes": 8,
            "content_hash": "hash",
            "status": "ready",
            "error_message": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        db_path,
    )
    replace_chunk_records(
        file_id,
        [
            {
                "id": f"record-{file_id}:0",
                "knowledge_base_id": knowledge_base_id,
                "file_id": file_id,
                "chunk_index": 0,
                "vector_id": f"{file_id}:0",
                "content_hash": "hash",
                "content": "第一个来源片段",
                "created_at": timestamp,
            },
            {
                "id": f"record-{file_id}:1",
                "knowledge_base_id": knowledge_base_id,
                "file_id": file_id,
                "chunk_index": 1,
                "vector_id": f"{file_id}:1",
                "content_hash": "hash",
                "content": "第二个来源片段",
                "created_at": timestamp,
            },
        ],
        db_path,
    )


def test_user_can_choose_one_two_or_three_question_types():
    assert validate_question_counts(5, 0, 0) == {"choice": 5, "judgment": 0, "short_answer": 0}
    assert validate_question_counts(2, 3, 0) == {"choice": 2, "judgment": 3, "short_answer": 0}
    assert validate_question_counts(2, 2, 1) == {"choice": 2, "judgment": 2, "short_answer": 1}


def test_at_least_one_question_is_required():
    with pytest.raises(ValueError, match="至少选择一种题型"):
        validate_question_counts(0, 0, 0)


def test_negative_question_count_is_rejected():
    with pytest.raises(ValueError, match="不能为负数"):
        validate_question_counts(-1, 1, 0)


def test_objective_questions_are_scored_without_llm():
    assert grade_choice("A", "A") == (100.0, "回答正确")
    assert grade_choice("B", "A") == (0.0, "回答错误")
    assert grade_judgment("正确", "正确") == (100.0, "回答正确")
    assert grade_judgment("错", "正确") == (0.0, "回答错误")


def test_question_validation_enforces_type_specific_fields():
    with pytest.raises(ValueError):
        GeneratedQuestion(**make_question(options=[]))
    with pytest.raises(ValueError):
        GeneratedQuestion(**make_question("judgment", correct_answer="可能"))
    with pytest.raises(ValueError):
        GeneratedQuestion(**make_question("short_answer", rubric=""))


@pytest.mark.parametrize(
    ("options", "correct_answer"),
    [
        (
            [
                {"label": "A", "text": "一"},
                {"label": "A", "text": "二"},
                {"label": "C", "text": "三"},
                {"label": "D", "text": "四"},
            ],
            "A",
        ),
        (
            [
                {"label": "A", "text": "一"},
                {"label": "B", "text": "二"},
                {"label": "C", "text": "三"},
                {"label": "E", "text": "四"},
            ],
            "A",
        ),
        (
            [
                {"label": "A", "text": "一"},
                {"label": "B", "text": "二"},
                {"label": "C", "text": "三"},
                {"label": "D", "text": "四"},
            ],
            "E",
        ),
    ],
)
def test_choice_validation_requires_canonical_labels_and_known_answer(
    options, correct_answer
):
    with pytest.raises(ValueError):
        GeneratedQuestion(
            **make_question(options=options, correct_answer=correct_answer)
        )


def test_short_answer_rubric_none_is_rejected():
    with pytest.raises(ValueError, match="评分标准不能为空"):
        GeneratedQuestion(**make_question("short_answer", rubric=None))


def test_generate_questions_rejects_model_count_mismatch():
    with pytest.raises(ValueError, match="题目数量与请求不一致"):
        generate_questions(
            [{"source": "lesson.md", "chunk_id": "file-1:0", "text": "资料"}],
            {"choice": 2, "judgment": 0, "short_answer": 0},
            FakeReviewLLM(),
        )


def test_generate_questions_rejects_fabricated_source_chunk_id():
    class FakeWithFabricatedSource(FakeReviewLLM):
        def chat_json(self, messages):
            result = super().chat_json(messages)
            result["questions"][0]["source_chunk_ids"] = ["attacker:99"]
            return result

    with pytest.raises(ValueError, match="来源"):
        generate_questions(
            [{"source": "lesson.md", "chunk_id": "file-1:0", "text": "资料"}],
            {"choice": 1, "judgment": 0, "short_answer": 0},
            FakeWithFabricatedSource(),
        )


def test_short_answer_grading_intersects_model_citations_with_context():
    result = grade_short_answer(
        make_question("short_answer"),
        "Agent 可以调用工具。",
        "[来源: lesson.md#file-1:0]\nAgent 可以根据任务调用工具。",
        FakeReviewLLM(),
        supplied_citations=[{"source": "lesson.md", "chunk_id": "file-1:0"}],
    )
    assert result["score"] == 80.0
    assert result["status"] == "graded"
    assert result["citations"] == [{"source": "lesson.md", "chunk_id": "file-1:0"}]


def test_short_answer_grading_keeps_answer_when_model_fails():
    class BrokenLLM:
        def chat_json(self, messages):
            raise RuntimeError("模型暂时不可用")

    result = grade_short_answer(
        make_question("short_answer"),
        "我的答案",
        "资料",
        BrokenLLM(),
        supplied_citations=[],
    )
    assert result["status"] == "grading_failed"
    assert result["answer_text"] == "我的答案"
    assert "模型暂时不可用" in result["feedback"]


def test_review_store_persists_questions_and_allows_only_valid_drafts(db_path):
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base_id = create_knowledge_base("存储测试", db_path)["id"]
    review = create_review_session(knowledge_base_id, {"file_ids": []}, [make_question()], db_path)
    assert get_review_session(review["id"], db_path)["status"] == "draft"
    questions = list_review_questions(review["id"], db_path)
    assert len(questions) == 1
    question_id = questions[0]["id"]

    answers = save_review_draft(
        review["id"], [{"question_id": question_id, "answer_text": "A"}], db_path
    )
    assert answers[0]["answer_text"] == "A"
    with pytest.raises(ValueError, match="题目不存在"):
        save_review_draft(review["id"], [{"question_id": "missing", "answer_text": "A"}], db_path)


def test_review_store_locks_submitted_session_and_accumulates_weak_points(db_path):
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("锁定测试", db_path)
    review = create_review_session(knowledge_base["id"], {"file_ids": []}, [make_question()], db_path)
    mark_review_submitted(review["id"], 50.0, db_path)
    assert get_review_session(review["id"], db_path)["status"] == "submitted"
    with pytest.raises(ValueError, match="已经提交"):
        save_review_draft(review["id"], [], db_path)

    seed_file_chunks(knowledge_base["id"], db_path)
    first = save_weak_point(knowledge_base["id"], "Agent", ["file-1:0"], db_path)
    second = save_weak_point(knowledge_base["id"], "Agent", ["file-1:1"], db_path)
    assert first["occurrence_count"] == 1
    assert second["occurrence_count"] == 2
    assert second["source_chunk_ids"] == ["file-1:0", "file-1:1"]


def test_weak_point_sources_must_belong_to_the_knowledge_base(db_path):
    from app.storage.knowledge_base_store import create_knowledge_base

    first = create_knowledge_base("弱点边界一", db_path)
    second = create_knowledge_base("弱点边界二", db_path)
    seed_file_chunk(first["id"], db_path)

    with pytest.raises(ValueError, match="来源"):
        save_weak_point(first["id"], "Agent", ["missing:0"], db_path)
    with pytest.raises(ValueError, match="来源"):
        save_weak_point(second["id"], "Agent", ["file-1:1"], db_path)
    with pytest.raises(NotFoundError, match="知识库不存在"):
        save_weak_point("missing-kb", "Agent", [], db_path)


def test_create_review_session_does_not_mislabel_other_integrity_errors(db_path):
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("复习错误映射", db_path)
    with pytest.raises(sqlite3.IntegrityError):
        create_review_session(
            knowledge_base["id"],
            {"file_ids": []},
            [make_question(prompt=None)],
            db_path,
        )


def test_generate_review_can_create_one_question_type(db_path, tmp_path):
    from app.core.config import Settings
    from app.review.service import REVIEW_QUERY, generate_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("复习测试", db_path)
    settings = Settings(
        api_key="test", base_url="https://example.test/v1", chat_model="chat",
        embedding_model="embedding", embedding_dimension=None, timeout_seconds=1,
        temperature=0, chunk_size=20, chunk_overlap=3, top_k=3, score_threshold=0,
        max_file_size=10 * 1024 * 1024, data_dir=tmp_path, upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma", db_path=db_path, host="127.0.0.1", port=8000,
    )
    vector_store = FakeVectorStoreWithContext()
    result = generate_review(
        knowledge_base["id"],
        ["file-1"],
        {"choice": 1, "judgment": 0, "short_answer": 0},
        settings,
        FakeReviewLLM(),
        db_path,
        vector_store,
    )
    assert result["review_session_id"]
    assert len(result["questions"]) == 1
    assert result["scope"] == {"file_ids": ["file-1"]}
    assert vector_store.calls == [
        (REVIEW_QUERY, settings.top_k, {"file_id": {"$in": ["file-1"]}})
    ]


def test_short_answer_with_source_ids_uses_exact_chunks_instead_of_top_k(
    db_path, tmp_path
):
    from app.review.service import submit_review
    from app.storage.knowledge_base_store import create_knowledge_base

    class CapturingLLM:
        def __init__(self):
            self.messages = []

        def chat_json(self, messages):
            self.messages.append(messages)
            return {
                "score": 80,
                "feedback": "回答基本正确",
                "citations": [{"source": "lesson.md", "chunk_id": "file-1:1"}],
            }

    knowledge_base = create_knowledge_base("精确来源测试", db_path)
    seed_file_chunk(knowledge_base["id"], db_path, content="目标来源内容")
    question = make_question(
        "short_answer",
        prompt="请解释目标来源",
        source_chunk_ids=["file-1:1"],
    )
    review = create_review_session(
        knowledge_base["id"], {"file_ids": ["file-1"]}, [question], db_path
    )
    save_review_draft(
        review["id"],
        [{"question_id": review["questions"][0]["id"], "answer_text": "我的答案"}],
        db_path,
    )
    vector_store = FakeVectorStoreWithContext(
        [(make_document("语义检索干扰", "file-1:0"), 0.99)]
    )
    llm = CapturingLLM()

    result = submit_review(
        review["id"],
        make_review_settings(tmp_path, db_path),
        llm,
        db_path,
        vector_store,
    )

    grading_prompt = llm.messages[0][1]["content"]
    assert "目标来源内容" in grading_prompt
    assert "语义检索干扰" not in grading_prompt
    assert vector_store.calls == []
    assert result["answers"][0]["citations"][0]["chunk_id"] == "file-1:1"


def test_short_answer_without_source_ids_uses_scoped_semantic_retrieval(
    db_path, tmp_path
):
    from app.review.service import submit_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("语义来源测试", db_path)
    question = make_question(
        "short_answer",
        prompt="请解释 Agent",
        source_chunk_ids=[],
    )
    review = create_review_session(
        knowledge_base["id"], {"file_ids": ["file-1"]}, [question], db_path
    )
    save_review_draft(
        review["id"],
        [{"question_id": review["questions"][0]["id"], "answer_text": "我的答案"}],
        db_path,
    )
    vector_store = FakeVectorStoreWithContext()

    submit_review(
        review["id"],
        make_review_settings(tmp_path, db_path),
        FakeReviewLLM(),
        db_path,
        vector_store,
    )

    assert vector_store.calls == [
        (question["prompt"], 3, {"file_id": {"$in": ["file-1"]}})
    ]


def test_submission_claim_is_atomic_and_can_be_released(db_path):
    from app.review.service import save_draft
    from app.storage.knowledge_base_store import create_knowledge_base
    from app.storage.review_store import (
        claim_review_submission,
        release_review_submission,
    )

    knowledge_base = create_knowledge_base("提交 claim 测试", db_path)
    review = create_review_session(
        knowledge_base["id"], {"file_ids": []}, [make_question()], db_path
    )
    save_draft(
        review["id"],
        [{"question_id": review["questions"][0]["id"], "answer_text": "B"}],
        db_path,
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def claim():
        barrier.wait()
        outcomes.append(claim_review_submission(review["id"], db_path))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == [False, True]
    assert get_review_session(review["id"], db_path)["status"] == "submitting"
    release_review_submission(review["id"], db_path)
    assert get_review_session(review["id"], db_path)["status"] == "draft"


def test_draft_write_cannot_cross_submission_claim(monkeypatch, db_path):
    from app.storage import review_store
    from app.storage.knowledge_base_store import create_knowledge_base
    from app.storage.review_store import claim_review_submission, list_review_answers

    knowledge_base = create_knowledge_base("草稿锁定竞态", db_path)
    review = create_review_session(
        knowledge_base["id"], {"file_ids": []}, [make_question()], db_path
    )
    question_id = review["questions"][0]["id"]
    save_review_draft(
        review["id"], [{"question_id": question_id, "answer_text": "A"}], db_path
    )

    saver_ident = None
    entered_write_window = threading.Event()
    release_write_window = threading.Event()
    original_now = review_store._now

    def blocking_now():
        if threading.get_ident() == saver_ident:
            entered_write_window.set()
            if not release_write_window.wait(timeout=5):
                raise AssertionError("未释放草稿写入窗口")
        return original_now()

    monkeypatch.setattr(review_store, "_now", blocking_now)
    outcome = []

    def save_late_answer():
        nonlocal saver_ident
        saver_ident = threading.get_ident()
        try:
            save_review_draft(
                review["id"],
                [{"question_id": question_id, "answer_text": "B"}],
                db_path,
            )
        except Exception as exc:
            outcome.append(exc)
        else:
            outcome.append(None)

    thread = threading.Thread(target=save_late_answer)
    thread.start()
    assert entered_write_window.wait(timeout=5)
    assert claim_review_submission(review["id"], db_path) is True
    release_write_window.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], ValueError)
    assert list_review_answers(review["id"], db_path)[0]["answer_text"] == "A"


def test_submit_review_scores_objective_answers_and_locks_session(db_path, tmp_path):
    from app.core.config import Settings
    from app.review.service import submit_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("客观评分测试", db_path)
    review = create_review_session(knowledge_base["id"], {"file_ids": []}, [make_question()], db_path)
    question_id = review["questions"][0]["id"]
    save_review_draft(review["id"], [{"question_id": question_id, "answer_text": "A"}], db_path)
    settings = Settings(
        api_key="test", base_url="https://example.test/v1", chat_model="chat",
        embedding_model="embedding", embedding_dimension=None, timeout_seconds=1,
        temperature=0, chunk_size=20, chunk_overlap=3, top_k=3, score_threshold=0,
        max_file_size=10 * 1024 * 1024, data_dir=tmp_path, upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma", db_path=db_path, host="127.0.0.1", port=8000,
    )
    result = submit_review(
        review["id"], settings, FakeReviewLLM(), db_path, FakeVectorStoreWithContext()
    )
    assert result["total_score"] == 100.0
    assert result["status"] == "submitted"
    with pytest.raises(ValueError, match="已经提交"):
        submit_review(review["id"], settings, FakeReviewLLM(), db_path, FakeVectorStoreWithContext())


def test_submit_review_records_unanswered_question_as_zero_and_weak_point(db_path, tmp_path):
    from app.core.config import Settings
    from app.review.service import submit_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("缺答测试", db_path)
    seed_file_chunk(knowledge_base["id"], db_path, vector_id="file-1:0")
    review = create_review_session(knowledge_base["id"], {"file_ids": []}, [make_question()], db_path)
    settings = Settings(
        api_key="test", base_url="https://example.test/v1", chat_model="chat",
        embedding_model="embedding", embedding_dimension=None, timeout_seconds=1,
        temperature=0, chunk_size=20, chunk_overlap=3, top_k=3, score_threshold=0,
        max_file_size=10 * 1024 * 1024, data_dir=tmp_path, upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma", db_path=db_path, host="127.0.0.1", port=8000,
    )
    result = submit_review(review["id"], settings, FakeReviewLLM(), db_path, FakeVectorStoreWithContext())
    assert result["total_score"] == 0.0
    assert result["answers"][0]["status"] == "unanswered"
    assert result["answers"][0]["answer_text"] == ""


def test_normalize_raw_question_accepts_common_llm_aliases():
    from app.review.generator import _normalize_raw_question
    from app.review.schemas import GeneratedQuestion

    normalized = _normalize_raw_question(
        {
            "type": "choice",
            "description": "常用标准库里哪个用于 JSON？",
            "options": {"A": "os", "B": "json", "C": "re", "D": "datetime"},
            "answer": "B",
            "explanation": "json 模块负责编解码",
            "topic": "标准库",
            "chunk_ids": ["c1"],
        }
    )
    question = GeneratedQuestion(**normalized)
    assert question.question_type == "choice"
    assert question.prompt.startswith("常用标准库")
    assert [option.label for option in question.options] == ["A", "B", "C", "D"]
    assert question.correct_answer == "B"


def test_generate_questions_retries_then_succeeds():
    class FlakyLLM(FakeReviewLLM):
        def __init__(self):
            self.calls = 0

        def chat_json(self, messages):
            self.calls += 1
            if self.calls == 1:
                return super().chat_json(messages)  # only 1 question
            q = super().chat_json(messages)["questions"][0]
            q2 = dict(q)
            q2["prompt"] = "第二题：" + q["prompt"]
            return {"questions": [q, q2]}

    llm = FlakyLLM()
    questions = generate_questions(
        [{"source": "lesson.md", "chunk_id": "file-1:0", "text": "资料"}],
        {"choice": 2, "judgment": 0, "short_answer": 0},
        llm,
        max_attempts=3,
    )
    assert len(questions) == 2
    assert llm.calls == 2


def test_generate_questions_accepts_extra_questions_and_trims():
    class ExtraLLM(FakeReviewLLM):
        def chat_json(self, messages):
            q = super().chat_json(messages)["questions"][0]
            q2 = dict(q)
            q2["prompt"] = "额外题"
            return {"questions": [q, q2]}

    questions = generate_questions(
        [{"source": "lesson.md", "chunk_id": "file-1:0", "text": "资料"}],
        {"choice": 1, "judgment": 0, "short_answer": 0},
        ExtraLLM(),
    )
    assert len(questions) == 1
