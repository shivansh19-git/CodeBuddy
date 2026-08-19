"""Single place where configured provider adapters are registered.

It currently returns no adapters deliberately. Add a real adapter here after
placing its credentials in environment variables—not in source control.
"""

from app.models.router import ModelRouter


def build_model_router() -> ModelRouter:
    return ModelRouter(providers=[])
