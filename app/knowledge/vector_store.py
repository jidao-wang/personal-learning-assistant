try:
    from langchain_chroma import Chroma
except ImportError:  # The dependency is only needed for the real vector path.
    Chroma = None

from app.knowledge.embeddings import DashScopeEmbeddingAdapter


def collection_name(knowledge_base_id: str) -> str:
    return f"kb_{knowledge_base_id.replace('-', '')}"


def get_vector_store(knowledge_base_id: str, settings, embedding_function=None):
    if Chroma is None:
        raise RuntimeError("未安装 langchain-chroma，无法使用 Chroma")
    embedding = embedding_function or DashScopeEmbeddingAdapter(
        model=settings.embedding_model,
        api_key=settings.api_key,
        dimension=settings.embedding_dimension,
    )
    return Chroma(
        collection_name=collection_name(knowledge_base_id),
        persist_directory=str(settings.chroma_dir),
        embedding_function=embedding,
        collection_metadata={"hnsw:space": "cosine"},
    )
