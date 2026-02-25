"""Logs API - SSE stream and log history."""

import select
import time
from typing import Annotated, Optional

import psycopg2
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/logs", tags=["logs"])
logger = get_logger("api.logs")


def _block_for_chunk(conn, cursor, last_keepalive_ref):
    """Block for up to 1 second. Returns SSE chunk or empty string."""
    if select.select([conn], [], [], 1.0)[0]:
        conn.poll()
        for notify in conn.notifies:
            payload = notify.payload
            conn.notifies.clear()
            return f"data: {payload}\n\n"
        conn.notifies.clear()
    if time.time() - last_keepalive_ref[0] > 15:
        last_keepalive_ref[0] = time.time()
        return ": ping\n\n"
    return ""


def _log_stream_generator():
    settings = get_settings()
    db_url = settings.sync_database_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.set_isolation_level(0)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_log_entry;")
    last_keepalive = [time.time()]
    try:
        while True:
            chunk = _block_for_chunk(conn, cursor, last_keepalive)
            if chunk:
                yield chunk
    except GeneratorExit:
        pass
    finally:
        try:
            cursor.execute("UNLISTEN new_log_entry;")
        except Exception:
            pass
        conn.close()


@router.get("/stream")
async def log_stream(token: Optional[str] = Query(None, alias="token")):
    """SSE log stream. Auth via ?token={access_token}."""
    if not token:
        return PlainTextResponse("Unauthorized", status_code=401)
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return PlainTextResponse("Unauthorized", status_code=401)

    async def async_stream():
        gen = _log_stream_generator()
        try:
            while True:
                chunk = await run_in_threadpool(
                    lambda: next(gen, None),
                )
                if chunk is None:
                    break
                yield chunk
        except StopIteration:
            pass
        finally:
            try:
                gen.close()
            except Exception:
                pass

    return StreamingResponse(
        async_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/")
async def list_logs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    level: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
):
    """Paginated log history with optional level/module filters."""
    conditions = []
    params = {}
    if level:
        conditions.append("level = :level")
        params["level"] = level
    if module:
        conditions.append("module = :module")
        params["module"] = module

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * size

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM logs WHERE {where_clause}"),
        params,
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        text(
            f"""
            SELECT id, timestamp, level, module, event, user_id, request_id, task_id, duration_ms, metadata, error
            FROM logs WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT :size OFFSET :offset
            """
        ),
        {**params, "size": size, "offset": offset},
    )
    rows = result.fetchall()

    items = []
    for row in rows:
        items.append({
            "id": str(row[0]),
            "timestamp": row[1].isoformat() if row[1] else None,
            "level": row[2],
            "module": row[3],
            "event": row[4],
            "user_id": str(row[5]) if row[5] else None,
            "request_id": str(row[6]) if row[6] else None,
            "task_id": row[7],
            "duration_ms": row[8],
            "metadata": row[9],
            "error": row[10],
        })

    logger.debug("LOGS_FETCHED", extra={"event": "LOGS_FETCHED", "metadata": {"count": len(items), "page": page}})
    return {"items": items, "total": total, "page": page, "size": size}
