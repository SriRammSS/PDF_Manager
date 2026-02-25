"""Sync database session for Celery tasks."""

from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine

SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


@contextmanager
def sync_db_session():
    """Context manager for sync DB session (used in Celery tasks)."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
