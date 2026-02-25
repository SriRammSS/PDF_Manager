"""E2E tests for the visual editor (edit operations)."""

import io

import httpx
import pikepdf
import pytest

from tests.conftest import (
    BASE_URL,
    auth_headers,
    extract_page_content,
    fresh_pdf_3page,
    fresh_user,
    wait_for_version,
)


def test_dimensions_endpoint(auth_headers, fresh_pdf_3page):
    """GET /api/pdfs/{pdf_id}/dimensions returns page dimensions."""
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/dimensions",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert len(pages) == 3
    assert all(p["width_pts"] > 0 and p["height_pts"] > 0 for p in pages)
    assert 500 < pages[0]["width_pts"] < 700


def test_text_operation(auth_headers, fresh_pdf_3page):
    """POST text op adds text to PDF content."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 0,
                    "x": 72.0,
                    "y": 700.0,
                    "text": "VisualEditorTest",
                    "font_family": "Helvetica",
                    "font_size": 14,
                    "bold": False,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"VisualEditorTest" in content


def test_bold_text(auth_headers, fresh_pdf_3page):
    """POST bold text uses Helvetica-Bold or HelveticaBold."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 0,
                    "x": 72.0,
                    "y": 700.0,
                    "text": "BoldTest",
                    "font_family": "Helvetica",
                    "font_size": 14,
                    "bold": True,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"HelveticaBold" in content or b"Helvetica-Bold" in content


def test_highlight_operation(auth_headers, fresh_pdf_3page):
    """POST highlight op adds rectangle, fill, and graphics state."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "highlight",
                    "page": 0,
                    "x": 100,
                    "y": 650,
                    "width": 200,
                    "height": 20,
                    "color_hex": "#FFFF00",
                    "opacity": 0.4,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"re" in content
    assert b"f\n" in content
    assert b"gs\n" in content


def test_erase_whiteout(auth_headers, fresh_pdf_3page):
    """POST erase with white fill adds white rectangle."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "erase",
                    "page": 0,
                    "x": 50,
                    "y": 600,
                    "width": 300,
                    "height": 40,
                    "fill_color": "#FFFFFF",
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"1 1 1 rg" in content


def test_erase_redact_black(auth_headers, fresh_pdf_3page):
    """POST erase with black fill adds black rectangle."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "erase",
                    "page": 0,
                    "x": 50,
                    "y": 550,
                    "width": 200,
                    "height": 30,
                    "fill_color": "#000000",
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"0 0 0 rg" in content


def test_shape_rectangle(auth_headers, fresh_pdf_3page):
    """POST shape rectangle adds re and S (stroke only)."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "shape",
                    "shape_type": "rectangle",
                    "page": 0,
                    "x": 100,
                    "y": 500,
                    "width": 150,
                    "height": 80,
                    "stroke_color": "#0000FF",
                    "fill_color": None,
                    "stroke_width": 2.0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"re\n" in content
    assert b"S\n" in content


def test_shape_line(auth_headers, fresh_pdf_3page):
    """POST shape line adds moveto and lineto."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "shape",
                    "shape_type": "line",
                    "page": 0,
                    "x": 50,
                    "y": 450,
                    "width": 300,
                    "height": 0,
                    "stroke_color": "#FF0000",
                    "stroke_width": 1.5,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b" m\n" in content or b" m " in content
    assert b" l\n" in content or b" l " in content


def test_draw_freehand(auth_headers, fresh_pdf_3page):
    """POST draw op adds path with moveto, lineto, stroke."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "draw",
                    "page": 0,
                    "path": "M 100 100 L 150 150 L 200 100 L 250 150",
                    "color_hex": "#00AA00",
                    "stroke_width": 3.0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b" m\n" in content
    assert b" l\n" in content
    assert b"S\n" in content


