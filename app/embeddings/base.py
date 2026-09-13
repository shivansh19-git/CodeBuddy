"""Provider-neutral embedding contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingDescriptor:
    name: str
    model: str
    priority: int
    availability: str = "unknown"


class EmbeddingProvider(ABC):
    descriptor: EmbeddingDescriptor

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed source chunks in one compatible vector space."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a query with the same model used for its index."""

    @abstractmethod
    def health_check(self) -> str:
        """Return an honest API availability state."""
