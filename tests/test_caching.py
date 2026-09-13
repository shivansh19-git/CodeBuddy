import pytest
from pathlib import Path

from app.rag.cache import IndexCache, compute_content_hash
from app.schemas import Symbol


def test_compute_content_hash():
    h1 = compute_content_hash("def foo(): pass\n")
    h2 = compute_content_hash("def foo(): pass\n")
    h3 = compute_content_hash("def bar(): pass\n")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_index_cache_roundtrip(tmp_path: Path):
    cache_file = tmp_path / "cache.json"
    cache = IndexCache(cache_file)

    symbols = [
        Symbol(
            file="math.py",
            name="add",
            kind="function",
            start_line=1,
            end_line=2,
            signature="(a, b)",
            docstring="Add two numbers",
        )
    ]
    content_hash = compute_content_hash("def add(a, b):\n    return a + b\n")
    cache.set_symbols(content_hash, symbols)
    cache.set_embedding("test_prov", "chunk_123", [0.1, 0.2, 0.3])
    cache.save()

    # Verify persisted cache can be reloaded
    reloaded_cache = IndexCache(cache_file)
    cached_symbols = reloaded_cache.get_symbols(content_hash)
    assert cached_symbols is not None
    assert len(cached_symbols) == 1
    assert cached_symbols[0].name == "add"
    assert cached_symbols[0].signature == "(a, b)"

    vector = reloaded_cache.get_embedding("test_prov", "chunk_123")
    assert vector == [0.1, 0.2, 0.3]
    assert reloaded_cache.get_embedding("test_prov", "non_existent") is None
