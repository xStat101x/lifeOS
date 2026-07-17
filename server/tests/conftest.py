"""Integration-test fixtures: a dedicated ``lifeos_test`` database on the lifeos-db
container (isolated from the seeded dev DB). Pure scoring tests don't touch any of this.
"""

from __future__ import annotations

# Point the app at the throwaway test DB BEFORE any app module (and its engine) imports.
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://lifeos:lifeos@localhost:5432/lifeos_test"

import psycopg
import pytest

_ADMIN = "postgresql://lifeos:lifeos@localhost:5432/lifeos"  # maintenance connection


def _db_reachable() -> bool:
    try:
        with psycopg.connect(_ADMIN, connect_timeout=3):
            return True
    except Exception:
        return False


DB_REACHABLE = _db_reachable()


@pytest.fixture(scope="session")
def provision_db():
    if not DB_REACHABLE:
        pytest.skip("lifeos-db container not reachable on localhost:5432")
    with psycopg.connect(_ADMIN, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS lifeos_test")
        c.execute("CREATE DATABASE lifeos_test")

    from app.db import engine, SessionLocal
    from app.models import Base
    from app.seed.seed_data import seed

    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        seed(s)
    yield
    engine.dispose()
    try:
        with psycopg.connect(_ADMIN, autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS lifeos_test")
    except Exception:
        pass  # left for next run's DROP IF EXISTS


@pytest.fixture
def db(provision_db):
    """Fresh session with the volatile (recomputable/log) tables cleared; seed kept.

    Seasons are reset to a canonical Season 1 each test so a test that reconfigures
    seasons (the reset/peak test) can't leak into others.
    """
    from datetime import date

    from app.db import SessionLocal
    from app.models import (
        AccountLevel, DayAssignment, DayEvaluation, Log, Mulligan, RankPeak, RankState,
        Season, XPLedger,
    )

    session = SessionLocal()
    # order matters: clear rank_state/rank_peaks (FK -> seasons) before seasons
    for model in (Log, DayEvaluation, RankState, RankPeak, XPLedger, DayAssignment, Mulligan):
        session.query(model).delete()
    session.query(Season).delete()
    session.add(Season(name="Season 1", start_day=date(2026, 8, 20),
                       end_day=date(2026, 11, 20), reset_compression=0.35))
    session.query(AccountLevel).delete()
    session.add(AccountLevel(level=1, xp_into_level=0))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db):
    from datetime import date

    from fastapi.testclient import TestClient

    from app.api.main import app, get_today

    # Pin "today" so the §9.1 retroactive rule is deterministic regardless of wall clock.
    # Test days at/after 2026-08-20 (Season 1 start) are "today or future" => free.
    app.dependency_overrides[get_today] = lambda: date(2026, 8, 20)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
