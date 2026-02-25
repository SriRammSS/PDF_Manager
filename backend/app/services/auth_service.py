"""Auth business logic."""

import uuid
from datetime import datetime, timezone

import psycopg2
import redis
from psycopg2.extras import Json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.schemas.auth import SignupRequest

logger = get_logger("auth_service")

REVOKED_PREFIX = "revoked:"
LOGIN_FAIL_PREFIX = "login_fail:"
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 60  # seconds


def get_redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def check_login_rate_limit(email: str) -> bool:
    """Per-email rate limit for failed logins. Returns True if rate limited."""
    r = get_redis()
    key = f"{LOGIN_FAIL_PREFIX}{email}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOGIN_FAIL_WINDOW)
    pipe.execute()
    return int(r.get(key) or 0) > LOGIN_FAIL_LIMIT


def _write_log_sync(event: str, user_id: str | None) -> None:
    """Write log entry directly to DB for critical audit events."""
    try:
        db_url = get_settings().sync_database_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO logs (id, timestamp, level, module, event, user_id, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
                    """,
                    (str(uuid.uuid4()), datetime.now(timezone.utc), "INFO", "auth_service", event, user_id, Json({})),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Non-fatal; log_event still runs async


async def signup(db: AsyncSession, data: SignupRequest) -> User:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("EMAIL_EXISTS")
    user = User(
        email=data.email,
        display_name=data.display_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    log_event(logger, "SIGNUP_SUCCESS", user_id=str(user.id), metadata={"email": data.email})
    return user


async def login(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        log_event(logger, "LOGIN_USER_NOT_FOUND", metadata={"email": email})
        raise ValueError("USER_NOT_FOUND")
    if not verify_password(password, user.hashed_password):
        log_event(logger, "LOGIN_BAD_PASSWORD", user_id=str(user.id), metadata={"email": email})
        raise ValueError("BAD_PASSWORD")
    # Reset failed-attempt counter on successful login
    r = get_redis()
    r.delete(f"{LOGIN_FAIL_PREFIX}{email}")
    access_token = create_access_token(str(user.id))
    refresh_token, _ = create_refresh_token(str(user.id))
    log_event(logger, "LOGIN_SUCCESS", user_id=str(user.id), metadata={"email": email})
    return user, access_token, refresh_token


def revoke_refresh_token(refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    if payload and payload.get("type") == "refresh" and payload.get("jti"):
        r = get_redis()
        jti = payload["jti"]
        user_id = payload.get("sub")
        # Store with TTL matching token expiry (7 days default)
        r.setex(f"{REVOKED_PREFIX}{jti}", 7 * 24 * 3600, "1")
        log_event(logger, "LOGOUT", user_id=user_id, metadata={"jti": jti})
        log_event(logger, "TOKEN_REVOKED", user_id=user_id, metadata={"jti": jti})
        # Sync write to DB for audit (DatabaseLogHandler queue may lag)
        _write_log_sync("LOGOUT", user_id)
        _write_log_sync("TOKEN_REVOKED", user_id)


def is_refresh_token_revoked(refresh_token: str) -> bool:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("jti"):
        return True
    r = get_redis()
    return bool(r.exists(f"{REVOKED_PREFIX}{payload['jti']}"))


def refresh_tokens(refresh_token: str) -> tuple[str, str]:
    if is_refresh_token_revoked(refresh_token):
        raise ValueError("TOKEN_REVOKED")
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("INVALID_TOKEN")
    sub = payload.get("sub")
    if not sub:
        raise ValueError("INVALID_TOKEN")
    access_token = create_access_token(sub)
    new_refresh_token, _ = create_refresh_token(sub)
    return access_token, new_refresh_token
