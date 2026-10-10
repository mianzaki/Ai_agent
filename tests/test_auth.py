import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import AuthSettings, get_current_identity, jwks_client, verify_token
from app.settings import Settings

ISSUER = "https://sample-project.supabase.co/auth/v1"


@pytest.fixture(scope="module")
def rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    return private, public


def make_token(
    key,
    *,
    issuer=ISSUER,
    audience="authenticated",
    exp=None,
    algorithm="RS256",
    subject="user-123",
):
    now = int(time.time())
    return jwt.encode(
        {
            "sub": subject,
            "iss": issuer,
            "aud": audience,
            "iat": now - 1,
            "exp": exp or now + 60,
        },
        key,
        algorithm=algorithm,
        headers={"kid": "local-test-key"} if algorithm != "HS256" else None,
    )


def test_asymmetric_token_validation_uses_cached_jwks_client(monkeypatch, rsa_keys):
    private, public = rsa_keys

    class StaticKey:
        key = public

    class StaticJwks:
        def get_signing_key_from_jwt(self, _token):
            return StaticKey()

    monkeypatch.setattr("app.auth.jwks_client", lambda _url: StaticJwks())
    token = make_token(private)
    identity = verify_token(
        token, AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/.well-known/jwks.json")
    )
    assert identity.subject == "user-123"


def test_jwks_client_is_cached_for_key_rotation_window():
    jwks_client.cache_clear()
    first = jwks_client(f"{ISSUER}/.well-known/jwks.json")
    second = jwks_client(f"{ISSUER}/.well-known/jwks.json")
    assert first is second
    assert first.jwk_set_cache is not None
    assert first.jwk_set_cache.lifespan == 300
    assert (
        first.get_signing_key_from_jwt.__func__
        is second.get_signing_key_from_jwt.__func__
    )
    jwks_client.cache_clear()


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 60},
        {"issuer": "https://attacker.invalid/auth/v1"},
        {"audience": "other"},
    ],
)
def test_rejects_expired_wrong_issuer_and_wrong_audience(rsa_keys, overrides):
    private, _public = rsa_keys
    token = make_token(private, **overrides)
    with pytest.raises(HTTPException) as exc:
        verify_token(token, AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/jwks"))
    assert exc.value.status_code == 401


def test_rejects_forged_signature(rsa_keys):
    private, _public = rsa_keys
    forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(forged)
    with pytest.raises(HTTPException):
        verify_token(token, AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/jwks"))


def test_rejects_missing_required_claims(rsa_keys):
    private, _public = rsa_keys
    token = jwt.encode(
        {"sub": "user-123", "iss": ISSUER, "aud": "authenticated"},
        private,
        algorithm="RS256",
        headers={"kid": "local-test-key"},
    )
    with pytest.raises(HTTPException):
        verify_token(token, AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/jwks"))


def test_rejects_algorithm_confusion_and_bad_tokens():
    config = AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/jwks", allow_hs256=False)
    for token in ("not-a-token", "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1In0."):
        with pytest.raises(HTTPException):
            verify_token(token, config)


def test_missing_or_malformed_authorization_is_rejected_without_identity():
    from unittest.mock import Mock

    request = Mock()
    request.headers = {"authorization": "Bearer"}
    with pytest.raises(HTTPException) as missing:
        get_current_identity(
            request, Settings(supabase_url="https://sample-project.supabase.co")
        )
    assert missing.value.status_code == 401

    request.headers = {"authorization": "Basic abc"}
    with pytest.raises(HTTPException) as malformed:
        get_current_identity(
            request, Settings(supabase_url="https://sample-project.supabase.co")
        )
    assert malformed.value.status_code == 401


def test_legacy_hs256_is_opt_in_only():
    token = make_token("local-only-secret", algorithm="HS256")
    disabled = AuthSettings(issuer=ISSUER, jwks_url=f"{ISSUER}/jwks")
    with pytest.raises(HTTPException):
        verify_token(token, disabled)
    enabled = AuthSettings(
        issuer=ISSUER,
        jwks_url=f"{ISSUER}/jwks",
        allow_hs256=True,
        jwt_secret="local-only-secret",
    )
    assert verify_token(token, enabled).subject == "user-123"
