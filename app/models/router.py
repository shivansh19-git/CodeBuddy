"""Capability-aware model selection with deterministic fallback order."""

from app.models.base import LLMProvider


class NoCompatibleProviderError(RuntimeError):
    """Raised when no configured provider can safely handle an operation."""


class ModelRouter:
    """Select one stable model per logical operation, not per tiny step."""

    def __init__(self, providers: list[LLMProvider] | None = None):
        self.providers = providers or []

    def select(
        self,
        *,
        task_type: str,
        requires_tools: bool = False,
        requires_structured_output: bool = False,
    ) -> LLMProvider:
        """Return the highest-priority healthy adapter meeting all requirements."""
        candidates = self.compatible(
            task_type=task_type,
            requires_tools=requires_tools,
            requires_structured_output=requires_structured_output,
        )
        if not candidates:
            raise NoCompatibleProviderError("No healthy, compatible model provider is configured.")
        return candidates[0]

    def compatible(
        self,
        *,
        task_type: str,
        requires_tools: bool = False,
        requires_structured_output: bool = False,
    ) -> list[LLMProvider]:
        """List compatible providers in fallback order, without calling them."""
        candidates = []
        for provider in self.providers:
            data = provider.descriptor
            capable = (
                data.capabilities.coding
                if task_type in {"coding", "debugging", "test_generation"}
                else True
            )
            if (
                data.enabled
                and data.availability == "healthy"
                and capable
                and (not requires_tools or data.capabilities.tools)
                and (not requires_structured_output or data.capabilities.structured_output)
            ):
                candidates.append(provider)
        return sorted(candidates, key=lambda provider: provider.descriptor.priority)

    def status(self) -> list[dict[str, object]]:
        """Return display-safe metadata for the UI; keys are never stored here."""
        return [
            {
                "name": p.descriptor.provider,
                "model": p.descriptor.model,
                "status": p.descriptor.availability,
                "capabilities": [
                    name
                    for name, supported in {
                        "coding": p.descriptor.capabilities.coding,
                        "tools": p.descriptor.capabilities.tools,
                        "structured output": p.descriptor.capabilities.structured_output,
                    }.items()
                    if supported
                ],
            }
            for p in self.providers
        ]
