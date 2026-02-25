"""E2E tests for PDF Viewing and File Management. Celery worker must be running."""

import time
from uuid import uuid4

import httpx
import psycopg2
import pytest

from tests.conftest import wait_for_status

BASE_URL = "http://localhost:8000"
DB_URL = "postgresql://postgres:Krishn%4062001@localhost:5433/pdf_management_app"


def _auth_headers_for_user(email: str, password: str) -> dict:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post(
            "/api/auth/signup",
            json={"email": email, "display_name": "Test", "password": password},
        )
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_pdfs_authenticated(auth_headers):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/pdfs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    for item in data["items"]:
        assert "id" in item
        assert "name" in item
        assert "status" in item
        assert "page_count" in item


def test_list_pdfs_unauthenticated():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/pdfs")
    assert resp.status_code == 401


def test_list_pdfs_pagination(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[
                ("files", ("p1.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("p2.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("p3.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("p4.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("p5.pdf", sample_pdf_bytes, "application/pdf")),
            ],
        )
    assert resp.status_code == 202
    pdf_ids = [str(f["pdf_id"]) for f in resp.json()["files"]]
    for pdf_id in pdf_ids:
        wait_for_status(pdf_id, "ready", auth_headers, timeout=45)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r1 = client.get("/api/pdfs", headers=auth_headers, params={"page": 1, "size": 2})
        r2 = client.get("/api/pdfs", headers=auth_headers, params={"page": 2, "size": 2})
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert len(d1["items"]) == 2
    assert d1["total"] >= 5
    page1_ids = {item["id"] for item in d1["items"]}
    page2_ids = {item["id"] for item in d2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_get_single_pdf(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get(f"/api/pdfs/{pdf_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pdf_id
    assert data["status"] == "ready"
    assert data.get("page_count", 0) >= 1


def test_get_pdf_wrong_owner(auth_headers, sample_pdf_bytes):
    email_b = f"userb_{uuid4().hex[:8]}@test.com"
    headers_b = _auth_headers_for_user(email_b, "TestPass1")
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=headers_b,
            files=[("files", ("b.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    assert resp.status_code == 202
    pdf_id_b = resp.json()["files"][0]["pdf_id"]
    wait_for_status(pdf_id_b, "ready", headers_b, timeout=30)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get(f"/api/pdfs/{pdf_id_b}", headers=auth_headers)
    assert resp.status_code == 403

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM pdfs WHERE id = %s", (pdf_id_b,))
    cur.execute("DELETE FROM users WHERE email = %s", (email_b,))
    conn.commit()
    cur.close()
    conn.close()


def test_stream_pdf(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    t0 = time.perf_counter()
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.get(f"/api/pdfs/{pdf_id}/stream", headers=auth_headers)
    t1 = time.perf_counter()
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/pdf")
    assert resp.content[:4] == b"%PDF"
    assert (t1 - t0) < 0.8


def test_stream_pdf_range_request(auth_headers, sample_pdf_bytes):
    import io
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(sample_pdf_bytes))
    for _ in range(8):
        pdf.pages.append(pdf.pages[0])
    buf = io.BytesIO()
    pdf.save(buf)
    buf.seek(0)
    large_pdf = buf.read()
    pdf.close()
    assert len(large_pdf) >= 1024

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        up = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("range_test.pdf", large_pdf, "application/pdf"))],
        )
    assert up.status_code == 202
    pdf_id = up.json()["files"][0]["pdf_id"]
    wait_for_status(pdf_id, "ready", auth_headers, timeout=30)

    headers = {**auth_headers, "Range": "bytes=0-1023"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.get(f"/api/pdfs/{pdf_id}/stream", headers=headers)
    assert resp.status_code == 206
    assert resp.headers.get("content-range") is not None
    assert len(resp.content) == 1024


def test_stream_requires_auth(uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get(f"/api/pdfs/{pdf_id}/stream")
    assert resp.status_code == 401


def test_rename_pdf(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            f"/api/pdfs/{pdf_id}",
            headers=auth_headers,
            json={"name": "my-renamed.pdf"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "my-renamed.pdf"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r2 = client.get(f"/api/pdfs/{pdf_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["name"] == "my-renamed.pdf"

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM logs WHERE event = 'RENAME_SUCCESS' AND metadata->>'pdf_id' = %s",
        (pdf_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) >= 1
    conn2 = psycopg2.connect(DB_URL)
    cur2 = conn2.cursor()
    cur2.execute(
        "SELECT metadata FROM logs WHERE event = 'RENAME_SUCCESS' AND metadata->>'pdf_id' = %s LIMIT 1",
        (pdf_id,),
    )
    row = cur2.fetchone()
    cur2.close()
    conn2.close()
    meta = row[0] if row else {}
    assert "old_name" in meta or "new_name" in meta


def test_rename_without_pdf_extension(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            f"/api/pdfs/{pdf_id}",
            headers=auth_headers,
            json={"name": "no-extension"},
        )
    assert resp.status_code == 422


def test_soft_delete(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[2]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.delete(f"/api/pdfs/{pdf_id}", headers=auth_headers)
    assert resp.status_code == 204

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT deleted_at FROM pdfs WHERE id = %s", (pdf_id,))
    row = cur.fetchone()
    assert row is not None
    assert row[0] is not None

    cur.execute("SELECT id FROM pdfs WHERE id = %s", (pdf_id,))
    assert cur.fetchone() is not None
    cur.close()
    conn.close()

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r2 = client.get(f"/api/pdfs/{pdf_id}", headers=auth_headers)
    assert r2.status_code == 404


def test_deleted_pdf_not_in_list(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[
                ("files", ("del_a.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("del_b.pdf", sample_pdf_bytes, "application/pdf")),
            ],
        )
    assert resp.status_code == 202
    ids = [str(f["pdf_id"]) for f in resp.json()["files"]]
    id_a, id_b = ids[0], ids[1]
    for pid in ids:
        wait_for_status(pid, "ready", auth_headers, timeout=45)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.delete(f"/api/pdfs/{id_a}", headers=auth_headers)
        r = client.get("/api/pdfs", headers=auth_headers)
    assert r.status_code == 200
    returned_ids = [item["id"] for item in r.json()["items"]]
    assert id_a not in returned_ids
    assert id_b in returned_ids


def test_view_logs_emitted(auth_headers, uploaded_pdfs):
    pdf_id = uploaded_pdfs[0]
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        client.get(f"/api/pdfs/{pdf_id}/stream", headers=auth_headers)
    time.sleep(2)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT event, metadata->>'duration_ms' as duration_ms
        FROM logs
        WHERE metadata->>'pdf_id' = %s
          AND event IN ('VIEW_REQUEST_INITIATED', 'FILE_STREAM_COMPLETE')
        """,
        (pdf_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    events = [r[0] for r in rows]
    assert "VIEW_REQUEST_INITIATED" in events
    assert "FILE_STREAM_COMPLETE" in events
    for r in rows:
        if r[0] == "FILE_STREAM_COMPLETE":
            assert r[1] is not None and int(r[1]) >= 0
            break