def test_all_op_types_one_request(auth_headers, fresh_pdf_3page):
    """5 ops in one request produce single version bump."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 0,
                    "x": 72,
                    "y": 700,
                    "text": "MultiOp",
                    "font_family": "Helvetica",
                    "font_size": 12,
                    "bold": False,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                },
                {
                    "type": "highlight",
                    "page": 0,
                    "x": 100,
                    "y": 650,
                    "width": 100,
                    "height": 15,
                    "color_hex": "#FFFF00",
                    "opacity": 0.4,
                },
                {
                    "type": "erase",
                    "page": 0,
                    "x": 50,
                    "y": 600,
                    "width": 80,
                    "height": 15,
                    "fill_color": "#FFFFFF",
                },
                {
                    "type": "shape",
                    "shape_type": "rectangle",
                    "page": 0,
                    "x": 100,
                    "y": 500,
                    "width": 80,
                    "height": 40,
                    "stroke_color": "#0000FF",
                    "fill_color": None,
                    "stroke_width": 1.5,
                },
                {
                    "type": "draw",
                    "page": 0,
                    "path": "M 50 50 L 100 100",
                    "color_hex": "#000000",
                    "stroke_width": 2.0,
                },
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    r2 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r2.status_code == 200
    assert r2.json()["version"] == 2


def test_multi_page_ops(auth_headers, fresh_pdf_3page):
    """Ops on pages 0, 1, 2 each add content to respective pages."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {"type": "text", "page": 0, "x": 72, "y": 700, "text": "P0"},
                {"type": "text", "page": 1, "x": 72, "y": 700, "text": "P1"},
                {"type": "text", "page": 2, "x": 72, "y": 700, "text": "P2"},
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    for page_idx in [0, 1, 2]:
        content = extract_page_content(fresh_pdf_3page, auth_headers, page_idx)
        assert len(content) > 0


def test_page_rotate(auth_headers, fresh_pdf_3page):
    """POST page rotate sets /Rotate to 90."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "page",
                    "action": "rotate",
                    "page": 0,
                    "rotate_degrees": 90,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    r2 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/stream",
        headers=auth_headers,
        timeout=30.0,
    )
    r2.raise_for_status()
    with pikepdf.open(io.BytesIO(r2.content)) as pdf:
        assert int(pdf.pages[0].get("/Rotate", 0)) == 90


def test_page_delete(auth_headers, fresh_pdf_3page):
    """POST page delete removes page 2, page_count becomes 2."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {"type": "page", "action": "delete", "page": 2}
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    r2 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r2.status_code == 200
    assert r2.json()["page_count"] == 2


def test_page_reorder(auth_headers, fresh_pdf_3page):
    """POST page reorder reorders pages, still 3 pages."""
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "page",
                    "action": "reorder",
                    "page": 0,
                    "new_order": [2, 0, 1],
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)
    r2 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r2.status_code == 200
    assert r2.json()["page_count"] == 3


def test_version_history_after_edits(auth_headers, fresh_pdf_3page):
    """Two edits create version history; original stream lacks new text."""
    r1 = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 0,
                    "x": 72,
                    "y": 700,
                    "text": "VisualEditorTest",
                    "font_family": "Helvetica",
                    "font_size": 12,
                    "bold": False,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r1.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)

    r2 = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "highlight",
                    "page": 0,
                    "x": 100,
                    "y": 650,
                    "width": 200,
                    "height": 20,
                    "color_hex": "#FFFF00",
                    "opacity": 0.4,
                }
            ]
        },
        timeout=10.0,
    )
    assert r2.status_code == 202
    wait_for_version(fresh_pdf_3page, 3, auth_headers, timeout=30)

    r3 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/versions",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r3.status_code == 200
    versions = r3.json()
    assert len(versions) >= 2
    versions_sorted = sorted(versions, key=lambda v: v["version"])
    assert versions_sorted == versions

    r4 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/versions/{versions_sorted[0]['id']}/stream",
        headers=auth_headers,
        timeout=30.0,
    )
    assert r4.status_code == 200
    assert r4.content[:4] == b"%PDF"
    with pikepdf.open(io.BytesIO(r4.content)) as pdf:
        page = pdf.pages[0]
        contents = page.get("/Contents")
        if contents is None:
            orig_content = b""
        elif isinstance(contents, pikepdf.Array):
            orig_content = b"".join(c.read_bytes() for c in contents)
        else:
            orig_content = contents.read_bytes()
    assert b"VisualEditorTest" not in orig_content


