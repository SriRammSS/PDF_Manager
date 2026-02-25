"""Pytest configuration and fixtures."""

import time
from uuid import uuid4

import httpx
import psycopg2
import pytest

DB_URL = "postgresql://postgres:Krishn%4062001@localhost:5433/pdf_management_app"
BASE_URL = "http://localhost:8000"


def _delete_user_by_id(user_id: str) -> None:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM pdf_versions WHERE pdf_id IN (SELECT id FROM pdfs WHERE owner_id = %s)",
        (user_id,),
    )
    cur.execute("DELETE FROM pdfs WHERE owner_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture
def auth_headers():
    email = f"testuser_{uuid4().hex[:8]}@test.com"
    password = "TestPass1"
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post(
            "/api/auth/signup",
            json={"email": email, "display_name": "Test", "password": password},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
    token = resp.json()["access_token"]
    from jose import jwt
    payload = jwt.get_unverified_claims(token)
    user_id = payload.get("sub")
    yield {"Authorization": f"Bearer {token}"}
    if user_id:
        _delete_user_by_id(user_id)


@pytest.fixture
def fresh_user():
    """Creates a user with known password, returns {headers, email, password, user_id}."""
    email = f"profile_{uuid4().hex[:8]}@test.com"
    password = "TestPass1"
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        client.post(
            "/api/auth/signup",
            json={"email": email, "display_name": "Test", "password": password},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
    token = resp.json()["access_token"]
    from jose import jwt
    payload = jwt.get_unverified_claims(token)
    user_id = payload.get("sub")
    yield {
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
        "password": password,
        "user_id": user_id,
    }
    if user_id:
        _delete_user_by_id(user_id)


@pytest.fixture
def sample_pdf_bytes():
    import io
    import pikepdf
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 612, 792],
            Resources=pikepdf.Dictionary(),
            Contents=pikepdf.Stream(
                pdf, b"BT /F1 12 Tf 72 720 Td (Hello PDF) Tj ET"
            ),
        )
    )
    pdf.pages.append(page)
    buf = io.BytesIO()
    pdf.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.fixture
def sample_3page_pdf_bytes():
    """3-page PDF for visual editor tests (Letter size ~612x792).
    Uses proper Font resource so pdfminer can extract text."""
    import io
    import pikepdf
    pdf = pikepdf.new()
    font_res = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
            )
        )
    )
    for i in range(3):
        page = pikepdf.Page(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Page,
                MediaBox=[0, 0, 612, 792],
                Resources=font_res,
                Contents=pikepdf.Stream(
                    pdf, f"BT /F1 12 Tf 72 720 Td (Page {i + 1}) Tj ET".encode()
                ),
            )
        )
        pdf.pages.append(page)
    buf = io.BytesIO()
    pdf.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.fixture
def fresh_pdf_3page(auth_headers, sample_3page_pdf_bytes):
    """Uploads 3-page PDF, waits for 'ready', returns pdf_id string."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("fresh_3page.pdf", sample_3page_pdf_bytes, "application/pdf"))],
        )
    assert resp.status_code == 202
    pdf_id = str(resp.json()["files"][0]["pdf_id"])
    wait_for_status(pdf_id, "ready", auth_headers, timeout=45)
    return pdf_id


def extract_page_content(pdf_id: str, headers: dict, page_index: int = 0) -> bytes:
    """Extract raw content stream bytes from a PDF page."""
    import io
    import pikepdf
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{pdf_id}/stream",
        headers=headers,
        timeout=30.0,
    )
    r.raise_for_status()
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        page = pdf.pages[page_index]
        contents = page.get("/Contents")
        if contents is None:
            return b""
        if isinstance(contents, pikepdf.Array):
            return b"".join(s.read_bytes() for s in contents)
        return contents.read_bytes() if contents else b""


def wait_for_status(pdf_id, target_status, headers, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(
            f"{BASE_URL}/api/pdfs/{pdf_id}",
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 200 and r.json().get("status") == target_status:
            return r.json()
        time.sleep(1)
    raise TimeoutError(
        f"PDF {pdf_id} never reached status={target_status}"
    )


def wait_for_version(pdf_id, expected_version, headers, timeout=30):
    """Poll GET /api/pdfs/{pdf_id} until version == expected_version."""
    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(
            f"{BASE_URL}/api/pdfs/{pdf_id}",
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("version") == expected_version:
                return data
        time.sleep(1)
    raise TimeoutError(
        f"PDF {pdf_id} never reached version={expected_version}"
    )


@pytest.fixture
def fresh_pdf(auth_headers, sample_pdf_bytes):
    """Uploads 1 PDF, waits for 'ready', returns pdf_id string."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[("files", ("fresh.pdf", sample_pdf_bytes, "application/pdf"))],
        )
    assert resp.status_code == 202
    pdf_id = str(resp.json()["files"][0]["pdf_id"])
    wait_for_status(pdf_id, "ready", auth_headers, timeout=45)
    return pdf_id


@pytest.fixture
def uploaded_pdfs(auth_headers, sample_pdf_bytes):
    """Uploads 3 PDFs and waits for all to be 'ready'. Returns list of pdf_id strings."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post(
            "/api/pdfs/upload",
            headers=auth_headers,
            files=[
                ("files", ("v1.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("v2.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("v3.pdf", sample_pdf_bytes, "application/pdf")),
            ],
        )
    assert resp.status_code == 202
    pdf_ids = [str(f["pdf_id"]) for f in resp.json()["files"]]
    for pdf_id in pdf_ids:
        wait_for_status(pdf_id, "ready", auth_headers, timeout=45)
    return pdf_ids
