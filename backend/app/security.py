"""Password hashing and JWT access tokens."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import Settings


def _prehash(password: str) -> bytes:
    # bcrypt only looks at the first 72 bytes (and bcrypt>=5 rejects longer input), so we
    # hash first. base64 keeps the digest free of NUL bytes.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str | None:
    """Return the user id in the token, or None if the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
