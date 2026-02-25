"""E2E infrastructure tests - assume server is running at http://localhost:8000."""

import time
import uuid

import httpx
import psycopg2
import pytest
import redis

# Database credentials from spec
DB_URL = "postgresql://postgres:Krishn%4062001@localhost:5433/pdf_management_app"
REDIS_URL = "redis://localhost:6379/0"
BASE_URL = "http://localhost:8000"


def test_postgres_reachable():
    """Connect directly to DB and execute SELECT 1."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    result = cur.fetchall()
    cur.close()
    conn.close()
    assert result == [(1,)]


def test_redis_reachable():
    """Connect to Redis and PING."""
    r = redis.from_url(REDIS_URL)
    response = r.ping()
    assert response is True or response in (b"PONG", "PONG")


def test_all_tables_exist():
    """Verify users, pdfs, pdf_versions, logs tables exist."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    required = {"users", "pdfs", "pdf_versions", "logs"}
    for t in required:
        assert t in tables, f"Table {t} not found. Got: {tables}"


def test_api_health_endpoint():
    """GET /api/health returns ok, db connected, redis connected."""
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert data["redis"] == "connected"


def test_logging_writes_to_db():
    """Log an event, wait for queue flush, verify row in logs table."""
    from app.core.logging import get_logger, log_event

    logger = get_logger("test_00_infrastructure")
    log_event(logger, "TEST_EVENT", metadata={"test": True})
    time.sleep(1)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM logs WHERE event = 'TEST_EVENT'")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) >= 1


def test_request_id_header():
    """GET /api/health returns X-Request-ID header as valid UUID."""
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        resp = client.get("/api/health")
    assert "x-request-id" in resp.headers or "X-Request-ID" in resp.headers
    rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
    assert rid is not None
    uuid.UUID(rid)
