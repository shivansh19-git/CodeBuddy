from app.embeddings.router import EmbeddingRouter
from app.rag.chunker import CodeChunk
from app.rag.retriever import HybridRetriever


def test_hybrid_retriever_falls_back_to_lexical_ranking_without_embedding_api():
    chunks = [
        CodeChunk(
            "invoice.py", "total_invoice", "function", 1, 2, "def total_invoice(items): pass"
        ),
        CodeChunk("users.py", "create_user", "function", 1, 2, "def create_user(name): pass"),
    ]
    result = HybridRetriever(EmbeddingRouter()).retrieve("fix invoice total", chunks)
    assert result[0].symbol == "total_invoice"
