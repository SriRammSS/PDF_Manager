"""E2E tests for PDF Upload module. Celery worker must be running."""

import glob
import time

import httpx
import psycopg2
import pytest

from tests.conftest import wait_for_status

BASE_URL = "http://localhost:8000"
DB_URL = "postgresql://postgres:Krishn%4062001@localhost:5433/pdf_management_app"


def _get_storage_path():
    from app.core.config import get_settings
    return get_settings().file_storage_path


def test_single_pdf_upload_returns_202(auth_headers, sample_pdf_bytes):
    t0 = time.perf_counter()
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("test.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    t1 = time.perf_counter()
    assert resp.status_code == 202
    assert (t1 - t0) < 0.5
    data = resp.json()
    assert "files" in data and len(data["files"]) >= 1
    f = data["files"][0]
    assert "pdf_id" in f
    assert f.get("filename") == "test.pdf"
    assert f.get("status") == "pending"
    assert "task_id" in f


def test_processing_completes_status_ready(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("ready_test.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    pdf_id = resp.json()["files"][0]["pdf_id"]
    wait_for_status(pdf_id, "ready", auth_headers, timeout=30)
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r = client.get(f"/api/pdfs/{pdf_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data.get("page_count", 0) >= 1
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM logs WHERE event = 'TASK_COMPLETED' AND metadata->>'pdf_id' = %s",
        (pdf_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) >= 1


def test_multi_file_upload(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[
                ("files", ("a.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("b.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("c.pdf", sample_pdf_bytes, "application/pdf")),
            ],
        )
    assert resp.status_code == 202
    data = resp.json()
    assert len(data["files"]) == 3
    pdf_ids = [f["pdf_id"] for f in data["files"]]
    assert len(set(pdf_ids)) == 3
    for pdf_id in pdf_ids:
        wait_for_status(pdf_id, "ready", auth_headers, timeout=45)
    from jose import jwt
    payload = jwt.get_unverified_claims(
        auth_headers["Authorization"].replace("Bearer ", "")
    )
    user_id = payload.get("sub")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM pdfs WHERE owner_id = %s AND status = 'ready'",
        (user_id,),
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 3


def test_invalid_file_type_rejected(auth_headers):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pdfs")
    before = cur.fetchone()[0]
    cur.close()
    conn.close()
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("test.txt", b"plain text content", "text/plain"))],
        )
    assert resp.status_code == 422
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pdfs")
    after = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert after == before


def test_fake_pdf_magic_bytes_rejected(auth_headers):
    fake_bytes = b"THIS IS NOT A PDF" + b"x" * 100
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pdfs")
    before = cur.fetchone()[0]
    cur.close()
    conn.close()
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("sneaky.pdf", fake_bytes, "application/pdf"))],
        )
    assert resp.status_code == 422
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pdfs")
    after = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert after == before


def test_oversized_file_rejected(auth_headers):
    from app.core.config import get_settings
    max_mb = get_settings().max_upload_size_mb
    oversized = b"%PDF" + b"x" * ((max_mb + 1) * 1024 * 1024 - 4)
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("big.pdf", oversized, "application/pdf"))],
        )
    assert resp.status_code == 422


def test_upload_requires_auth(sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            files=[("files", ("test.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    assert resp.status_code == 401


def test_task_status_polling(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("poll.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    task_id = resp.json()["files"][0]["task_id"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r = client.get(f"/api/pdfs/tasks/{task_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert "state" in data
    assert data["state"] in ["PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY"]


def test_upload_logs_emitted(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("logs_test.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    pdf_id = resp.json()["files"][0]["pdf_id"]
    wait_for_status(pdf_id, "ready", auth_headers, timeout=30)
    time.sleep(2)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT event, timestamp FROM logs WHERE metadata->>'pdf_id' = %s ORDER BY timestamp ASC",
        (pdf_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    events = [r[0] for r in rows]
    assert "UPLOAD_RECEIVED" in events
    assert "TASK_ENQUEUED" in events
    assert "TASK_STARTED" in events
    assert "TASK_COMPLETED" in events
    timestamps = [r[1] for r in rows]
    idx_upload = events.index("UPLOAD_RECEIVED")
    idx_enqueued = events.index("TASK_ENQUEUED")
    idx_started = events.index("TASK_STARTED")
    idx_completed = events.index("TASK_COMPLETED")
    assert timestamps[idx_upload] <= timestamps[idx_enqueued]
    assert timestamps[idx_enqueued] <= timestamps[idx_started]
    assert timestamps[idx_started] <= timestamps[idx_completed]


def test_atomic_write_no_partial_files(auth_headers, sample_pdf_bytes):
    import os
    storage = _get_storage_path()
    before = set(glob.glob(os.path.join(storage, "**", "*.tmp"), recursive=True))
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("atomic.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    after = set(glob.glob(os.path.join(storage, "**", "*.tmp"), recursive=True))
    assert len(after - before) == 0
