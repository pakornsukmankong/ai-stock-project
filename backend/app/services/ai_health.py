"""Startup check that the configured OPENAI_MODEL is reachable by the account.

A wrong or unentitled model id (e.g. gpt-5.6-* on an account without access)
fails silently: the rule-based gate keeps working, but every AI call inside a
cycle errors and no notification is ever sent. Surfacing it once at boot turns
that into a visible warning instead of a quiet dead end.
"""
from typing import Tuple

from openai import AsyncOpenAI

from app.core.config import get_settings

# Keep the boot check snappy — never let a slow/hung API stall startup.
_CHECK_TIMEOUT_SECONDS = 10.0


async def check_openai_model_access() -> Tuple[bool, str]:
    """Return (ok, message). Never raises — a boot check must not crash startup.

    Uses the retrieve-model endpoint, which 404s when the account can't access
    the id. That's cheaper and side-effect-free compared to a test completion.
    """
    settings = get_settings()
    model = settings.openai_model

    if not settings.openai_api_key:
        return False, "OPENAI_API_KEY not set — AI analysis and briefings will be skipped."

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=_CHECK_TIMEOUT_SECONDS
        )
        await client.models.retrieve(model)
        return True, f"OpenAI model '{model}' is accessible."
    except Exception as e:
        # NotFoundError (no access / unknown id), auth failure, network, etc.
        return (
            False,
            f"OpenAI model '{model}' is NOT accessible ({type(e).__name__}: {e}). "
            f"Set OPENAI_MODEL to a model your account can use (e.g. gpt-4o-mini).",
        )
