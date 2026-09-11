import pytest

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

    first = save_weak_point(knowledge_base["id"], "Agent", ["file-1:0"], db_path)
    second = save_weak_point(knowledge_base["id"], "Agent", ["file-1:1"], db_path)
    assert first["occurrence_count"] == 1
    assert second["occurrence_count"] == 2
    assert second["source_chunk_ids"] == ["file-1:0", "file-1:1"]


def test_generate_review_can_create_one_question_type(db_path, tmp_path):
    from app.core.config import Settings
    from app.review.service import generate_review
    from app.storage.knowledge_base_store import create_knowledge_base

    knowledge_base = create_knowledge_base("复习测试", db_path)
    settings = Settings(
        api_key="test", base_url="https://example.test/v1", chat_model="chat",
        embedding_model="embedding", embedding_dimension=None, timeout_seconds=1,
        temperature=0, chunk_size=20, chunk_overlap=3, top_k=3, score_threshold=0,
        max_file_size=10 * 1024 * 1024, data_dir=tmp_path, upload_dir=tmp_path / "uploads",
        chroma_dir=tmp_path / "chroma", db_path=db_path, host="127.0.0.1", port=8000,
    )
    result = generate_review(
        knowledge_base["id"], None, {"choice": 1, "judgment": 0, "short_answer": 0},
        settings, FakeReviewLLM(), db_path, FakeVectorStoreWithContext(),
    )
    assert result["review_session_id"]
    assert len(result["questions"]) == 1
    assert result["scope"] == {"file_ids": []}


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
