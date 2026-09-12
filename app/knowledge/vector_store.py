try:
    from langchain_chroma import Chroma
except ImportError:  # The dependency is only needed for the real vector path.
    Chroma = None

from app.knowledge.embeddings import DashScopeEmbeddingAdapter


def collection_name(knowledge_base_id: str) -> str:
    return f"kb_{knowledge_base_id.replace('-', '')}"


class CompatibleChromaStore:
    """Adapt langchain_chroma.Chroma to the project's upsert-style API."""

    def __init__(self, store):
        self._store = store

    def upsert(self, ids, documents, metadatas, embeddings=None):
        ids = list(ids)
        if not ids:
            return
        # Overwrite by deleting first, then adding with the same IDs.
        try:
            self._store.delete(ids=ids)
        except Exception:
            # Collection may be empty on first write.
            pass
        kwargs = {
            "texts": list(documents),
            "metadatas": list(metadatas),
            "ids": ids,
        }
        if embeddings is not None:
            kwargs["embeddings"] = list(embeddings)
        self._store.add_texts(**kwargs)

    def delete(self, ids):
        ids = list(ids or [])
        if not ids:
            return
        self._store.delete(ids=ids)

    def get(self, ids=None, include=None):
        kwargs = {}
        if ids is not None:
            kwargs["ids"] = list(ids)
        if include is not None:
            kwargs["include"] = include
        return self._store.get(**kwargs)

    def delete_collection(self):
        return self._store.delete_collection()

    def similarity_search_with_relevance_scores(self, query, k=4, filter=None):
        kwargs = {"k": k}
        if filter is not None:
            kwargs["filter"] = filter
        return self._store.similarity_search_with_relevance_scores(query, **kwargs)

    def __getattr__(self, name):
        return getattr(self._store, name)


def get_vector_store(knowledge_base_id: str, settings, embedding_function=None):
    if Chroma is None:
        raise RuntimeError("未安装 langchain-chroma，无法使用 Chroma")
    embedding = embedding_function or DashScopeEmbeddingAdapter(
        model=settings.embedding_model,
        api_key=settings.api_key,
        dimension=settings.embedding_dimension,
    )
    store = Chroma(
        collection_name=collection_name(knowledge_base_id),
        persist_directory=str(settings.chroma_dir),
        embedding_function=embedding,
        collection_metadata={"hnsw:space": "cosine"},
    )
    return CompatibleChromaStore(store)
