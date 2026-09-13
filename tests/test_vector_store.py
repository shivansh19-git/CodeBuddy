from app.rag.vector_store import FaissVectorStore, index_namespace


def test_embedding_model_namespaces_are_isolated(tmp_path):
    assert index_namespace("provider", "model/a") != index_namespace("provider", "model-b")
    first = FaissVectorStore(tmp_path, "provider", "model/a")
    second = FaissVectorStore(tmp_path, "provider", "model-b")
    assert first.directory != second.directory
