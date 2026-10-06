import os

import pytest


@pytest.fixture(autouse=True)
def _default_auth_disabled(monkeypatch):
    # existing tests predate auth; modules that test auth flip this off
    os.environ.setdefault("DISABLE_AUTH", "1")
    # .env ships a known-default secret that startup refuses; tests use a strong one
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "0123456789abcdef" * 2)
    yield


@pytest.fixture(autouse=True)
def _isolate_llm(monkeypatch):
    # repo .env may carry a real key; tests must never hit a live LLM
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_db_by_default(monkeypatch):
    # hermetic by default; opt in with KANSER_TEST_DB=1 (see test_postgres.py)
    if os.environ.get("KANSER_TEST_DB") != "1":
        monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path, monkeypatch):
    # never write audit entries into the real data/audit chain from tests
    monkeypatch.setenv("AUDIT_LOG", str(tmp_path / "audit.jsonl"))


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.limits import diagnose_limiter, global_limiter

    global_limiter.reset()
    diagnose_limiter.reset()
    yield
    global_limiter.reset()
    diagnose_limiter.reset()
