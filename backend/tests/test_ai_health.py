"""Startup OpenAI model access check — offline (SDK fully mocked)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import ai_health


class _Settings:
    def __init__(self, api_key, model="gpt-5.6-luna"):
        self.openai_api_key = api_key
        self.openai_model = model


@pytest.mark.asyncio
async def test_missing_api_key_reports_not_ok(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings(""))
    ok, msg = await ai_health.check_openai_model_access()
    assert ok is False
    assert "OPENAI_API_KEY" in msg


@pytest.mark.asyncio
async def test_model_accessible(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings("sk-test"))
    client = MagicMock()
    client.models.retrieve = AsyncMock(return_value=MagicMock(id="gpt-5.6-luna"))
    monkeypatch.setattr(ai_health, "AsyncOpenAI", lambda **kw: client)

    ok, msg = await ai_health.check_openai_model_access()
    assert ok is True
    assert "accessible" in msg
    client.models.retrieve.assert_awaited_once_with("gpt-5.6-luna")


@pytest.mark.asyncio
async def test_model_not_accessible_is_caught(monkeypatch):
    monkeypatch.setattr(ai_health, "get_settings", lambda: _Settings("sk-test", "gpt-5.6-luna"))
    client = MagicMock()
    client.models.retrieve = AsyncMock(side_effect=Exception("model_not_found"))
    monkeypatch.setattr(ai_health, "AsyncOpenAI", lambda **kw: client)

    ok, msg = await ai_health.check_openai_model_access()
    assert ok is False
    assert "NOT accessible" in msg
    assert "gpt-5.6-luna" in msg
