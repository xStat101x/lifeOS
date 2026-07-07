"""Habits & systems (spec §6.2, §11)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Habit(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "habits"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # 'binary' | 'quantitative'
    importance: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5 (§7.2, §11)
    schedule_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'weekdays' | 'daily' | 'specific_days' | 'floating_count'
    schedule_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timing_window: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {start,end} or null
    is_lifelong: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class HabitPhase(UUIDPKMixin, TimestampMixin, Base):
    """Time-versioned targets (bulk/maintain/cut). Historical days scored vs the target
    active then (§11) — a phase switch never retroactively fails a past day."""

    __tablename__ = "habit_phases"

    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # null = current


class System(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "systems"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timing_window: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SystemStep(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "system_steps"

    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("systems.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    habit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("habits.id"), nullable=True
    )
    inline_label: Mapped[str | None] = mapped_column(String, nullable=True)
