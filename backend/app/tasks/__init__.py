"""Celery tasks - use: celery -A app.tasks worker --loglevel=info"""

from app.tasks.celery_app import celery_app
from app.tasks import pdf_tasks  # noqa: F401 - register tasks

app = celery_app
