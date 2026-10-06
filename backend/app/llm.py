import json
import os

import httpx


class LlmError(Exception):
    pass


class RateLimited(LlmError):
    pass


class LocalLLM:
    """Offline extractive fallback: no network, no keys."""

    name = "local"

    def complete(self, prompt: str) -> str:
        if "CLINICAL GROUP CHAT" in prompt:
            import re

            m = re.search(r"You are ([^,]+), answering", prompt)
            who = m.group(1) if m else "board"
            return json.dumps(
                {
                    "reply": (
                        f"{who}: local extractive fallback "
                        "(external LLM unavailable); case context loaded."
                    )
                }
            )
        conf = 0.55 if "role: clinical" in prompt else 0.7
        if "Consensus" in prompt:
            return json.dumps(
                {"diagnosis": "Insufficient evidence - local fallback", "confidence": 0.4}
            )
        if prompt.startswith(("Clinician view", "Patient view")):
            return json.dumps({"text": "Local fallback explanation. External LLM unavailable."})
        if "Self-critic" in prompt:
            return json.dumps({"warnings": ["external LLM unavailable; verdict unverified"]})
        if "Critique" in prompt:
            return json.dumps({"adjusted": {}})
        return json.dumps({"hypothesis": "local extractive summary", "confidence": conf})


class GroqClient:
    name = "groq"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        self._client = httpx.Client(timeout=30.0)

    def complete(self, prompt: str) -> str:
        r = self._client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        if r.status_code == 429:
            raise RateLimited("Groq free tier rate limit hit")
        if r.status_code != 200:
            raise LlmError(f"Groq error {r.status_code}: {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"]


def get_llm():
    key = os.environ.get("GROQ_API_KEY", "")
    if key:
        try:
            return GroqClient(key)
        except Exception:
            pass
    return LocalLLM()
