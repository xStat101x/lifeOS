"""Body metrics (spec §6.7, §15). Inert in Phase 1."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class WeightEntry(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "weight_entries"

    effective_day: Mapped[date] = mapped_column(Date, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    trend_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 7-day EMA (§15)
