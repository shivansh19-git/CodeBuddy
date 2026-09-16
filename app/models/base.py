"""Interfaces that every LLM provider adapter must satisfy.

The rest of the application talks to this contract, never directly to a
vendor SDK. That is what makes provider fallback possible.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    """Facts used by the router; availability is observed, never guessed."""

    coding: bool
    tools: bool = False
    structured_output: bool = False
    context_limit: int | None = None


@dataclass(frozen=True)
class ModelDescriptor:
    """Configuration and live status for one selectable model."""

    provider: str
    model: str
    priority: int
    capabilities: ModelCapabilities
    enabled: bool = True
    availability: str = "unknown"  # healthy, rate_limited, unavailable, unknown


class LLMProvider(ABC):
    """A provider adapter must implement real generation and health checking."""

    descriptor: ModelDescriptor

    @abstractmethod
    def generate(self, prompt: str, *, max_tokens: int = 4096) -> str:
        """Generate text. Implementations must raise on provider failure."""

    @abstractmethod
    def health_check(self) -> str:
        """Return an honest availability string; never expose credentials."""
