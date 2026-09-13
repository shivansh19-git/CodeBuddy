"""Generic HTTP embedding adapter for a configured API endpoint."""

from dataclasses import replace

import httpx

from app.embeddings.base import EmbeddingDescriptor, EmbeddingProvider


class EmbeddingRequestError(RuntimeError):
    """An embedding provider did not return usable vectors."""


class HttpEmbeddingProvider(EmbeddingProvider):
    """Provider adapter for endpoints accepting `{"inputs": [...]}` JSON.

    The URL is configuration rather than a hard-coded free-tier promise: API
    offerings and model availability change frequently.
    """

    def __init__(self, *, name: str, model: str, api_key: str, url: str, priority: int):
        self._api_key = api_key
        self._url = url
        self._client = httpx.Client(timeout=30.0)
        self.descriptor = EmbeddingDescriptor(name=name, model=model, priority=priority)

    def with_availability(self, availability: str) -> "HttpEmbeddingProvider":
        self.descriptor = replace(self.descriptor, availability=availability)
        return self

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        result = self._post(texts)
        if (
            not isinstance(result, list)
            or not result
            or not all(isinstance(row, list) for row in result)
        ):
            raise EmbeddingRequestError(
                "Embedding API returned an invalid document-vector response."
            )
        return [[float(value) for value in row] for row in result]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def health_check(self) -> str:
        try:
            self._post(["health check"])
        except (httpx.HTTPError, EmbeddingRequestError):
            return "unavailable"
        return "healthy"

    def _post(self, inputs: list[str]):
        response = self._client.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"inputs": inputs},
        )
        if response.is_error:
            raise EmbeddingRequestError(
                f"Embedding request failed with HTTP {response.status_code}."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise EmbeddingRequestError("Embedding API returned invalid JSON.") from exc
