"""Day Modes (spec §6.4, §9) — reusable templates that reshape a day's expectations."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class DayMode(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "day_modes"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DayModeOverride(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "day_mode_overrides"

    day_mode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("day_modes.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String, nullable=False)  # 'domain'|'habit'|'system'
    # Polymorphic reference to a domain/habit/system depending on scope; no FK.
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    op: Mapped[str] = mapped_column(String, nullable=False)
    # 'pause'|'scale_target'|'neutralize_timing'|'expect_more'|'scale_importance'
    factor: Mapped[float | None] = mapped_column(Float, nullable=True)  # e.g. 0.6; null for pause
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class DayModeReminder(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "day_mode_reminders"

    day_mode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("day_modes.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    at_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    relative_to: Mapped[str | None] = mapped_column(String, nullable=True)


class DayAssignment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "day_assignments"

    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    day_mode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("day_modes.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 'scheduled'|'calendar_suggested'|'manual'
    is_retroactive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mulligan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mulligans.id"), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
