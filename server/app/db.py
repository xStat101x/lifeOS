"""SQLAlchemy engine/session wiring. Canonical Postgres store (spec §4.2)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI-style dependency / context helper yielding a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
