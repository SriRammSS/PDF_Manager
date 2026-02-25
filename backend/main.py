"""PDF Manager API - FastAPI application."""

from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.core.limiter import limiter
from app.api.logs import router as logs_router
from app.api.pdfs import router as pdfs_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.middleware import RequestIDMiddleware
from app.db.session import AsyncSessionLocal, async_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_engine.dispose()


app = FastAPI(
    title="PDF Manager API",
    lifespan=lifespan,
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter  # required by slowapi
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router, prefix="/api")
app.include_router(pdfs_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(logs_router, prefix="/api")


@app.get("/api/health")
async def health():
    """Health check - verifies DB and Redis connectivity."""
    settings = get_settings()
    db_status = "disconnected"
    redis_status = "disconnected"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass

    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        redis_status = "connected"
    except Exception:
        pass

    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
    }
