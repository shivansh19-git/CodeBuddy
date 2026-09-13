"""Incremental caching for AST parsing and embedding vector computation."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas import Symbol


def compute_content_hash(text: str | bytes) -> str:
    """Return the SHA-256 hex digest for given text/bytes."""
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


class IndexCache:
    """In-memory and file-backed cache for AST symbols and chunk embeddings."""

    def __init__(self, cache_file: Path | None = None):
        self.cache_file = cache_file
        self.ast_cache: dict[str, list[dict[str, Any]]] = {}
        self.embedding_cache: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file and self.cache_file.is_file():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                self.ast_cache = data.get("ast", {})
                self.embedding_cache = data.get("embeddings", {})
            except Exception:
                pass

    def save(self) -> None:
        if self.cache_file:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                payload = {
                    "ast": self.ast_cache,
                    "embeddings": self.embedding_cache,
                }
                self.cache_file.write_text(json.dumps(payload), encoding="utf-8")
            except Exception:
                pass

    def get_symbols(self, content_hash: str) -> list[Symbol] | None:
        raw_list = self.ast_cache.get(content_hash)
        if raw_list is None:
            return None
        return [Symbol.model_validate(item) for item in raw_list]

    def set_symbols(self, content_hash: str, symbols: list[Symbol]) -> None:
        self.ast_cache[content_hash] = [s.model_dump() for s in symbols]

    def get_embedding(self, provider_key: str, chunk_hash: str) -> list[float] | None:
        key = f"{provider_key}:{chunk_hash}"
        return self.embedding_cache.get(key)

    def set_embedding(self, provider_key: str, chunk_hash: str, vector: list[float]) -> None:
        key = f"{provider_key}:{chunk_hash}"
        self.embedding_cache[key] = vector
