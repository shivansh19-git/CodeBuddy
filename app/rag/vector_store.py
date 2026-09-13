"""FAISS-backed vector indexes, isolated by provider and model namespace."""

import hashlib
import json
import re
from pathlib import Path

import faiss
import numpy as np

from app.rag.chunker import CodeChunk


def index_namespace(provider: str, model: str) -> str:
    """Create a filesystem-safe namespace; never mix vector-model spaces."""
    safe_provider = re.sub(r"[^a-zA-Z0-9_.-]", "_", provider)
    safe_model = re.sub(r"[^a-zA-Z0-9_.-]", "_", model)
    return f"{safe_provider}__{safe_model}"


class FaissVectorStore:
    """Persist one cosine-similarity FAISS index for exactly one embedding model."""

    def __init__(self, root: Path, provider: str, model: str):
        self.directory = root / index_namespace(provider, model)
        self.index_path = self.directory / "index.faiss"
        self.metadata_path = self.directory / "chunks.json"

    def save(self, chunks: list[CodeChunk], vectors: list[list[float]]) -> None:
        """Build a normalized inner-product index and save matching metadata."""
        if len(chunks) != len(vectors) or not vectors:
            raise ValueError("Every chunk requires exactly one non-empty vector.")
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise ValueError("Vectors must be a non-empty two-dimensional matrix.")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        self.directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self.index_path))
        self.metadata_path.write_text(
            json.dumps([chunk.__dict__ for chunk in chunks]), encoding="utf-8"
        )

    def search(self, query_vector: list[float], limit: int = 8) -> list[CodeChunk]:
        """Search only this provider/model namespace and return semantic chunks."""
        index = faiss.read_index(str(self.index_path))
        query = np.asarray([query_vector], dtype="float32")
        if query.shape[1] != index.d:
            raise ValueError("Query vector dimension does not match this embedding index.")
        faiss.normalize_L2(query)
        _scores, ids = index.search(query, min(limit, index.ntotal))
        raw_chunks = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        return [CodeChunk(**raw_chunks[item]) for item in ids[0] if item >= 0]

    def content_hash(self, chunks: list[CodeChunk]) -> str:
        """Expose a stable input hash for future incremental-index caching."""
        payload = "\n".join(f"{chunk.identifier}\n{chunk.source}" for chunk in chunks)
        return hashlib.sha256(payload.encode()).hexdigest()
