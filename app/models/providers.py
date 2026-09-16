"""HTTP adapters for the supported chat-completion providers."""

from dataclasses import replace

import httpx

from app.models.base import LLMProvider, ModelCapabilities, ModelDescriptor


class ProviderRequestError(RuntimeError):
    """Raised when a provider rejects a request or returns an invalid response."""


class ProviderRateLimitError(ProviderRequestError):
    """Raised when a provider rejects a request due to rate limits (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderQuotaExhaustedError(ProviderRequestError):
    """Raised when a provider quota or credit balance is exhausted (HTTP 402/403)."""


class ChatCompletionProvider(LLMProvider):
    """Adapter for providers exposing an OpenAI-compatible chat API."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        priority: int,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=120.0)
        self._owns_client = client is None
        self.descriptor = ModelDescriptor(
            provider=provider,
            model=model,
            priority=priority,
            capabilities=ModelCapabilities(
                coding=True,
                tools=True,
                structured_output=True,
            ),
            availability="unknown",
        )

    def with_availability(self, availability: str) -> "ChatCompletionProvider":
        self.descriptor = replace(self.descriptor, availability=availability)
        return self

    def generate(self, prompt: str, *, max_tokens: int = 4096) -> str:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.descriptor.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
            },
        )
        self._raise_for_provider_error(response)
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderRequestError(
                f"Provider returned an invalid chat response: {self._response_detail(response)}"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise ProviderRequestError("Provider returned an empty chat response.")
        return content

    def health_check(self) -> str:
        try:
            response = self._client.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            self._raise_for_provider_error(response)
        except ProviderRateLimitError:
            return "rate_limited"
        except ProviderQuotaExhaustedError:
            return "quota_exhausted"
        except (httpx.HTTPError, ProviderRequestError):
            return "unavailable"
        return "healthy"

    @staticmethod
    def _raise_for_provider_error(response: httpx.Response) -> None:
        if response.status_code == 429:
            retry_after = None
            if "retry-after" in response.headers:
                try:
                    retry_after = float(response.headers["retry-after"])
                except ValueError:
                    pass
            raise ProviderRateLimitError(
                f"Provider rate limit exceeded (HTTP 429).", retry_after=retry_after
            )
        if response.status_code == 402 or (
            response.status_code == 403
            and any(term in response.text.lower() for term in ("quota", "credit", "billing", "balance"))
        ):
            raise ProviderQuotaExhaustedError(
                f"Provider quota or credit limit exhausted (HTTP {response.status_code})."
            )
        if response.is_error:
            detail = ChatCompletionProvider._response_detail(response)
            raise ProviderRequestError(
                f"Provider request failed with HTTP {response.status_code}: {detail}"
            )

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        """Return a bounded response detail without exposing request credentials."""
        detail = response.text.strip().replace("\n", " ")
        return detail[:300] or "empty response body"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class HuggingFaceProvider(ChatCompletionProvider):
    """Hugging Face Inference Providers adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        priority: int = 20,
        client: httpx.Client | None = None,
    ):
        super().__init__(
            provider="huggingface",
            api_key=api_key,
            model=model,
            base_url="https://router.huggingface.co/v1",
            priority=priority,
            client=client,
        )


class MistralProvider(ChatCompletionProvider):
    """Mistral AI chat-completions adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        priority: int = 10,
        client: httpx.Client | None = None,
    ):
        super().__init__(
            provider="mistral",
            api_key=api_key,
            model=model,
            base_url="https://api.mistral.ai/v1",
            priority=priority,
            client=client,
        )


class GroqProvider(ChatCompletionProvider):
    """Groq API chat-completions adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        priority: int = 5,
        client: httpx.Client | None = None,
    ):
        super().__init__(
            provider="groq",
            api_key=api_key,
            model=model,
            base_url="https://api.groq.com/openai/v1",
            priority=priority,
            client=client,
        )


class GeminiProvider(ChatCompletionProvider):
    """Google Gemini API chat-completions adapter using OpenAI compatibility layer."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        priority: int = 1,
        client: httpx.Client | None = None,
    ):
        super().__init__(
            provider="gemini",
            api_key=api_key,
            model=model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            priority=priority,
            client=client,
        )
