from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


QuestionType = Literal["choice", "judgment", "short_answer"]


def _validate_question_fields(value: dict) -> None:
    question_type = value.get("question_type")
    if question_type == "choice":
        options = value.get("options") or []
        if len(options) != 4:
            raise ValueError("选择题必须包含恰好四个选项")
    elif question_type == "judgment":
        if value.get("correct_answer", "").strip() not in {"正确", "错误"}:
            raise ValueError("判断题正确答案必须为正确或错误")
    elif question_type == "short_answer":
        if not str(value.get("rubric", "")).strip():
            raise ValueError("简答题评分标准不能为空")


try:
    from pydantic import BaseModel, Field
except ImportError:  # Keep deterministic review tests usable without pydantic.
    @dataclass
    class GeneratedOption:
        label: str
        text: str

        def __post_init__(self):
            if not isinstance(self.label, str) or not 1 <= len(self.label) <= 4:
                raise ValueError("选项标签长度必须在 1 到 4 个字符之间")
            if not isinstance(self.text, str) or not 1 <= len(self.text) <= 500:
                raise ValueError("选项文本长度必须在 1 到 500 个字符之间")

    @dataclass
    class GeneratedQuestion:
        question_type: QuestionType
        prompt: str
        correct_answer: str
        reference_answer: str
        rubric: str
        knowledge_point: str
        options: list[GeneratedOption] = field(default_factory=list)
        source_chunk_ids: list[str] = field(default_factory=list)

        def __post_init__(self):
            if self.question_type not in {"choice", "judgment", "short_answer"}:
                raise ValueError("题型不受支持")
            if not isinstance(self.prompt, str) or not 1 <= len(self.prompt) <= 2000:
                raise ValueError("题目内容长度必须在 1 到 2000 个字符之间")
            self.options = [
                option if isinstance(option, GeneratedOption) else GeneratedOption(**option)
                for option in self.options
            ]
            _validate_question_fields(self.__dict__)

        def model_dump(self) -> dict:
            return {
                "question_type": self.question_type,
                "prompt": self.prompt,
                "options": [option.__dict__.copy() for option in self.options],
                "correct_answer": self.correct_answer,
                "reference_answer": self.reference_answer,
                "rubric": self.rubric,
                "knowledge_point": self.knowledge_point,
                "source_chunk_ids": list(self.source_chunk_ids),
            }
else:
    class GeneratedOption(BaseModel):
        label: str = Field(min_length=1, max_length=4)
        text: str = Field(min_length=1, max_length=500)

    class GeneratedQuestion(BaseModel):
        question_type: QuestionType
        prompt: str = Field(min_length=1, max_length=2000)
        options: list[GeneratedOption] = Field(default_factory=list)
        correct_answer: str
        reference_answer: str
        rubric: str
        knowledge_point: str
        source_chunk_ids: list[str] = Field(default_factory=list)

        def __init__(self, **data):
            super().__init__(**data)
            _validate_question_fields(self.model_dump() if hasattr(self, "model_dump") else self.dict())


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
    if any(not isinstance(count, int) or isinstance(count, bool) for count in counts.values()):
        raise ValueError("题目数量必须为整数")
    if any(count < 0 for count in counts.values()):
        raise ValueError("题目数量不能为负数")
    if sum(counts.values()) == 0:
        raise ValueError("至少选择一种题型")
    return counts
