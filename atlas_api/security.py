import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from .config import Settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def opaque_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def access_token(settings: Settings, user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])


def oauth_state(settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"purpose": "github_oauth", "nonce": secrets.token_urlsafe(24), "iat": now, "exp": now + timedelta(minutes=10)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def verify_oauth_state(settings: Settings, state: str) -> None:
    payload = jwt.decode(state, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
    if payload.get("purpose") != "github_oauth" or not payload.get("nonce"):
        raise jwt.InvalidTokenError("invalid OAuth state")
