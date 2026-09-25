import os

import pytest


@pytest.fixture(autouse=True)
def _default_auth_disabled():
    # existing tests predate auth; modules that test auth flip this off
    os.environ.setdefault("DISABLE_AUTH", "1")
    yield


@pytest.fixture(autouse=True)
def _isolate_llm(monkeypatch):
    # repo .env may carry a real key; tests must never hit a live LLM
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.limits import diagnose_limiter, global_limiter

    global_limiter.reset()
    diagnose_limiter.reset()
    yield
    global_limiter.reset()
    diagnose_limiter.reset()
