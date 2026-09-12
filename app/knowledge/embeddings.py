from http import HTTPStatus
from typing import Sequence

try:
    import dashscope
except ImportError:  # Optional until the real embedding path is used.
    dashscope = None


class DashScopeEmbeddingAdapter:
    def __init__(self, model: str, api_key: str, dimension: int | None = None) -> None:
        if dashscope is None:
            raise RuntimeError("未安装 dashscope，无法使用 DashScope embedding")
        self.model = model
        self.dimension = dimension
        dashscope.api_key = api_key

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = dashscope.TextEmbedding.call(model=self.model, input=list(texts))
        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(f"Embedding 失败：{response.code} {response.message}")
        embeddings = sorted(
            response.output["embeddings"], key=lambda item: item["text_index"]
        )
        vectors = [item["embedding"] for item in embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding 返回数量与输入文本数量不一致")
        if self.dimension and any(len(vector) != self.dimension for vector in vectors):
            raise RuntimeError("Embedding 返回维度与 EMBEDDING_DIMENSION 不一致")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
