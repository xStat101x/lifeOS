"""Logs — append-only source of truth (spec §6.3, §20). Everything derivable is
derived from here; scoring is a pure function of these rows + config."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Log(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "logs"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)  # 'habit'|'system_step'|'system'
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # UTC
    effective_day: Mapped[date] = mapped_column(Date, nullable=False)  # local logical day (§10)
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 'manual'|'photo'|'voice'|'watch'|'import'|'actual'|'system'
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
