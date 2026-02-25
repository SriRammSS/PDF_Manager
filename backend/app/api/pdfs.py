"""PDFs API router."""

import os
import re
import time
from pathlib import Path
from typing import Annotated
from uuid import UUID

import pikepdf
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.limiter import _upload_key, limiter
from app.core.logging import get_logger, log_event
from app.db.models import PDF, PDFVersion, User
from app.db.session import get_db
from app.schemas.pdf import (
    EditRequest,
    PDFListResponse,
    PDFResponse,
    RenameRequest,
    TaskStatusResponse,
    UploadResponse,
    UploadResponseItem,
    VersionResponse,
)
from app.services.pdf_service import get_pdf_or_raise, list_pdfs, rename_pdf, soft_delete_pdf
from app.services.storage_service import save_upload
from app.tasks.celery_app import celery_app
from app.tasks.pdf_tasks import process_uploaded_pdf, save_edited_pdf

router = APIRouter(prefix="/pdfs", tags=["pdfs"])
logger = get_logger("api.pdfs")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=202,
)
@limiter.limit("10/minute", key_func=_upload_key)
async def upload_pdfs(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    files: Annotated[list[UploadFile], File(alias="files")] = [],
):
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    items: list[UploadResponseItem] = []

    pending: list[tuple[PDF, str, str]] = []  # (pdf, storage_path, filename)

    for file in files:
        if not file.filename:
            continue
        filename = file.filename

        if not (
            (file.content_type or "").startswith("application/pdf")
            or filename.lower().endswith(".pdf")
        ):
            raise HTTPException(422, f"{filename}: invalid content type")

        all_bytes = await file.read()
        if all_bytes[:4] != b"%PDF":
            raise HTTPException(422, f"{filename} is not a valid PDF")

        if len(all_bytes) > max_bytes:
            raise HTTPException(
                422,
                f"{filename} exceeds size limit",
            )

        storage_path = await save_upload(
            all_bytes, filename, str(current_user.id)
        )

        pdf = PDF(
            owner_id=current_user.id,
            name=filename,
            storage_path=storage_path,
            size_bytes=len(all_bytes),
            status="pending",
        )
        db.add(pdf)
        await db.flush()
        pending.append((pdf, storage_path, filename))

    await db.commit()

    for pdf, storage_path, filename in pending:
        log_event(
            logger,
            "UPLOAD_RECEIVED",
            user_id=str(current_user.id),
            metadata={"pdf_id": str(pdf.id), "filename": filename},
        )
        task = process_uploaded_pdf.delay(
            str(pdf.id), storage_path, str(current_user.id)
        )
        log_event(
            logger,
            "TASK_ENQUEUED",
            user_id=str(current_user.id),
            task_id=task.id,
            metadata={"pdf_id": str(pdf.id), "filename": filename},
        )
        items.append(
            UploadResponseItem(
                pdf_id=pdf.id,
                filename=filename,
                status="pending",
                task_id=task.id,
            )
        )

    return UploadResponse(files=items, total=len(items))


@router.get("", response_model=PDFListResponse)
async def list_pdf_files(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    size: int = Query(default=20, le=100),
):
    result = await list_pdfs(db, current_user.id, page, size)
    log_event(
        logger,
        "PDF_LIST_FETCHED",
        user_id=str(current_user.id),
        metadata={"page": page, "size": size, "total": result.total},
    )
    return result


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    result = AsyncResult(task_id, app=celery_app)
    log_event(
        logger,
        "TASK_STATUS_POLLED",
        user_id=str(current_user.id),
        metadata={"task_id": task_id, "state": result.state},
    )
    task_result = None
    if result.ready():
        try:
            task_result = result.result
        except Exception:
            task_result = None
    return TaskStatusResponse(
        task_id=task_id,
        state=result.state,
        result=task_result,
        progress=None,
    )


