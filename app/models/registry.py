"""Single place where configured provider adapters are registered."""

from app.config import settings
from app.models.providers import HuggingFaceProvider, MistralProvider
from app.models.router import ModelRouter


def build_model_router() -> ModelRouter:
    providers = []
    if settings.mistral_api_key:
        provider = MistralProvider(api_key=settings.mistral_api_key, model=settings.mistral_model)
        providers.append(provider.with_availability(provider.health_check()))
    if settings.huggingface_api_key:
        provider = HuggingFaceProvider(
            api_key=settings.huggingface_api_key,
            model=settings.huggingface_model,
        )
        providers.append(provider.with_availability(provider.health_check()))
    return ModelRouter(providers=providers)
