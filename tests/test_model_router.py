from app.models.base import LLMProvider, ModelCapabilities, ModelDescriptor
from app.models.router import ModelRouter


class Provider(LLMProvider):
    def __init__(self, name: str, priority: int):
        self.descriptor = ModelDescriptor(
            name,
            "model",
            priority,
            ModelCapabilities(coding=True, tools=True, structured_output=True),
            availability="healthy",
        )

    def generate(self, prompt: str) -> str:
        return prompt

    def health_check(self) -> str:
        return "healthy"


def test_router_returns_providers_in_priority_fallback_order():
    router = ModelRouter([Provider("fallback", 20), Provider("primary", 10)])
    assert [provider.descriptor.provider for provider in router.compatible(task_type="coding")] == [
        "primary",
        "fallback",
    ]
