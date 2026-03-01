from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from core.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def _make_session_factory():
    return sessionmaker(autocommit=False, autoflush=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    engine = get_engine()
    SessionLocal = _make_session_factory()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
