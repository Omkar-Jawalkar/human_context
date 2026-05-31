from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_sync_url = settings.database_url.replace("+asyncpg", "+psycopg")
_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def _get_sync_engine() -> Engine:
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        _sync_engine = create_engine(_sync_url, pool_pre_ping=True)
        _sync_session_factory = sessionmaker(bind=_sync_engine, expire_on_commit=False)
    return _sync_engine


def _get_sync_session_factory() -> sessionmaker[Session]:
    _get_sync_engine()
    assert _sync_session_factory is not None
    return _sync_session_factory


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    session = _get_sync_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
