import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from jose import jwt, JWTError

from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.core.http_client import get_http_client

# Supabase's new (asymmetric) signing keys default to ES256; RS256 is the other
# offered option. HS256 is the legacy shared-secret mode.
_ASYMMETRIC_ALGS = ("ES256", "RS256")

# In-memory JWKS cache: {kid: jwk_dict}. Refreshed on a TTL, or immediately on a
# cache miss (key rotation introduces a new kid).
_jwks_cache: dict[str, dict] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 600


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    return token


def _user_id_from_claims(payload: dict) -> str:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


# --------------------------------------------------------------------------- #
# JWKS (asymmetric ES256/RS256)
# --------------------------------------------------------------------------- #
def _jwks_url() -> str:
    base = get_settings().supabase_url.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


async def _load_jwks(force: bool = False) -> dict[str, dict]:
    """Return {kid: jwk}, fetching from Supabase and caching for a TTL."""
    global _jwks_cache, _jwks_fetched_at

    is_fresh = (time.monotonic() - _jwks_fetched_at) < _JWKS_TTL_SECONDS
    if _jwks_cache and is_fresh and not force:
        return _jwks_cache

    client = get_http_client()
    resp = await client.get(_jwks_url(), timeout=5.0)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])

    _jwks_cache = {k["kid"]: k for k in keys if "kid" in k}
    _jwks_fetched_at = time.monotonic()
    return _jwks_cache


async def _get_jwk(kid: str) -> Optional[dict]:
    keys = await _load_jwks()
    if kid not in keys:
        # Unknown kid: the signing key may have rotated — refresh once.
        keys = await _load_jwks(force=True)
    return keys.get(kid)


async def _verify_asymmetric(token: str, header: dict) -> str:
    """Verify an ES256/RS256 token against the project's JWKS.

    Raises HTTPException(401) for token problems (bad/missing kid, bad
    signature). Infra failures (JWKS unreachable) propagate as other exceptions
    so the caller can fall back to remote verification.
    """
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    key = await _get_jwk(kid)
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=list(_ASYMMETRIC_ALGS),
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return _user_id_from_claims(payload)


# --------------------------------------------------------------------------- #
# HS256 (legacy shared secret)
# --------------------------------------------------------------------------- #
def _verify_hs256(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return _user_id_from_claims(payload)


# --------------------------------------------------------------------------- #
# Remote fallback
# --------------------------------------------------------------------------- #
async def _verify_remotely(token: str) -> str:
    """Ask Supabase to validate the token (works for any signing algorithm)."""
    try:
        supabase = get_supabase_client()
        response = await run_in_threadpool(supabase.auth.get_user, token)
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return response.user.id


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
async def get_current_user_id(request: Request) -> str:
    """Extract and verify the caller's Supabase JWT, returning their user id.

    Verification is local whenever possible:
    - ES256/RS256 (Supabase's new signing keys) → verified against the project's
      published JWKS, no secret required.
    - HS256 (legacy) → verified with SUPABASE_JWT_SECRET when configured.

    Anything else, or an infra failure fetching the JWKS, falls back to a remote
    check against the Supabase Auth server (correct for any algorithm, slower).
    """
    token = _extract_bearer_token(request)
    settings = get_settings()

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    alg = header.get("alg", "")

    try:
        if alg in _ASYMMETRIC_ALGS and settings.supabase_url:
            return await _verify_asymmetric(token, header)
        if alg == "HS256" and settings.supabase_jwt_secret:
            return _verify_hs256(token, settings.supabase_jwt_secret)
    except HTTPException:
        # A structurally valid token that failed verification is a genuine 401 —
        # don't mask it by retrying remotely.
        raise
    except Exception:
        # Infra problem (e.g. JWKS endpoint unreachable): fall through to remote.
        pass

    return await _verify_remotely(token)
