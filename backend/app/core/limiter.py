"""Rate limiter configuration."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

def _default_key(request: Request) -> str:
    return get_remote_address(request) or "127.0.0.1"


def _upload_key(request: Request) -> str:
    """Rate limit by user_id from Bearer token, fallback to IP."""
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth[7:]
        from app.core.security import decode_token
        payload = decode_token(token)
        if payload and payload.get("type") == "access" and payload.get("sub"):
            return f"upload:{payload['sub']}"
    return getattr(request, "client", None) and request.client.host or "127.0.0.1"


limiter = Limiter(key_func=_default_key)
