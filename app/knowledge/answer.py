from dataclasses import dataclass
from enum import Enum

from app.knowledge.retriever import format_citations, format_context, retrieve


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


def answer_question(
    query,
    knowledge_base_id,
    policy,
    settings,
    llm_client,
    file_ids=None,
    vector_store=None,
):
    policy = AnswerPolicy(policy)
    results = retrieve(
        knowledge_base_id,
        query,
        file_ids=file_ids,
        settings=settings,
        vector_store=vector_store,
    )
    if not results and policy == AnswerPolicy.STRICT:
        return build_answer_result("", results, policy)

    if results:
        context = format_context(results)
        messages = [
            {
                "role": "system",
                "content": "只依据提供的资料回答问题；资料不足时明确说明资料不足，不要编造资料中的事实或引用。",
            },
            {
                "role": "user",
                "content": f"资料上下文:\n{context}\n\n问题：{query}",
            },
        ]
    else:
        messages = [
            {
                "role": "user",
                "content": f"请使用你的通用知识回答以下问题：\n{query}",
            }
        ]

    answer = llm_client.chat(messages)
    return build_answer_result(answer, results, policy)
