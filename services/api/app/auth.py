"""Supabase access-token verification using cached asymmetric JWKS keys.

Legacy HS256 tokens are intentionally disabled by default. Enabling them requires
an explicit secret and VOLVOX_SUPABASE_ALLOW_HS256=true during migration only.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import User
from app.settings import Settings, get_settings


class AuthSettings(BaseModel):
    issuer: str
    audience: str = "authenticated"
    jwks_url: str
    allow_hs256: bool = False
    jwt_secret: str | None = None


@dataclass(frozen=True)
class Identity:
    subject: str
    claims: dict[str, Any]


def auth_settings(settings: Settings) -> AuthSettings:
    project_url = settings.supabase_url.rstrip("/")
    issuer = settings.supabase_jwt_issuer or (f"{project_url}/auth/v1" if project_url else "")
    jwks_url = settings.supabase_jwks_url or (
        f"{project_url}/auth/v1/.well-known/jwks.json" if project_url else ""
    )
    audience = settings.supabase_jwt_audience
    allow_hs256 = settings.supabase_allow_hs256
    secret = (
        settings.supabase_jwt_secret.get_secret_value() if settings.supabase_jwt_secret else None
    )
    if allow_hs256 and not secret:
        raise ValueError("HS256 compatibility requires VOLVOX_SUPABASE_JWT_SECRET")
    return AuthSettings(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        allow_hs256=allow_hs256,
        jwt_secret=secret,
    )


@lru_cache(maxsize=8)
def jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def verify_token(token: str, config: AuthSettings) -> Identity:
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        issuer = config.issuer
        if not issuer:
            raise ValueError("Supabase JWT issuer is not configured")
        if algorithm in {"RS256", "ES256"}:
            signing_key = jwks_client(config.jwks_url).get_signing_key_from_jwt(token).key
            algorithms = [algorithm]
        elif algorithm == "HS256" and config.allow_hs256 and config.jwt_secret:
            signing_key = config.jwt_secret
            algorithms = ["HS256"]
        else:
            raise ValueError("JWT algorithm is not allowed")
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=algorithms,
            issuer=issuer,
            audience=config.audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=0,
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError("JWT subject is invalid")
        return Identity(subject=subject, claims=claims)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_identity(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Identity:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    config = auth_settings(settings)
    if not config.issuer or (not config.jwks_url and not config.allow_hs256):
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return verify_token(token, config)


def get_current_user(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> User:
    user = db.scalar(
        select(User).where(User.auth_subject == identity.subject, User.active.is_(True))
    )
    if user is None:
        raise HTTPException(status_code=403, detail="User is not provisioned")
    return user
