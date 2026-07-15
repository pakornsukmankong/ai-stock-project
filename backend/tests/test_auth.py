"""Auth verification tests — offline, no Supabase calls.

Covers the two local-verify paths added for the new asymmetric signing keys:
ES256 via JWKS (the production case) and HS256 via a shared secret (legacy).
"""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jose import jwt, jwk

from app.core import auth


def _es256_keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    jwk_dict = jwk.construct(pub_pem, "ES256").to_dict()
    jwk_dict.update({"kid": "kid-test", "use": "sig"})
    return priv_pem, jwk_dict


class _Req:
    def __init__(self, token=None):
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}


@pytest.fixture(autouse=True)
def _clear_jwks_cache():
    auth._jwks_cache = {}
    auth._jwks_fetched_at = 0.0
    yield


@pytest.mark.asyncio
async def test_es256_token_verified_via_jwks(monkeypatch):
    priv_pem, jwk_dict = _es256_keypair()

    async def fake_load(force=False):
        return {jwk_dict["kid"]: jwk_dict}

    monkeypatch.setattr(auth, "_load_jwks", fake_load)
    monkeypatch.setattr(auth, "get_settings", lambda: type("S", (), {
        "supabase_url": "https://proj.supabase.co", "supabase_jwt_secret": ""})())

    token = jwt.encode(
        {"sub": "user-abc", "aud": "authenticated", "exp": int(time.time()) + 3600},
        priv_pem, algorithm="ES256", headers={"kid": jwk_dict["kid"]},
    )

    assert await auth.get_current_user_id(_Req(token)) == "user-abc"


@pytest.mark.asyncio
async def test_es256_forged_token_rejected(monkeypatch):
    _, jwk_dict = _es256_keypair()
    other_priv_pem, _ = _es256_keypair()  # signed with a different key

    async def fake_load(force=False):
        return {jwk_dict["kid"]: jwk_dict}

    monkeypatch.setattr(auth, "_load_jwks", fake_load)
    monkeypatch.setattr(auth, "get_settings", lambda: type("S", (), {
        "supabase_url": "https://proj.supabase.co", "supabase_jwt_secret": ""})())

    forged = jwt.encode(
        {"sub": "attacker", "aud": "authenticated", "exp": int(time.time()) + 3600},
        other_priv_pem, algorithm="ES256", headers={"kid": jwk_dict["kid"]},
    )

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user_id(_Req(forged))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_hs256_legacy_secret_path(monkeypatch):
    secret = "legacy-shared-secret"
    monkeypatch.setattr(auth, "get_settings", lambda: type("S", (), {
        "supabase_url": "", "supabase_jwt_secret": secret})())

    token = jwt.encode(
        {"sub": "user-hs", "aud": "authenticated", "exp": int(time.time()) + 3600},
        secret, algorithm="HS256",
    )

    assert await auth.get_current_user_id(_Req(token)) == "user-hs"


@pytest.mark.asyncio
async def test_missing_header_rejected():
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user_id(_Req(None))
    assert exc.value.status_code == 401
