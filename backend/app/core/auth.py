from fastapi import Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from jose import jwt, JWTError

from app.core.config import get_settings
from app.core.database import get_supabase_client


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    return token


def _verify_locally(token: str, secret: str) -> str:
    """Verify a Supabase-issued JWT with the project's JWT secret.

    Avoids a network round-trip to the Supabase Auth server on every single API
    call (which was also a blocking call inside the event loop).
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


async def _verify_remotely(token: str) -> str:
    """Fallback: ask Supabase to validate the token (slower, one HTTP hop)."""
    try:
        supabase = get_supabase_client()
        response = await run_in_threadpool(supabase.auth.get_user, token)
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return response.user.id


async def get_current_user_id(request: Request) -> str:
    """Extract and verify the caller's Supabase JWT, returning their user id."""
    token = _extract_bearer_token(request)
    settings = get_settings()

    if settings.supabase_jwt_secret:
        return _verify_locally(token, settings.supabase_jwt_secret)

    return await _verify_remotely(token)
