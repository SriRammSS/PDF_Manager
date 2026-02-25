"""E2E tests for User Profile module."""

import json
import time
from uuid import uuid4

import httpx
import psycopg2
import pytest

from tests.conftest import BASE_URL, DB_URL

DEFAULT_PASSWORD = "TestPass1"


def test_get_my_profile(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/users/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert "display_name" in data
    assert "created_at" in data


def test_get_profile_requires_auth():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_update_display_name(fresh_user):
    headers = fresh_user["headers"]
    user_id = fresh_user["user_id"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"display_name": "New Name"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "New Name"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        get_resp = client.get("/api/users/me", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["display_name"] == "New Name"

    time.sleep(2)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM logs WHERE event = 'DISPLAY_NAME_CHANGED' AND user_id = %s",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) == 1


def test_update_display_name_whitespace_only(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"display_name": "   "},
        )
    assert resp.status_code == 422


def test_update_display_name_too_short(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"display_name": "A"},
        )
    assert resp.status_code == 422


def test_change_email_success(fresh_user):
    headers = fresh_user["headers"]
    user_id = fresh_user["user_id"]
    old_email = fresh_user["email"]
    new_email = f"changed_{uuid4().hex[:6]}@test.com"

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"email": new_email, "current_password": DEFAULT_PASSWORD},
        )
    assert resp.status_code == 200
    assert resp.json()["email"] == new_email

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        login_new = client.post(
            "/api/auth/login",
            json={"email": new_email, "password": DEFAULT_PASSWORD},
        )
        login_old = client.post(
            "/api/auth/login",
            json={"email": old_email, "password": DEFAULT_PASSWORD},
        )
    assert login_new.status_code == 200
    assert login_old.status_code == 401

    time.sleep(2)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM logs WHERE event = 'EMAIL_CHANGED' AND user_id = %s",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) == 1


def test_change_email_without_current_password(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"email": "whatever@test.com"},
        )
    assert resp.status_code == 422


def test_change_email_wrong_current_password(fresh_user):
    headers = fresh_user["headers"]
    original_email = fresh_user["email"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"email": "new@test.com", "current_password": "WRONGPASSWORD"},
        )
    assert resp.status_code == 401

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        get_resp = client.get("/api/users/me", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == original_email


def test_change_email_already_taken(fresh_user):
    headers = fresh_user["headers"]
    email_b = f"other_{uuid4().hex[:6]}@test.com"
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post(
            "/api/auth/signup",
            json={"email": email_b, "display_name": "Other", "password": DEFAULT_PASSWORD},
        )
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            resp = client.patch(
                "/api/users/me",
                headers=headers,
                json={"email": email_b, "current_password": DEFAULT_PASSWORD},
            )
        assert resp.status_code == 409
    finally:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email = %s", (email_b,))
        conn.commit()
        cur.close()
        conn.close()


def test_change_password_success(fresh_user):
    headers = fresh_user["headers"]
    user_id = fresh_user["user_id"]
    email = fresh_user["email"]

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"current_password": DEFAULT_PASSWORD, "new_password": "NewPass99"},
        )
    assert resp.status_code == 200

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        login_new = client.post(
            "/api/auth/login",
            json={"email": email, "password": "NewPass99"},
        )
        login_old = client.post(
            "/api/auth/login",
            json={"email": email, "password": DEFAULT_PASSWORD},
        )
    assert login_new.status_code == 200
    assert login_old.status_code == 401

    time.sleep(2)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM logs WHERE event = 'PASSWORD_CHANGED' AND user_id = %s",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.execute(
        "SELECT metadata, error FROM logs WHERE event = 'PASSWORD_CHANGED' AND user_id = %s",
        (user_id,),
    )
    log_rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) == 1
    for row in log_rows:
        combined = json.dumps(row, default=str)
        assert "TestPass1" not in combined
        assert "NewPass99" not in combined


def test_change_password_weak_new_password(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"current_password": DEFAULT_PASSWORD, "new_password": "weak"},
        )
    assert resp.status_code == 422


def test_change_password_same_as_current(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.patch(
            "/api/users/me",
            headers=headers,
            json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
        )
    assert resp.status_code == 422


def test_empty_body_update(fresh_user):
    headers = fresh_user["headers"]
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        get_before = client.get("/api/users/me", headers=headers)
        patch_resp = client.patch("/api/users/me", headers=headers, json={})
        get_after = client.get("/api/users/me", headers=headers)
    assert patch_resp.status_code == 200
    assert get_before.json() == get_after.json()
