from functools import lru_cache
from typing import Any

from fastapi.concurrency import run_in_threadpool
from supabase import create_client, Client

from app.core.config import get_settings


@lru_cache()
def get_supabase_client() -> Client:
    """Return the shared Supabase client.

    Cached: create_client() builds a fresh HTTP session (and connection pool)
    every time, so calling it per query meant a new TCP+TLS handshake for every
    single DB round-trip.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def db(query: Any) -> Any:
    """Execute a supabase-py query builder without blocking the event loop.

    supabase-py 2.x is a *synchronous* client, so calling `.execute()` directly
    inside an `async def` stalls the whole loop — including the analysis
    scheduler, which shares it. Building the query is cheap; only `.execute()`
    does I/O, so that is what we hand to the threadpool.

    Usage:
        rows = await db(supabase.table("alerts").select("*").eq("user_id", uid))
    """
    return await run_in_threadpool(query.execute)
