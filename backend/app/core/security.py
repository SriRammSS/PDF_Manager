"""Password hashing and JWT utilities."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": now,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Returns (token, jti)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


def decode_token(token: str, verify: bool = True) -> dict | None:
    settings = get_settings()
    try:
        if verify:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return jwt.get_unverified_claims(token)
    except JWTError:
        return None


def create_expired_token_for_testing() -> str:
    """Create an access token that is already expired (for testing)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) - timedelta(seconds=1)
    payload = {
        "sub": str(uuid.uuid4()),
        "exp": expire,
        "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
