"""File storage service for PDF uploads."""

import logging
import os
from pathlib import Path
from uuid import uuid4

import aiofiles
from collections.abc import AsyncGenerator

from app.core.config import get_settings

logger = logging.getLogger(__name__)
BASE_PATH = Path(get_settings().file_storage_path)


def _sanitise_filename(filename: str) -> str:
    """Strip path separators, replace spaces with underscores."""
    name = os.path.basename(filename).replace(" ", "_")
    return "".join(c for c in name if c not in "/\\")


async def save_upload(file_bytes: bytes, filename: str, user_id: str) -> str:
    """Save uploaded file atomically. Returns storage_path."""
    sanitised = _sanitise_filename(filename)
    user_dir = BASE_PATH / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    dest_path = user_dir / f"{uuid4()}_{sanitised}"
    tmp_path = dest_path.with_suffix(".tmp")
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(file_bytes)
        tmp_path.rename(dest_path)
        return str(dest_path.resolve())
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


async def read_file_stream(
    storage_path: str,
    start: int | None = None,
    end: int | None = None,
) -> AsyncGenerator[bytes, None]:
    """Open file async and yield chunks. If start/end given, stream only that byte range."""
    async with aiofiles.open(storage_path, "rb") as f:
        if start is not None:
            await f.seek(start)
        to_read: int | None = None
        if start is not None and end is not None:
            to_read = end - start + 1
        chunk_size = 8192
        while True:
            n = chunk_size if to_read is None else min(chunk_size, to_read)
            chunk = await f.read(n)
            if not chunk:
                break
            if to_read is not None:
                to_read -= len(chunk)
                if to_read <= 0:
                    break
            yield chunk


def read_file_stream_sync(
    storage_path: str,
    start: int | None = None,
    end: int | None = None,
):
    """Sync generator: yield file chunks. If start/end given, stream only that byte range."""
    with open(storage_path, "rb") as f:
        if start is not None:
            f.seek(start)
        to_read: int | None = None
        if start is not None and end is not None:
            to_read = end - start + 1
        chunk_size = 8192
        while True:
            n = chunk_size if to_read is None else min(chunk_size, to_read)
            chunk = f.read(n)
            if not chunk:
                break
            if to_read is not None:
                to_read -= len(chunk)
                if to_read <= 0:
                    break
            yield chunk


def delete_file(storage_path: str) -> None:
    """Remove file. Log warning if not found, do not raise."""
    try:
        os.remove(storage_path)
    except FileNotFoundError:
        logger.warning("File not found for deletion: %s", storage_path)
