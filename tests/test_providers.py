import httpx

from app.models.providers import HuggingFaceProvider, MistralProvider


def test_huggingface_generate_uses_router_chat_endpoint():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "patched"}}]},
            request=request,
        )

    provider = HuggingFaceProvider(
        api_key="hf-test-key",
        model="Qwen/test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.generate("Fix the test") == "patched"
    assert requests[0].url == "https://router.huggingface.co/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer hf-test-key"
    assert requests[0].read().decode() == (
        '{"model":"Qwen/test","messages":[{"role":"user","content":"Fix the test"}],'
        '"response_format":{"type":"json_object"}}'
    )


def test_mistral_health_check_reports_unavailable_on_api_error():
    def handler(request: httpx.Request):
        return httpx.Response(401, request=request)

    provider = MistralProvider(
        api_key="mistral-test-key",
        model="codestral-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.health_check() == "unavailable"


def test_provider_handles_rate_limit_and_quota_errors():
    import pytest
    from app.models.providers import ProviderQuotaExhaustedError, ProviderRateLimitError

    def rate_limit_handler(request: httpx.Request):
        return httpx.Response(429, headers={"retry-after": "5"}, request=request)

    def quota_handler(request: httpx.Request):
        return httpx.Response(402, text="Insufficient credit balance", request=request)

    rl_provider = MistralProvider(
        api_key="key",
        model="m",
        client=httpx.Client(transport=httpx.MockTransport(rate_limit_handler)),
    )
    assert rl_provider.health_check() == "rate_limited"
    with pytest.raises(ProviderRateLimitError) as exc_info:
        rl_provider.generate("test")
    assert exc_info.value.retry_after == 5.0

    quota_provider = MistralProvider(
        api_key="key",
        model="m",
        client=httpx.Client(transport=httpx.MockTransport(quota_handler)),
    )
    assert quota_provider.health_check() == "quota_exhausted"
    with pytest.raises(ProviderQuotaExhaustedError):
        quota_provider.generate("test")


def test_provider_reports_invalid_response_detail():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="upstream unavailable", request=request)

    provider = MistralProvider(
        api_key="key",
        model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    import pytest
    from app.models.providers import ProviderRequestError

    with pytest.raises(ProviderRequestError, match="upstream unavailable"):
        provider.generate("test")
