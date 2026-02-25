"""Celery tasks for PDF processing."""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pikepdf
from sqlalchemy import select, update

from app.core.logging import get_logger, log_event
from app.db.models import PDF, PDFVersion
from app.db.sync_session import sync_db_session
from app.services.edit_service import apply_operations
from app.services.storage_service import delete_file

from .celery_app import celery_app

logger = get_logger("task.upload")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=2)
def process_uploaded_pdf(self, pdf_id: str, storage_path: str, user_id: str):
    start = time.perf_counter()
    try:
        log_event(
            logger,
            "TASK_STARTED",
            task_id=self.request.id,
            metadata={"pdf_id": pdf_id, "storage_path": storage_path},
        )

        with pikepdf.open(storage_path) as pdf:
            page_count = len(pdf.pages)

        with sync_db_session() as db:
            db.execute(
                update(PDF)
                .where(PDF.id == UUID(pdf_id))
                .values(
                    page_count=page_count,
                    status="ready",
                    updated_at=datetime.now(timezone.utc),
                )
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event(
            logger,
            "TASK_COMPLETED",
            task_id=self.request.id,
            duration_ms=duration_ms,
            metadata={"pdf_id": pdf_id, "page_count": page_count},
        )

    except Exception as exc:
        with sync_db_session() as db:
            db.execute(
                update(PDF).where(PDF.id == UUID(pdf_id)).values(status="error")
            )
        log_event(
            logger,
            "TASK_FAILED",
            task_id=self.request.id,
            metadata={"pdf_id": pdf_id, "error": str(exc)},
        )
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@celery_app.task(bind=True, max_retries=3)
def save_edited_pdf(
    self,
    pdf_id: str,
    user_id: str,
    operations_json: list,
    comment: str | None = None,
):
    logger = get_logger("task.edit")
    start = time.perf_counter()
    op_types = list({op["type"] for op in operations_json})
    log_event(
        logger,
        "EDIT_TASK_STARTED",
        task_id=self.request.id,
        metadata={
            "pdf_id": pdf_id,
            "ops_count": len(operations_json),
            "op_types": op_types,
        },
    )
    try:
        with sync_db_session() as db:
            pdf = db.get(PDF, UUID(pdf_id))
            if not pdf:
                raise ValueError(f"PDF {pdf_id} not found")

            # Archive current version
            db.add(
                PDFVersion(
                    pdf_id=UUID(pdf_id),
                    version=pdf.version,
                    storage_path=pdf.storage_path,
                    saved_at=datetime.now(timezone.utc),
                    saved_by=UUID(user_id),
                )
            )

            src_path = str(Path(pdf.storage_path).resolve())
            new_path = str((Path(pdf.storage_path).resolve().parent / f"{uuid4()}_{pdf.name}").resolve())
            new_pages = apply_operations(src_path, operations_json, new_path)

            pdf.storage_path = new_path
            pdf.version += 1
            pdf.page_count = new_pages
            pdf.updated_at = datetime.now(timezone.utc)
            new_version = pdf.version
            db.commit()

        ms = int((time.perf_counter() - start) * 1000)
        log_event(
            logger,
            "EDIT_TASK_COMPLETED",
            task_id=self.request.id,
            duration_ms=ms,
            metadata={"pdf_id": pdf_id, "new_version": new_version},
        )
    except Exception as exc:
        log_event(
            logger,
            "EDIT_TASK_FAILED",
            task_id=self.request.id,
            metadata={"pdf_id": pdf_id, "error": str(exc)},
        )
        raise self.retry(exc=exc, countdown=2**self.request.retries)


@celery_app.task
def purge_deleted_pdfs():
    purge_logger = get_logger("task.purge")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    with sync_db_session() as db:
        result = db.execute(
            select(PDF).where(
                PDF.deleted_at.isnot(None),
                PDF.deleted_at < cutoff,
            )
        )
        rows = result.scalars().all()
        count = 0
        for pdf in rows:
            delete_file(pdf.storage_path)
            db.delete(pdf)
            count += 1
    log_event(purge_logger, "PURGE_COMPLETED", metadata={"files_purged": count})
