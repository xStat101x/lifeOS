"""Calendar & tasks (spec §6.9, §16). Inert in Phase 1."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class CalendarCache(UUIDPKMixin, TimestampMixin, Base):
    """Read-only mirror of aggregated Apple Calendar (EventKit, §16)."""

    __tablename__ = "calendar_cache"

    external_event_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_calendar: Mapped[str | None] = mapped_column(String, nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LifeosBlock(UUIDPKMixin, TimestampMixin, Base):
    """Auto-blocks LifeOS writes to its own dedicated calendar (§16)."""

    __tablename__ = "lifeos_blocks"

    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("systems.id"), nullable=False)
    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Task(UUIDPKMixin, TimestampMixin, Base):
    """Optional, minimal, NEVER auto-scheduled (§16)."""

    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    due_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
