"""Embedding routing remains separate from the coding-model router."""

from app.embeddings.base import EmbeddingProvider


class NoEmbeddingProviderError(RuntimeError):
    """No healthy embedding API is available for semantic retrieval."""


class EmbeddingRouter:
    def __init__(self, providers: list[EmbeddingProvider] | None = None):
        self.providers = providers or []

    def select(self) -> EmbeddingProvider:
        healthy = [p for p in self.providers if p.descriptor.availability == "healthy"]
        if not healthy:
            raise NoEmbeddingProviderError("No healthy embedding provider is configured.")
        return min(healthy, key=lambda p: p.descriptor.priority)
