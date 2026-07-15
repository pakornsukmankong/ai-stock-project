from typing import Optional

import httpx

# One shared client for all outbound HTTP (Yahoo Finance, LINE). Constructing an
# httpx.AsyncClient per call — as every service used to — meant a fresh TCP + TLS
# handshake on every request, adding hundreds of ms and defeating keep-alive.
_client: Optional[httpx.AsyncClient] = None

_LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20)
_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def get_http_client() -> httpx.AsyncClient:
    """Return the process-wide async HTTP client, creating it on first use."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=_LIMITS,
            timeout=_DEFAULT_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
    return _client


async def close_http_client() -> None:
    """Close the shared client (called from the FastAPI lifespan shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
