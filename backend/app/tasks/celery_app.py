"""Celery application configuration."""

import time

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import get_logger, log_event

settings = get_settings()

celery_app = Celery("pdf_manager")
celery_app.config_from_object(
    {
        "broker_url": settings.redis_url,
        "result_backend": settings.redis_url,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
        "timezone": "UTC",
    }
)
celery_app.autodiscover_tasks(["app.tasks"])

celery_app.conf.beat_schedule = {
    "purge-deleted-pdfs-daily": {
        "task": "app.tasks.pdf_tasks.purge_deleted_pdfs",
        "schedule": crontab(hour=2, minute=0),
    },
}

_task_start_times: dict = {}


@task_prerun.connect
def _on_task_prerun(sender=None, task_id=None, args=None, kwargs=None, **extra):
    logger = get_logger("celery")
    args_str = str(args)[:200] if args else ""
    log_event(
        logger,
        "TASK_PRERUN",
        task_id=task_id,
        metadata={"task_name": sender.name if sender else "", "args": args_str},
    )
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect
def _on_task_postrun(sender=None, task_id=None, state=None, retval=None, **extra):
    logger = get_logger("celery")
    start = _task_start_times.pop(task_id, None)
    duration_ms = int((time.perf_counter() - start) * 1000) if start else None
    log_event(
        logger,
        "TASK_POSTRUN",
        task_id=task_id,
        duration_ms=duration_ms,
        metadata={
            "task_name": sender.name if sender else "",
            "state": state,
        },
    )
