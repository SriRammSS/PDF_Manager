"""PDF service for listing, viewing, renaming, and soft-deleting PDFs."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_event
from app.db.models import PDF
from app.schemas.pdf import PDFListResponse, PDFResponse

logger = get_logger("service.pdf")


async def list_pdfs(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    size: int = 20,
) -> PDFListResponse:
    offset = (page - 1) * size
    count_q = (
        select(func.count())
        .select_from(PDF)
        .where(PDF.owner_id == user_id, PDF.deleted_at.is_(None))
    )
    total = (await db.execute(count_q)).scalar() or 0
    rows_q = (
        select(PDF)
        .where(PDF.owner_id == user_id, PDF.deleted_at.is_(None))
        .order_by(PDF.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    result = await db.execute(rows_q)
    items = result.scalars().all()
    return PDFListResponse(
        items=[PDFResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        size=size,
    )


async def get_pdf_or_raise(
    db: AsyncSession,
    pdf_id: str | UUID,
    user_id: str | UUID,
) -> PDF:
    uid = UUID(str(pdf_id)) if isinstance(pdf_id, str) else pdf_id
    row = await db.get(PDF, uid)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "PDF not found")
    if str(row.owner_id) != str(user_id):
        raise HTTPException(403, "Access denied")
    return row


async def rename_pdf(
    db: AsyncSession,
    pdf_id: str | UUID,
    user_id: str | UUID,
    new_name: str,
) -> PDF:
    pdf = await get_pdf_or_raise(db, pdf_id, user_id)
    old_name = pdf.name
    pdf.name = new_name
    pdf.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(pdf)
    log_event(
        logger,
        "RENAME_SUCCESS",
        user_id=str(user_id),
        metadata={
            "pdf_id": str(pdf_id),
            "old_name": old_name,
            "new_name": new_name,
        },
    )
    return pdf


async def soft_delete_pdf(
    db: AsyncSession,
    pdf_id: str | UUID,
    user_id: str | UUID,
) -> None:
    pdf = await get_pdf_or_raise(db, pdf_id, user_id)
    pdf.deleted_at = datetime.now(UTC)
    pdf.status = "deleted"
    await db.commit()
    log_event(
        logger,
        "SOFT_DELETE_SUCCESS",
        user_id=str(user_id),
        metadata={"pdf_id": str(pdf_id), "name": pdf.name},
    )
