"""Nutrition subsystem (spec §6.8, §14). Inert in Phase 1 (agent stubbed later)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Meal(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "meals"

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MealTemplate(UUIDPKMixin, TimestampMixin, Base):
    """Meal memory (§14) — recognized recurring meals become one-tap, no-API entries."""

    __tablename__ = "meal_templates"

    name: Mapped[str] = mapped_column(String, nullable=False)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein: Mapped[float | None] = mapped_column(Float, nullable=True)
    learned_from_meal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
