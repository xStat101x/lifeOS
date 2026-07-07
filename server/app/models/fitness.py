"""Fitness subsystem (spec §6.6, §13). Present in Phase 1 schema; only exercises /
lift_plans / lift_plan_entries receive seed rows (§22). No scoring off these yet."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Exercise(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "exercises"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    modality: Mapped[str] = mapped_column(String, nullable=False)  # 'lift'|'cardio'
    primary_muscles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    secondary_muscles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    default_unit: Mapped[str | None] = mapped_column(String, nullable=True)


class LiftPlan(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "lift_plans"

    source_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LiftPlanEntry(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "lift_plan_entries"

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lift_plans.id"), nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    day_pattern: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "MO"
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_lite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bonus_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LiftSet(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "lift_sets"

    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    is_adhoc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # §13 bonus


class CardioSession(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "cardio_sessions"

    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="watch")
