"""LINE webhook tests — signature verification and code parsing (offline)."""
import base64
import hashlib
import hmac

from app.api import line_webhook as wh
from app.services import line_linking as ll


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_signature_accepts_valid():
    secret, body = "chan-secret", b'{"events":[]}'
    assert wh._verify_signature(secret, body, _sign(secret, body)) is True


def test_signature_rejects_tampered_body():
    secret = "chan-secret"
    good = _sign(secret, b'{"events":[]}')
    # Same signature, different body must not verify.
    assert wh._verify_signature(secret, b'{"events":[{"x":1}]}', good) is False


def test_signature_rejects_wrong_secret():
    body = b'{"events":[]}'
    assert wh._verify_signature("real", body, _sign("attacker", body)) is False


def test_signature_rejects_when_secret_unset():
    body = b'{"events":[]}'
    assert wh._verify_signature("", body, _sign("x", body)) is False


def test_code_generation_is_unambiguous():
    for _ in range(200):
        code = ll.generate_code()
        assert len(code) == ll.CODE_LENGTH
        assert set(code) <= set(ll._ALPHABET)
        # No lookalike characters that trip up manual entry.
        assert not (set(code) & set("01OIL"))


def test_looks_like_code_normalizes_spacing_and_case():
    code = ll.generate_code()
    spaced = " ".join(code.lower())  # e.g. "a b c d e f"
    assert ll.looks_like_code(spaced) is True
    assert ll.normalize_code(spaced) == code


def test_looks_like_code_rejects_non_codes():
    assert ll.looks_like_code("hello there") is False
    assert ll.looks_like_code("ABC") is False       # too short
    assert ll.looks_like_code("ABCDEFG") is False    # too long
