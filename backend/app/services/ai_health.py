"""Chat-completion request shape + a startup check that it actually works.

Both matter together: a wrong model id OR an unsupported parameter fails the
same silent way — the rule-based gate keeps running, every AI call errors, and
no notification is ever sent. The boot check therefore issues a real (1-token)
completion using the SAME request shape as production, so a parameter
incompatibility is caught at boot rather than discovered as missing alerts.
"""
from typing import Any, Dict, List, Tuple

from openai import AsyncOpenAI

from app.core.config import get_settings

# Keep the boot check snappy — never let a slow/hung API stall startup.
_CHECK_TIMEOUT_SECONDS = 10.0


def build_chat_request(
    messages: List[Dict[str, str]], max_output_tokens: int
) -> Dict[str, Any]:
    """Build a chat-completion kwargs dict compatible across model families.

    - `max_completion_tokens`, not `max_tokens`: GPT-5-family models reject the
      latter with a 400 (it also works on older models, so it's the safe choice).
    - `temperature` is only sent when explicitly configured: GPT-5-family models
      accept only the default and 400 on an explicit non-default value.
    """
    settings = get_settings()
    request: Dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "max_completion_tokens": max_output_tokens,
    }
    if settings.openai_temperature is not None:
        request["temperature"] = settings.openai_temperature
    return request


async def check_openai_model_access() -> Tuple[bool, str]:
    """Return (ok, message). Never raises — a boot check must not crash startup.

    Sends a real 1-token completion (negligible cost) instead of just retrieving
    the model, because `models.retrieve` returns 200 even when the request
    parameters we actually use would be rejected.
    """
    settings = get_settings()
    model = settings.openai_model

    if not settings.openai_api_key:
        return False, "OPENAI_API_KEY not set — AI analysis and briefings will be skipped."

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=_CHECK_TIMEOUT_SECONDS
        )
        await client.chat.completions.create(
            **build_chat_request([{"role": "user", "content": "ping"}], 1)
        )
        return True, f"OpenAI model '{model}' is usable."
    except Exception as e:
        # Unknown/unentitled model, unsupported parameter, auth, network, etc.
        return (
            False,
            f"OpenAI model '{model}' is NOT usable ({type(e).__name__}: {e}). "
            f"Check OPENAI_MODEL / OPENAI_TEMPERATURE — AI alerts and briefings "
            f"will not be sent until this succeeds.",
        )
