"""E2E tests for Authentication module."""

import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import pytest
import redis
from jose import jwt

BASE_URL = "http://localhost:8000"
DB_URL = "postgresql://postgres:Krishn%4062001@localhost:5433/pdf_management_app"
REDIS_URL = "redis://localhost:6379/0"


def _unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:12]}@test.example"


def _delete_user_by_email(email: str) -> None:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()


def test_signup_success():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            resp = client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test User", "password": "SecurePass123!"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["email"] == email
        assert data["display_name"] == "Test User"

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT hashed_password FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        hashed = row[0]
        assert hashed != "SecurePass123!"

        time.sleep(3)
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM logs WHERE event = 'SIGNUP_SUCCESS' AND metadata->>'email' = %s",
            (email,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        assert len(rows) >= 1
    finally:
        _delete_user_by_email(email)


def test_signup_duplicate_email():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            resp1 = client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "User 1", "password": "SecurePass123!"},
            )
            assert resp1.status_code == 201
            resp2 = client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "User 2", "password": "OtherPass456!"},
            )
        assert resp2.status_code == 409

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE email = %s", (email,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert count == 1
    finally:
        _delete_user_by_email(email)


def test_signup_weak_password():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/auth/signup",
            json={"email": _unique_email(), "display_name": "Test", "password": "abc"},
        )
    assert resp.status_code == 422


def test_login_success():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test", "password": "SecurePass123!"},
            )
            resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "SecurePass123!"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data and data["access_token"]
        assert "refresh_token" in data and data["refresh_token"]

        payload = jwt.get_unverified_claims(data["access_token"])
        assert "sub" in payload

        time.sleep(1)
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT * FROM logs WHERE event = 'LOGIN_SUCCESS'")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        assert len(rows) >= 1
    finally:
        _delete_user_by_email(email)


def test_login_wrong_password():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test", "password": "SecurePass123!"},
            )
            resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "WrongPassword123!"},
            )
        assert resp.status_code == 401

        time.sleep(1)
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT * FROM logs WHERE event = 'LOGIN_BAD_PASSWORD'")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        assert len(rows) >= 1
    finally:
        _delete_user_by_email(email)


def test_login_unknown_email():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.post(
            "/api/auth/login",
            json={"email": "nonexistent@test.example", "password": "SomePass123!"},
        )
    assert resp.status_code == 401

    time.sleep(1)
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM logs WHERE event = 'LOGIN_USER_NOT_FOUND'")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert len(rows) >= 1


def test_logout_invalidates_refresh_token():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test", "password": "SecurePass123!"},
            )
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "SecurePass123!"},
            )
        access_token = login_resp.json()["access_token"]
        refresh_token = login_resp.json()["refresh_token"]

        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            logout_resp = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"refresh_token": refresh_token},
            )
        assert logout_resp.status_code == 200

        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            refresh_resp = client.post(
                "/api/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        assert refresh_resp.status_code == 401

        jti = jwt.get_unverified_claims(refresh_token).get("jti")
        assert jti
        r = redis.from_url(REDIS_URL)
        assert r.exists(f"revoked:{jti}") == 1
    finally:
        _delete_user_by_email(email)


def test_refresh_token_success():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test", "password": "SecurePass123!"},
            )
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "SecurePass123!"},
            )
        original_access = login_resp.json()["access_token"]
        refresh_token = login_resp.json()["refresh_token"]

        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            refresh_resp = client.post(
                "/api/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert "access_token" in data
        assert data["access_token"] != original_access
    finally:
        _delete_user_by_email(email)


def test_protected_route_without_token():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get("/api/users/me")
    assert resp.status_code in (401, 422)


def test_protected_route_with_expired_token():
    from app.core.config import get_settings
    secret = get_settings().secret_key

    expire = datetime.now(timezone.utc) - timedelta(seconds=1)
    payload = {
        "sub": str(uuid.uuid4()),
        "exp": expire,
        "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
        "type": "access",
    }
    expired_token = jwt.encode(payload, secret, algorithm="HS256")

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        resp = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
    assert resp.status_code == 401


def test_request_id_on_all_auth_responses():
    email = _unique_email()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            signup_resp = client.post(
                "/api/auth/signup",
                json={"email": email, "display_name": "Test", "password": "SecurePass123!"},
            )
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "SecurePass123!"},
            )
            access_token = login_resp.json()["access_token"]
            refresh_token = login_resp.json()["refresh_token"]
            logout_resp = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"refresh_token": refresh_token},
            )

        for name, resp in [("signup", signup_resp), ("login", login_resp), ("logout", logout_resp)]:
            rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
            assert rid is not None, f"Missing x-request-id on {name}"
            uuid.UUID(rid)
    finally:
        _delete_user_by_email(email)
