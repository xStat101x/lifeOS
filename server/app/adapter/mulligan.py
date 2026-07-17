"""Mulligan spend (spec §8.3, CLAUDE.md invariant 3).

Spending a mulligan is the ONLY way to reclassify a past day: it charges XP on the
escalating cost ladder (200/400/800) under a monthly cap, then records a `Mulligan` row
(and, for the mode path, a retroactive `day_assignment`). The forgiveness itself lives in
the replay (`day_close`): a neutralize erases the day's losses, a retroactive mode is
re-scored then clamped so it can never become a win. Because the mulligan is persisted
source data, the whole ladder stays recomputable from `logs + config + mulligans` (§20).

XP model (§8): lifetime *earned* is permanent and drives level; *spendable* = earned −
Σ mulligan costs. Spending never lowers your level, only your spendable balance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.adapter.day_close import close_day
from app.config import ACTIVE_SCORING, ScoringConfig
from app.models import DayAssignment, DayEvaluation, DayMode, Mulligan, XPLedger
from app.scoring.forgiveness import mulligan_cost


class MulliganError(Exception):
    """Carries an HTTP status + message for the API layer to translate."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class MulliganResult:
    effective_day: date
    kind: str                 # 'neutralize' | 'retroactive_mode'
    mode_name: str | None
    xp_cost: int
    xp_spendable_after: int
    rank: dict                # per-domain + overall LP after the propagating re-close


def xp_lifetime(session: Session) -> int:
    """Permanent earned XP = balance on the most-recent day-close ledger row (the replay's
    cumulative earned through the last closed day)."""
    row = (
        session.query(XPLedger)
        .filter(XPLedger.event == "day_close", XPLedger.deleted_at.is_(None))
        .order_by(XPLedger.effective_day.desc().nullslast(), XPLedger.created_at.desc())
        .first()
    )
    return row.balance if row else 0


def xp_spent(session: Session) -> int:
    total = (
        session.query(func.coalesce(func.sum(Mulligan.xp_cost), 0))
        .filter(Mulligan.deleted_at.is_(None))
        .scalar()
    )
    return int(total or 0)


def xp_spendable(session: Session) -> int:
    return xp_lifetime(session) - xp_spent(session)


def day_was_scored(session: Session, day: date) -> bool:
    """Whether day-close has already materialized a result for this day.

    Day evaluations cover ordinary scored targets; the day-close XP row also marks a
    close with zero active targets. Either makes a later expectation change retroactive.
    """
    evaluation = (
        session.query(DayEvaluation.id)
        .filter(DayEvaluation.effective_day == day, DayEvaluation.deleted_at.is_(None))
        .first()
    )
    if evaluation is not None:
        return True
    return (
        session.query(XPLedger.id)
        .filter(
            XPLedger.effective_day == day,
            XPLedger.event == "day_close",
            XPLedger.deleted_at.is_(None),
        )
        .first()
        is not None
    )


def mulligans_in_month(session: Session, day: date) -> int:
    """Count non-deleted mulligans whose effective_day is in the same calendar month."""
    return (
        session.query(Mulligan)
        .filter(
            Mulligan.deleted_at.is_(None),
            extract("year", Mulligan.effective_day) == day.year,
            extract("month", Mulligan.effective_day) == day.month,
        )
        .count()
    )


def spend_mulligan(
    session: Session,
    *,
    effective_day: date,
    today: date,
    mode_id: uuid.UUID | None = None,
    cfg: ScoringConfig = ACTIVE_SCORING,
) -> MulliganResult:
    from app.adapter.queries import current_rank

    # Planning today/future is free only before scoring. Once today is closed, changing
    # its expectation is retroactive and must use this paid, never-win path.
    if effective_day > today or (effective_day == today and not day_was_scored(session, today)):
        raise MulliganError(
            422,
            f"{effective_day} has not been scored yet; apply a mode for free before "
            f"day-close instead (today is {today}).",
        )

    # cost ladder + monthly cap (server-side, not just client-side)
    prior = mulligans_in_month(session, effective_day)
    try:
        cost = mulligan_cost(prior, cfg)
    except ValueError as e:
        raise MulliganError(409, str(e))

    spendable = xp_spendable(session)
    if spendable < cost:
        raise MulliganError(
            409, f"Insufficient XP: this mulligan costs {cost}, spendable balance is {spendable}."
        )

    mode = None
    if mode_id is not None:
        mode = session.get(DayMode, mode_id)
        if mode is None:
            raise MulliganError(404, "day_mode not found")

    now = datetime.now(timezone.utc)
    mull = Mulligan(effective_day=effective_day, target_kind=None, target_id=None, xp_cost=cost)
    session.add(mull)
    session.flush()

    if mode is not None:
        # retroactive mode application (allowed ONLY because it's paid): one active mode/day
        for a in (
            session.query(DayAssignment)
            .filter(DayAssignment.effective_day == effective_day,
                    DayAssignment.deleted_at.is_(None))
            .all()
        ):
            a.deleted_at = now
        session.add(DayAssignment(
            effective_day=effective_day, day_mode_id=mode.id, source="manual",
            is_retroactive=True, mulligan_id=mull.id, applied_at=now,
        ))

    spendable_after = spendable - cost
    session.add(XPLedger(event="mulligan", xp_delta=-cost, balance=spendable_after,
                         effective_day=effective_day))
    session.commit()

    # Re-close the latest scored day so the forgiveness propagates into rank_state.
    latest = session.query(func.max(DayEvaluation.effective_day)).scalar()
    reclose_day = max(latest, effective_day) if latest is not None else effective_day
    close_day(session, reclose_day, cfg)

    return MulliganResult(
        effective_day=effective_day,
        kind="retroactive_mode" if mode is not None else "neutralize",
        mode_name=mode.name if mode is not None else None,
        xp_cost=cost, xp_spendable_after=spendable_after,
        rank=current_rank(session),
    )
