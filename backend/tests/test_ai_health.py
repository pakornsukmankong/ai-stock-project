"""OpenAI request shape + startup usability check — offline (SDK fully mocked)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import ai_health


class _Settings:
    def __init__(
        self,
        api_key="sk-test",
        model="gpt-5.6-luna",
        temperature=None,
        reasoning_effort=None,
    ):
        self.openai_api_key = api_key
        self.openai_model = model
        self.openai_temperature = temperature
        self.openai_reasoning_effort = reasoning_effort


# --------------------------------------------------------------------------- #
# Request shape — GPT-5-family compatibility
# --------------------------------------------------------------------------- #
def test_request_uses_max_completion_tokens_not_max_tokens(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings())
    req = ai_health.build_chat_request([{"role": "user", "content": "hi"}], 500)

    # GPT-5-family models reject max_tokens with a 400.
    assert req["max_completion_tokens"] == 500
    assert "max_tokens" not in req
    assert req["model"] == "gpt-5.6-luna"


def test_temperature_omitted_by_default(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings(temperature=None))
    req = ai_health.build_chat_request([{"role": "user", "content": "hi"}], 10)

    # An explicit non-default temperature 400s on GPT-5-family models.
    assert "temperature" not in req


def test_temperature_sent_when_configured(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings(temperature=0.2))
    req = ai_health.build_chat_request([{"role": "user", "content": "hi"}], 10)
    assert req["temperature"] == 0.2


def test_reasoning_effort_omitted_by_default(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings())
    req = ai_health.build_chat_request([{"role": "user", "content": "hi"}], 10)
    # Non-reasoning models (gpt-4o-mini) 400 on this parameter.
    assert "reasoning_effort" not in req


def test_reasoning_effort_sent_when_configured(monkeypatch):
    monkeypatch.setattr(
        ai_health, "get_settings", lambda: _Settings(reasoning_effort="minimal")
    )
    req = ai_health.build_chat_request([{"role": "user", "content": "hi"}], 10)
    assert req["reasoning_effort"] == "minimal"


# --------------------------------------------------------------------------- #
# Startup check
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_api_key_reports_not_ok(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings(api_key=""))
    ok, msg = await ai_health.check_openai_model_access()
    assert ok is False
    assert "OPENAI_API_KEY" in msg


@pytest.mark.asyncio
async def test_model_usable_sends_real_completion(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings())
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(ai_health, "AsyncOpenAI", lambda **kw: client)

    ok, msg = await ai_health.check_openai_model_access()
    assert ok is True
    assert "usable" in msg
    # Must exercise a real completion with the production request shape —
    # models.retrieve returns 200 even when the params would be rejected.
    kwargs = client.chat.completions.create.await_args.kwargs
    assert "max_tokens" not in kwargs
    # Needs room for a reasoning model's hidden tokens: a tiny budget makes the
    # model spend it all thinking and 400, which looks like a config error.
    assert kwargs["max_completion_tokens"] >= 500


@pytest.mark.asyncio
async def test_unsupported_parameter_is_caught(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings())
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=Exception("Unsupported parameter: 'max_tokens'")
    )
    monkeypatch.setattr(ai_health, "AsyncOpenAI", lambda **kw: client)

    ok, msg = await ai_health.check_openai_model_access()
    assert ok is False
    assert "NOT usable" in msg
    assert "gpt-5.6-luna" in msg