def test_original_preserved_on_failure(auth_headers, fresh_pdf_3page):
    """Bad op (page 9999) leaves version unchanged after task fails."""
    r0 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r0.status_code == 200
    orig_version = r0.json()["version"]

    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 9999,
                    "x": 72,
                    "y": 700,
                    "text": "BadPage",
                    "font_family": "Helvetica",
                    "font_size": 12,
                    "bold": False,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 202

    import time
    time.sleep(20)

    r2 = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r2.status_code == 200
    assert r2.json()["version"] == orig_version


def test_max_500_ops_limit(auth_headers, fresh_pdf_3page):
    """POST with 501 ops returns 422."""
    ops = [
        {
            "type": "erase",
            "page": 0,
            "x": float(i),
            "y": 0,
            "width": 1,
            "height": 1,
            "fill_color": "#FFFFFF",
        }
        for i in range(501)
    ]
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={"operations": ops},
        timeout=10.0,
    )
    assert r.status_code == 422


def test_edit_ownership(auth_headers, fresh_pdf_3page, fresh_user):
    """Second user editing first user's PDF gets 403."""
    second_headers = fresh_user["headers"]
    r = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=second_headers,
        json={
            "operations": [
                {
                    "type": "text",
                    "page": 0,
                    "x": 72,
                    "y": 700,
                    "text": "Hacked",
                    "font_family": "Helvetica",
                    "font_size": 12,
                    "bold": False,
                    "italic": False,
                    "color_hex": "#000000",
                    "rotation": 0,
                }
            ]
        },
        timeout=10.0,
    )
    assert r.status_code == 403


def test_text_content_endpoint(auth_headers, fresh_pdf_3page):
    """GET /api/pdfs/{pdf_id}/text-content?page=0 returns text blocks."""
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/text-content?page=0",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert isinstance(blocks, list)
    if len(blocks) > 0:
        b = blocks[0]
        assert all(k in b for k in ["text", "x", "y", "width", "height", "font_family", "font_size", "bold", "italic"])
        assert b["font_family"] in ["Helvetica", "Times-Roman", "Courier"]
        assert b["font_size"] > 0
        assert b["x"] >= 0 and b["y"] >= 0


def test_text_content_invalid_page(auth_headers, fresh_pdf_3page):
    """GET text-content?page=9999 returns empty blocks gracefully."""
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/text-content?page=9999",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r.status_code == 200
    assert r.json()["blocks"] == []


def test_text_content_requires_auth(fresh_pdf_3page):
    """GET text-content without auth returns 401."""
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/text-content?page=0",
        timeout=10.0,
    )
    assert r.status_code == 401


def test_text_content_wrong_owner(auth_headers, fresh_pdf_3page, fresh_user):
    """Second user GET text-content on first user's PDF returns 403."""
    second_headers = fresh_user["headers"]
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/text-content?page=0",
        headers=second_headers,
        timeout=10.0,
    )
    assert r.status_code == 403


def test_edit_text_full_flow(auth_headers, fresh_pdf_3page):
    """Edit text: get blocks, send erase+text ops, verify new text in content."""
    r = httpx.get(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/text-content?page=0",
        headers=auth_headers,
        timeout=10.0,
    )
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    if len(blocks) == 0:
        pytest.skip("No extractable text on page 0 of test PDF")
    block = blocks[0]

    ops = [
        {
            "type": "erase",
            "page": 0,
            "x": block["x"] - 1,
            "y": block["y"] - 1,
            "width": block["width"] + 2,
            "height": block["height"] + 2,
            "fill_color": "#FFFFFF",
        },
        {
            "type": "text",
            "page": 0,
            "x": block["x"],
            "y": block["y"],
            "text": "REPLACED_TEXT_12345",
            "font_family": block["font_family"],
            "font_size": block["font_size"],
            "bold": block["bold"],
            "italic": block["italic"],
            "color_hex": "#000000",
            "rotation": 0,
        },
    ]
    r2 = httpx.post(
        f"{BASE_URL}/api/pdfs/{fresh_pdf_3page}/edit",
        headers=auth_headers,
        json={"operations": ops},
        timeout=10.0,
    )
    assert r2.status_code == 202
    wait_for_version(fresh_pdf_3page, 2, auth_headers, timeout=30)

    content = extract_page_content(fresh_pdf_3page, auth_headers, 0)
    assert b"REPLACED_TEXT_12345" in content
    assert b"1 1 1 rg" in content
