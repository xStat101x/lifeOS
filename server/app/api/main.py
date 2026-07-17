"""Minimal FastAPI surface for the Phase-1 adapter slice (spec §4.2).

Three endpoints plus health: log an event, close a day (score + persist), read rank/XP.
Deep clients (iOS/web) come in later phases; this is enough to drive the engine
end-to-end against Postgres.

    uvicorn app.api.main:app --reload
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapter.day_close import close_day
from app.adapter.queries import current_rank
from app.db import get_session
from app.models import Log, User

app = FastAPI(title="LifeOS", version="0.1.0")


class LogIn(BaseModel):
    target_kind: str = Field(description="'habit' | 'system_step' | 'system'")
    target_id: uuid.UUID
    effective_day: date
    value: float | None = None
    unit: str | None = None
    logged_at: datetime | None = None
    source: str = "manual"
    meta: dict = Field(default_factory=dict)


class LogOut(BaseModel):
    id: uuid.UUID


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/logs", response_model=LogOut, status_code=201)
def create_log(body: LogIn, session: Session = Depends(get_session)) -> LogOut:
    user = session.query(User).first()
    if user is None:
        raise HTTPException(500, "No user seeded.")
    row = Log(
        user_id=user.id, target_kind=body.target_kind, target_id=body.target_id,
        value=body.value, unit=body.unit,
        logged_at=body.logged_at or datetime.now(timezone.utc),
        effective_day=body.effective_day, source=body.source, meta=body.meta,
    )
    session.add(row)
    session.commit()
    return LogOut(id=row.id)


@app.post("/day-close/{day}")
def day_close(day: date, session: Session = Depends(get_session)) -> dict:
    try:
        result = close_day(session, day)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {
        "day": result.day.isoformat(),
        "domains": result.domains,
        "overall": result.overall,
        "xp_earned": result.xp_earned,
        "xp_total": result.xp_total,
        "level": result.level,
    }


@app.get("/rank")
def rank(session: Session = Depends(get_session)) -> dict:
    return current_rank(session)
