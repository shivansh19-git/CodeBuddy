"""Hybrid lexical + semantic retrieval with an honest lexical-only fallback."""

import re
from pathlib import Path

from app.embeddings.providers import EmbeddingRequestError
from app.embeddings.router import EmbeddingRouter, NoEmbeddingProviderError
from app.rag.chunker import CodeChunk
from app.rag.vector_store import FaissVectorStore


def lexical_score(query: str, chunk: CodeChunk) -> float:
    words = set(re.findall(r"[a-zA-Z_]{3,}", query.lower()))
    text = f"{chunk.file} {chunk.symbol} {chunk.source}".lower()
    return float(sum(word in text for word in words))


class HybridRetriever:
    """Combine code-name matching with semantic similarity when API vectors exist."""

    def __init__(self, embedding_router: EmbeddingRouter, vector_store_root: Path | None = None):
        self.embedding_router = embedding_router
        self.vector_store_root = vector_store_root

    def retrieve(self, query: str, chunks: list[CodeChunk], limit: int = 8) -> list[CodeChunk]:
        """Return lexical results if embedding API/index is unavailable.

        Semantic vectors are intentionally not mixed between providers: the
        selected provider is the only one used in each scoring operation.
        """
        try:
            provider = self.embedding_router.select()
            vectors = provider.embed_documents([chunk.source for chunk in chunks])
            query_vector = provider.embed_query(query)
            if len(vectors) != len(chunks):
                raise ValueError("Embedding provider returned the wrong vector count.")
            if self.vector_store_root:
                # Each provider/model receives a completely separate FAISS
                # namespace; cached vectors can never be mixed accidentally.
                store = FaissVectorStore(
                    self.vector_store_root,
                    provider.descriptor.name,
                    provider.descriptor.model,
                )
                store.save(chunks, vectors)
                semantic = {
                    chunk.identifier: limit - rank + 1
                    for rank, chunk in enumerate(store.search(query_vector, limit), 1)
                }
                return sorted(
                    chunks,
                    key=lambda chunk: (
                        semantic.get(chunk.identifier, 0),
                        lexical_score(query, chunk),
                    ),
                    reverse=True,
                )[:limit]
            scores = [
                lexical_score(query, chunk) + self._cosine(query_vector, vector)
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        except (EmbeddingRequestError, NoEmbeddingProviderError, OSError, ValueError):
            scores = [lexical_score(query, chunk) for chunk in chunks]
        return [
            chunk
            for _, chunk in sorted(
                zip(scores, chunks, strict=True), key=lambda item: item[0], reverse=True
            )[:limit]
        ]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            raise ValueError("Embedding vectors must have matching non-zero dimensions.")
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = sum(value * value for value in left) ** 0.5
        right_norm = sum(value * value for value in right) ** 0.5
        if not left_norm or not right_norm:
            raise ValueError("Embedding vectors cannot have zero magnitude.")
        return numerator / (left_norm * right_norm)
