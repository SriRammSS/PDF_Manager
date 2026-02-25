"""E2E tests for Live Log Viewer module."""

import json
import threading
import time
from uuid import uuid4

import httpx
import psycopg2
import pytest

from tests.conftest import BASE_URL, DB_URL, auth_headers, sample_pdf_bytes, wait_for_status


def test_log_history_endpoint(auth_headers):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post("/api/auth/login", json={"email": "x@y.com", "password": "x"})
        resp = client.get("/api/logs/?page=1&size=10", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "timestamp" in item
        assert "level" in item
        assert "event" in item


def test_log_history_filter_by_level(auth_headers):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/logs/?level=INFO&page=1&size=50", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["level"] == "INFO"


def test_log_history_filter_by_module(auth_headers):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/logs/?module=auth_service&page=1&size=50", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["module"] == "auth_service"


def test_log_history_pagination(auth_headers):
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        for _ in range(5):
            client.get("/api/users/me", headers=auth_headers)
    time.sleep(2)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        r1 = client.get("/api/logs/?page=1&size=5", headers=auth_headers)
        r2 = client.get("/api/logs/?page=2&size=5", headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    ids1 = {item["id"] for item in r1.json()["items"]}
    ids2 = {item["id"] for item in r2.json()["items"]}
    assert len(ids1 & ids2) == 0


def test_log_history_requires_auth():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/logs/?page=1&size=10")
    assert resp.status_code == 401


def test_sse_stream_connects(auth_headers):
    token = auth_headers["Authorization"].replace("Bearer ", "")
    url = f"{BASE_URL}/api/logs/stream?token={token}"
    collected = []
    done = threading.Event()

    def collect():
        with httpx.Client(timeout=10.0) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    done.set()
                    return
                for line in resp.iter_lines():
                    if done.is_set():
                        break
                    collected.append(line)
                    if len(collected) >= 3:
                        break

    t = threading.Thread(target=collect)
    t.start()
    time.sleep(0.5)
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        client.post("/api/auth/login", json={"email": "x@y.com", "password": "x"})
    t.join(timeout=5)

    assert len(collected) >= 1
    for line in collected:
        if line.startswith("data: "):
            payload = line[6:]
            try:
                json.loads(payload)
            except json.JSONDecodeError:
                pass
            else:
                break
    else:
        assert any("data:" in line for line in collected)


def test_sse_stream_receives_login_event(auth_headers):
    email = f"login_{uuid4().hex[:8]}@test.com"
    password = "TestPass1"
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post("/api/auth/signup", json={"email": email, "display_name": "T", "password": password})

    token = auth_headers["Authorization"].replace("Bearer ", "")
    url = f"{BASE_URL}/api/logs/stream?token={token}"
    collected = []
    done = threading.Event()

    def collect():
        with httpx.Client(timeout=8.0) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    done.set()
                    return
                for line in resp.iter_lines():
                    if done.is_set():
                        break
                    collected.append(line)

    t = threading.Thread(target=collect)
    t.start()
    time.sleep(1)
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        client.post("/api/auth/login", json={"email": email, "password": password})
    time.sleep(3)
    done.set()
    t.join(timeout=2)

    events = []
    for line in collected:
        if line.startswith("data: "):
            try:
                obj = json.loads(line[6:])
                events.append(obj.get("event"))
            except json.JSONDecodeError:
                pass
    assert "LOGIN_SUCCESS" in events

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()


def test_sse_stream_receives_upload_event(auth_headers, sample_pdf_bytes):
    token = auth_headers["Authorization"].replace("Bearer ", "")
    url = f"{BASE_URL}/api/logs/stream?token={token}"
    collected = []
    done = threading.Event()

    def collect():
        with httpx.Client(timeout=20.0) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    done.set()
                    return
                for line in resp.iter_lines():
                    if done.is_set():
                        break
                    collected.append(line)

    t = threading.Thread(target=collect)
    t.start()
    time.sleep(1)
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("up.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    time.sleep(5)
    done.set()
    t.join(timeout=2)

    events = []
    for line in collected:
        if line.startswith("data: "):
            try:
                obj = json.loads(line[6:])
                events.append(obj.get("event"))
            except json.JSONDecodeError:
                pass
    assert "UPLOAD_RECEIVED" in events or "UPLOAD_FILES_RECEIVED" in events or any(
        "UPLOAD" in e for e in events if e
    )
    assert any("TASK" in (e or "") for e in events)


def test_sse_keepalive_sent(auth_headers):
    token = auth_headers["Authorization"].replace("Bearer ", "")
    url = f"{BASE_URL}/api/logs/stream?token={token}"
    collected = []

    def collect():
        with httpx.Client(timeout=25.0) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return
                for chunk in resp.iter_bytes():
                    collected.append(chunk)
                    if b": ping" in b"".join(collected):
                        return

    t = threading.Thread(target=collect)
    t.start()
    t.join(timeout=25)
    combined = b"".join(collected)
    assert b": ping" in combined


def test_sse_invalid_token_rejected():
    url = f"{BASE_URL}/api/logs/stream?token=this_is_invalid"
    with httpx.Client(timeout=5.0) as client:
        resp = client.get(url)
    assert resp.status_code == 401


def test_log_metadata_jsonb_queryable(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=45.0) as client:
        r = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("m.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    assert r.status_code == 202
    pdf_id = str(r.json()["files"][0]["pdf_id"])
    wait_for_status(pdf_id, "ready", auth_headers, timeout=45)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM logs WHERE metadata->>'pdf_id' = %s", (pdf_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) >= 1


def test_celery_logs_in_db(auth_headers, sample_pdf_bytes):
    with httpx.Client(base_url=BASE_URL, timeout=45.0) as client:
        client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("c.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    time.sleep(8)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT task_id, event, duration_ms FROM logs WHERE task_id IS NOT NULL ORDER BY timestamp"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    task_events = {}
    for task_id, event, duration_ms in rows:
        if task_id not in task_events:
            task_events[task_id] = []
        task_events[task_id].append((event, duration_ms))

    assert len(rows) >= 2
    found_completed = False
    for task_id, evts in task_events.items():
        events = [e[0] for e in evts]
        if "TASK_STARTED" in events and "TASK_COMPLETED" in events:
            for e, d in evts:
                if e == "TASK_COMPLETED" and d and d > 0:
                    found_completed = True
                    break
    assert found_completed
