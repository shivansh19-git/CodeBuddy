"""Build embedding providers from environment configuration."""

from app.config import settings
from app.embeddings.providers import HttpEmbeddingProvider
from app.embeddings.router import EmbeddingRouter


def build_embedding_router() -> EmbeddingRouter:
    providers = []
    if (
        settings.embedding_provider_primary == "huggingface"
        and settings.huggingface_embedding_api_key
        and settings.huggingface_embedding_url
    ):
        provider = HttpEmbeddingProvider(
            name="huggingface",
            model=settings.huggingface_embedding_model or "configured-endpoint",
            api_key=settings.huggingface_embedding_api_key,
            url=settings.huggingface_embedding_url,
            priority=10,
        )
        providers.append(provider.with_availability(provider.health_check()))
    return EmbeddingRouter(providers)
