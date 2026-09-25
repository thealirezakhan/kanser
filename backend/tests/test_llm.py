import json

import httpx
import pytest

from app.llm import GroqClient, LocalLLM, RateLimited


def test_local_llm_no_network():
    out = LocalLLM().complete("role: radiology analyze")
    data = json.loads(out)
    assert "hypothesis" in data
    assert 0 <= data["confidence"] <= 1


def test_groq_rate_limited_raises():
    client = GroqClient(api_key="test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimited):
        client.complete("prompt")


def test_groq_success_returns_content():
    client = GroqClient(api_key="test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"]
        assert body["messages"][0]["content"] == "hello"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": 1}'}}]}
        )

    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.complete("hello") == '{"ok": 1}'
