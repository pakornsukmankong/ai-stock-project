"""Config tests — OPENAI_MODEL default and override."""
from app.core.config import Settings


def test_openai_model_default_is_luna():
    # _env_file=None so a developer's local .env can't change the assertion.
    assert Settings(_env_file=None).openai_model == "gpt-5.6-luna"


def test_openai_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-nano")
    assert Settings(_env_file=None).openai_model == "gpt-5.4-nano"
