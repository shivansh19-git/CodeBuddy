"""Single place where configured provider adapters are registered."""

from app.config import Settings, settings
from app.models.providers import GeminiProvider, GroqProvider, HuggingFaceProvider, MistralProvider
from app.models.router import ModelRouter


def build_model_router(cfg: Settings | None = None) -> ModelRouter:
    """Build a ModelRouter from the given Settings (defaults to the global singleton).

    Pass a freshly constructed Settings() to pick up changes made to .env
    after the server started. The health-check for each configured provider
    is performed inside this function so callers always get current status.
    """
    if cfg is None:
        cfg = settings
    providers = []
    if cfg.mistral_api_key:
        provider = MistralProvider(api_key=cfg.mistral_api_key, model=cfg.mistral_model)
        providers.append(provider.with_availability(provider.health_check()))
    if cfg.huggingface_api_key:
        provider = HuggingFaceProvider(
            api_key=cfg.huggingface_api_key,
            model=cfg.huggingface_model,
        )
        providers.append(provider.with_availability(provider.health_check()))
    if cfg.groq_api_key:
        provider = GroqProvider(
            api_key=cfg.groq_api_key,
            model=cfg.groq_model,
        )
        providers.append(provider.with_availability(provider.health_check()))
    if cfg.gemini_api_key:
        provider = GeminiProvider(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
        )
        providers.append(provider.with_availability(provider.health_check()))
    return ModelRouter(providers=providers)


def reload_model_router() -> ModelRouter:
    """Re-read .env from disk and rebuild the ModelRouter from scratch.

    This allows model names or API keys changed in .env to take effect
    immediately without restarting the server.
    """
    from app.config import reload_settings
    fresh_cfg = reload_settings()
    return build_model_router(fresh_cfg)
