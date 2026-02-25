"""Structured JSON logging with DatabaseLogHandler for real-time SSE events."""

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    """Format log records as JSON with required fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": getattr(record, "module", record.module),
            "event": getattr(record, "event", "log"),
            "user_id": str(record.user_id) if getattr(record, "user_id", None) else None,
            "request_id": str(record.request_id) if getattr(record, "request_id", None) else None,
            "task_id": getattr(record, "task_id", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "metadata": getattr(record, "metadata", {}),
            "error": str(record.exc_info[1]) if record.exc_info else None,
        }
        return json.dumps(log_data)


class DatabaseLogHandler(logging.Handler):
    """Writes log rows to the 'logs' table via background thread queue."""

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._process_queue, daemon=True)
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = self._record_to_dict(record)
            self._queue.put(log_entry)
        except Exception:
            self.handleError(record)

    def _record_to_dict(self, record: logging.LogRecord) -> dict:
        meta = getattr(record, "metadata", {}) or {}
        # Unwrap if metadata was double-nested (e.g. metadata={"metadata": {"email": x}})
        if isinstance(meta, dict) and "metadata" in meta and len(meta) == 1:
            meta = meta["metadata"]
        return {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc),
            "level": record.levelname[:10] if record.levelname else "INFO",
            "module": (getattr(record, "module", record.module) or "")[:50],
            "event": (getattr(record, "event", "log") or "log")[:100],
            "user_id": str(record.user_id) if getattr(record, "user_id", None) else None,
            "request_id": str(record.request_id) if getattr(record, "request_id", None) else None,
            "task_id": getattr(record, "task_id", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "metadata": meta if isinstance(meta, dict) else {},
            "error": str(record.exc_info[1]) if record.exc_info else None,
        }

    def _to_serializable_dict(self, log_entry: dict) -> dict:
        """Convert log_entry for JSON serialization (pg_notify payload)."""
        return {
            "id": log_entry["id"],
            "timestamp": log_entry["timestamp"].isoformat() if log_entry.get("timestamp") else None,
            "level": log_entry.get("level"),
            "module": log_entry.get("module"),
            "event": log_entry.get("event"),
            "user_id": log_entry.get("user_id"),
            "request_id": log_entry.get("request_id"),
            "task_id": log_entry.get("task_id"),
            "duration_ms": log_entry.get("duration_ms"),
            "metadata": log_entry.get("metadata") or {},
            "error": log_entry.get("error"),
        }

    def _process_queue(self) -> None:
        import psycopg2
        from psycopg2.extras import Json

        settings = get_settings()
        while True:
            try:
                log_entry = self._queue.get()
                if log_entry is None:
                    break
                conn = psycopg2.connect(
                    settings.sync_database_url.replace("postgresql+psycopg2://", "postgresql://")
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO logs (id, timestamp, level, module, event, user_id, request_id, task_id, duration_ms, metadata, error)
                            VALUES (%s, %s, %s, %s, %s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
                            """,
                            (
                                log_entry["id"],
                                log_entry["timestamp"],
                                log_entry["level"],
                                log_entry["module"],
                                log_entry["event"],
                                log_entry["user_id"],
                                log_entry["request_id"],
                                log_entry["task_id"],
                                log_entry["duration_ms"],
                                Json(log_entry["metadata"]),
                                log_entry["error"],
                            ),
                        )
                        notify_payload = json.dumps(self._to_serializable_dict(log_entry))
                        cur.execute("SELECT pg_notify('new_log_entry', %s)", [notify_payload])
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                # Fallback to stderr if DB write fails
                import sys
                print(f"DatabaseLogHandler error: {e}", file=sys.stderr)
            finally:
                self._queue.task_done()


def get_logger(module_name: str) -> logging.Logger:
    """Factory for structured loggers."""
    logger = logging.getLogger(module_name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.addHandler(DatabaseLogHandler())
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    task_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    level: int = logging.INFO,
    **metadata: Any,
) -> None:
    """Helper to log structured events."""
    extra = {
        "event": event,
        "user_id": user_id,
        "request_id": request_id,
        "task_id": task_id,
        "duration_ms": duration_ms,
        "metadata": metadata,
    }
    logger.log(level, event, extra=extra)