@router.post("/{pdf_id}/edit", status_code=202)
async def edit_pdf(
    pdf_id: str,
    body: EditRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pdf = await get_pdf_or_raise(db, pdf_id, current_user.id)
    op_breakdown = {
        t: sum(1 for o in body.operations if o.type == t)
        for t in ["text", "highlight", "erase", "shape", "draw", "page"]
    }
    log_event(
        logger,
        "EDIT_REQUEST_RECEIVED",
        user_id=str(current_user.id),
        metadata={
            "pdf_id": pdf_id,
            "total_ops": len(body.operations),
            "breakdown": op_breakdown,
        },
    )
    task = save_edited_pdf.delay(
        pdf_id,
        str(current_user.id),
        [op.model_dump() for op in body.operations],
        body.comment,
    )
    return JSONResponse(
        status_code=202,
        content={
            "pdf_id": pdf_id,
            "version": pdf.version,
            "task_id": task.id,
        },
    )


@router.get("/{pdf_id}/versions", response_model=list[VersionResponse])
async def list_pdf_versions(
    pdf_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await get_pdf_or_raise(db, pdf_id, current_user.id)
    result = await db.execute(
        select(PDFVersion)
        .where(PDFVersion.pdf_id == UUID(pdf_id))
        .order_by(PDFVersion.version.asc())
    )
    rows = result.scalars().all()
    log_event(
        logger,
        "VERSION_HISTORY_FETCHED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id, "count": len(rows)},
    )
    return [VersionResponse.model_validate(r) for r in rows]


@router.get("/{pdf_id}/versions/{version_id}/stream")
async def stream_pdf_version(
    pdf_id: str,
    version_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await get_pdf_or_raise(db, pdf_id, current_user.id)
    result = await db.execute(
        select(PDFVersion).where(
            PDFVersion.id == UUID(version_id),
            PDFVersion.pdf_id == UUID(pdf_id),
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(404, "Version not found")
    log_event(
        logger,
        "VERSION_STREAM_FETCHED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id, "version_id": version_id},
    )
    file_path = str(Path(version.storage_path).resolve())
    if not os.path.exists(file_path):
        raise HTTPException(404, "Version file not found on storage")
    file_size = os.path.getsize(file_path)

    range_header = request.headers.get("Range")
    start, end = 0, file_size - 1
    status_code = 200
    chunk_size = file_size

    if range_header:
        m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
        if m:
            s, e = m.group(1), m.group(2)
            start = int(s) if s else 0
            end = int(e) if e else file_size - 1
            end = min(end, file_size - 1)
            start = min(start, end)
            chunk_size = end - start + 1
            status_code = 206

    t0 = time.perf_counter()
    with open(file_path, "rb") as f:
        f.seek(start)
        content = f.read(chunk_size)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    log_event(
        logger,
        "FILE_STREAM_COMPLETE",
        user_id=str(current_user.id),
        metadata={
            "pdf_id": pdf_id,
            "bytes_transferred": len(content),
            "duration_ms": duration_ms,
        },
    )

    headers = {
        "Content-Disposition": f'inline; filename="v{version.version}_{version_id[:8]}.pdf"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(content)),
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return Response(
        content=content,
        media_type="application/pdf",
        status_code=status_code,
        headers=headers,
    )


@router.get("/{pdf_id}/stream")
async def stream_pdf(
    pdf_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pdf = await get_pdf_or_raise(db, pdf_id, current_user.id)
    log_event(
        logger,
        "VIEW_REQUEST_INITIATED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id, "name": pdf.name},
    )
    file_path = str(Path(pdf.storage_path).resolve())
    if not os.path.exists(file_path):
        raise HTTPException(404, "PDF file not found on storage")
    file_size = os.path.getsize(file_path)

    range_header = request.headers.get("Range")
    start, end = 0, file_size - 1
    status_code = 200
    chunk_size = file_size

    if range_header:
        m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
        if m:
            s, e = m.group(1), m.group(2)
            start = int(s) if s else 0
            end = int(e) if e else file_size - 1
            end = min(end, file_size - 1)
            start = min(start, end)
            chunk_size = end - start + 1
            status_code = 206

    t0 = time.perf_counter()
    with open(file_path, "rb") as f:
        f.seek(start)
        content = f.read(chunk_size)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    log_event(
        logger,
        "FILE_STREAM_COMPLETE",
        user_id=str(current_user.id),
        metadata={
            "pdf_id": pdf_id,
            "bytes_transferred": len(content),
            "duration_ms": duration_ms,
        },
    )

    headers = {
        "Content-Disposition": f'inline; filename="{pdf.name}"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(content)),
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return Response(
        content=content,
        media_type="application/pdf",
        status_code=status_code,
        headers=headers,
    )


@router.get("/{pdf_id}", response_model=PDFResponse)
async def get_pdf(
    pdf_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pdf = await get_pdf_or_raise(db, pdf_id, current_user.id)
    log_event(
        logger,
        "PDF_DETAIL_FETCHED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id},
    )
    return PDFResponse.model_validate(pdf)


def _extract_text_blocks(pdf_path: str, page_index: int) -> list:
    """Extract text blocks with positions using pdfminer."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextBox, LTTextLine, LTChar

    blocks = []
    with open(pdf_path, "rb") as f:
        pages = list(extract_pages(f))
        if page_index >= len(pages):
            return []
        page_layout = pages[page_index]
        page_height = page_layout.height

        for element in page_layout:
            if not isinstance(element, LTTextBox):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                text = line.get_text().strip()
                if not text:
                    continue

                chars = [c for c in line if isinstance(c, LTChar)]
                if not chars:
                    continue

                raw_font = chars[0].fontname or ""
                font_size = round(chars[0].size, 1)

                fl = raw_font.lower()
                if any(k in fl for k in ["times", "roman", "serif", "garamond", "georgia"]):
                    font_family = "Times-Roman"
                elif any(k in fl for k in ["courier", "mono", "consolas", "code"]):
                    font_family = "Courier"
                else:
                    font_family = "Helvetica"

                bold = any(k in fl for k in ["bold", "heavy", "black", "demi"])
                italic = any(k in fl for k in ["italic", "oblique", "slant"])

                x0, y0, x1, y1 = line.bbox

                blocks.append({
                    "text": text,
                    "x": round(x0, 2),
                    "y": round(y0, 2),
                    "width": round(x1 - x0, 2),
                    "height": round(y1 - y0, 2),
                    "font_family": font_family,
                    "font_size": font_size,
                    "bold": bold,
                    "italic": italic,
                    "raw_font": raw_font,
                })
    return blocks


@router.get("/{pdf_id}/text-content")
async def get_pdf_text_content(
    pdf_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    page: int = Query(0, ge=0, description="0-indexed page"),
):
    pdf_obj = await get_pdf_or_raise(db, pdf_id, current_user.id)
    file_path = str(Path(pdf_obj.storage_path).resolve())
    blocks = _extract_text_blocks(file_path, page)
    log_event(
        logger,
        "TEXT_CONTENT_EXTRACTED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id, "page": page, "block_count": len(blocks)},
    )
    return JSONResponse({"page": page, "blocks": blocks})


@router.get("/{pdf_id}/dimensions")
async def get_pdf_dimensions(
    pdf_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pdf_obj = await get_pdf_or_raise(db, pdf_id, current_user.id)
    pages_info = []
    with pikepdf.open(str(Path(pdf_obj.storage_path).resolve())) as pdf:
        for i, page in enumerate(pdf.pages):
            mb = page.get("/MediaBox", [0, 0, 612, 792])
            pages_info.append(
                {
                    "page": i,
                    "width_pts": float(mb[2]) - float(mb[0]),
                    "height_pts": float(mb[3]) - float(mb[1]),
                }
            )
    log_event(
        logger,
        "DIMENSIONS_FETCHED",
        user_id=str(current_user.id),
        metadata={"pdf_id": pdf_id, "page_count": len(pages_info)},
    )
    return {"pages": pages_info}


@router.patch("/{pdf_id}", response_model=PDFResponse)
async def update_pdf_name(
    pdf_id: str,
    body: RenameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pdf = await rename_pdf(db, pdf_id, current_user.id, body.name)
    return PDFResponse.model_validate(pdf)


@router.delete("/{pdf_id}", status_code=204)
async def delete_pdf(
    pdf_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await soft_delete_pdf(db, pdf_id, current_user.id)
    return Response(status_code=204)
