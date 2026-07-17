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
from app.adapter.mulligan import MulliganError, spend_mulligan
from app.adapter.queries import current_rank
from app.db import get_session
from app.models import DayAssignment, DayMode as DayModeModel, Log, User

app = FastAPI(title="LifeOS", version="0.1.0")


def get_today() -> date:
    """The reference 'today' for the §9.1 anti-exploit rule. A dependency so tests can
    pin it deterministically."""
    return date.today()


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


# --- Day Modes (§9) ---------------------------------------------------------------

class DayAssignmentIn(BaseModel):
    effective_day: date
    day_mode_id: uuid.UUID
    source: str = "manual"                # 'scheduled' | 'manual' | 'calendar_suggested'


class DayAssignmentOut(BaseModel):
    id: uuid.UUID
    effective_day: date
    day_mode_id: uuid.UUID
    mode_name: str
    source: str


@app.post("/day-assignments", response_model=DayAssignmentOut, status_code=201)
def create_day_assignment(
    body: DayAssignmentIn,
    session: Session = Depends(get_session),
    today: date = Depends(get_today),
) -> DayAssignmentOut:
    mode = session.get(DayModeModel, body.day_mode_id)
    if mode is None:
        raise HTTPException(404, "day_mode not found")
    # §9.1 anti-exploit: applying a mode to today/future is free; reclassifying a PAST day
    # (which may already have scored) is the mulligan path — not wired yet, so reject it.
    if body.effective_day < today:
        raise HTTPException(
            409,
            f"Retroactive mode application to {body.effective_day} (before today {today}) "
            f"requires a mulligan (§9.1); mulligan-spend isn't supported yet. Applying to "
            f"today or a future day is free.",
        )
    # A day has one active mode: soft-delete any existing assignment, then insert.
    existing = (
        session.query(DayAssignment)
        .filter(DayAssignment.effective_day == body.effective_day,
                DayAssignment.deleted_at.is_(None))
        .all()
    )
    for row in existing:
        row.deleted_at = datetime.now(timezone.utc)
    assignment = DayAssignment(
        effective_day=body.effective_day, day_mode_id=mode.id, source=body.source,
        is_retroactive=False, applied_at=datetime.now(timezone.utc),
    )
    session.add(assignment)
    session.commit()
    return DayAssignmentOut(id=assignment.id, effective_day=assignment.effective_day,
                            day_mode_id=mode.id, mode_name=mode.name, source=assignment.source)


@app.get("/day-assignments", response_model=list[DayAssignmentOut])
def list_day_assignments(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
) -> list[DayAssignmentOut]:
    q = session.query(DayAssignment).filter(DayAssignment.deleted_at.is_(None))
    if start is not None:
        q = q.filter(DayAssignment.effective_day >= start)
    if end is not None:
        q = q.filter(DayAssignment.effective_day <= end)
    rows = q.order_by(DayAssignment.effective_day).all()
    names = {m.id: m.name for m in session.query(DayModeModel).all()}
    return [
        DayAssignmentOut(id=r.id, effective_day=r.effective_day, day_mode_id=r.day_mode_id,
                         mode_name=names.get(r.day_mode_id, ""), source=r.source)
        for r in rows
    ]


# --- Mulligans (§8.3) -------------------------------------------------------------

class MulliganIn(BaseModel):
    effective_day: date
    # None => neutralize the day's loss; set => apply this Day Mode retroactively.
    mode_id: uuid.UUID | None = None


@app.post("/mulligans", status_code=201)
def spend(
    body: MulliganIn,
    session: Session = Depends(get_session),
    today: date = Depends(get_today),
) -> dict:
    try:
        r = spend_mulligan(session, effective_day=body.effective_day, today=today,
                           mode_id=body.mode_id)
    except MulliganError as e:
        raise HTTPException(e.status, e.detail)
    return {
        "effective_day": r.effective_day.isoformat(),
        "kind": r.kind,
        "mode": r.mode_name,
        "xp_cost": r.xp_cost,
        "xp_spendable_after": r.xp_spendable_after,
        "rank": r.rank,
    }
