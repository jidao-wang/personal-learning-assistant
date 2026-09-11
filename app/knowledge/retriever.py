from app.knowledge.vector_store import get_vector_store


def retrieve(
    knowledge_base_id: str,
    query: str,
    file_ids: list[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
    settings=None,
    vector_store=None,
) -> list[dict]:
    store = vector_store if vector_store is not None else get_vector_store(knowledge_base_id, settings)
    k = settings.top_k if top_k is None else top_k
    threshold = settings.score_threshold if score_threshold is None else score_threshold
    kwargs = {"k": k}
    if file_ids:
        kwargs["filter"] = {"file_id": {"$in": file_ids}}

    matches = store.similarity_search_with_relevance_scores(query, **kwargs)
    results = []
    for document, score in matches:
        if score < threshold:
            continue
        metadata = document.metadata
        results.append(
            {
                "text": document.page_content,
                "source": metadata.get("source", ""),
                "title": metadata.get("title", ""),
                "chunk_id": metadata.get("chunk_id", ""),
                "file_id": metadata.get("file_id", ""),
                "knowledge_base_id": knowledge_base_id,
                "score": float(score),
            }
        )
    return results


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
