"""Scoring, seasons, currencies (spec §6.5, §7, §8).

``day_evaluations`` is the deterministic per-target/per-day record from which domain
LP is replayed (§7.6) — no hidden state; the whole ladder is re-computable from here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Season(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "seasons"

    name: Mapped[str] = mapped_column(String, nullable=False)
    start_day: Mapped[date] = mapped_column(Date, nullable=False)
    end_day: Mapped[date] = mapped_column(Date, nullable=False)
    reset_compression: Mapped[float] = mapped_column(Float, nullable=False)  # §7.8


class RankPeak(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rank_peaks"

    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)  # 'habit'|'domain'|'overall'
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    peak_lp: Mapped[float] = mapped_column(Float, nullable=False)
    peak_tier: Mapped[str] = mapped_column(String, nullable=False)
    peak_division: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DayEvaluation(UUIDPKMixin, TimestampMixin, Base):
    """One row per (scored target, effective_day) — the deterministic scoring record."""

    __tablename__ = "day_evaluations"

    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)  # 'habit'|'system'
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), nullable=False)

    completion: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    decay: Mapped[float | None] = mapped_column(Float, nullable=True)  # domain-level (§7.3)
    lp_change: Mapped[float | None] = mapped_column(Float, nullable=True)

    applied_mode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("day_modes.id"), nullable=True
    )
    was_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RankState(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rank_state"

    scope: Mapped[str] = mapped_column(String, nullable=False)  # 'habit'|'domain'|'overall'
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    lp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    division: Mapped[int | None] = mapped_column(Integer, nullable=True)


class XPLedger(UUIDPKMixin, TimestampMixin, Base):
    """XP is PERMANENT; never season-resets (§7.8, §8)."""

    __tablename__ = "xp_ledger"

    event: Mapped[str] = mapped_column(String, nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_day: Mapped[date | None] = mapped_column(Date, nullable=True)


class AccountLevel(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "account_level"

    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    xp_into_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Reward(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "rewards"

    name: Mapped[str] = mapped_column(String, nullable=False)
    cost_type: Mapped[str] = mapped_column(String, nullable=False)  # 'xp'|'level_milestone'
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Mulligan(UUIDPKMixin, TimestampMixin, Base):
    """Retroactive forgiveness (§8.3). Converts a past loss to neutral / applies a mode
    retroactively — NEVER to a win (§0 rule 3, §8.3 invariant)."""

    __tablename__ = "mulligans"

    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    xp_cost: Mapped[int] = mapped_column(Integer, nullable=False)
