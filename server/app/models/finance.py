"""Finance — thin cache over Actual Budget (spec §6.10, §17). Inert in Phase 1;
only the seed budget lines (§22) are created."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class FinTransaction(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fin_transactions"

    actual_id: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    account: Mapped[str | None] = mapped_column(String, nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FinBudget(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fin_budgets"

    category: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "monthly"
    limit_amount: Mapped[float] = mapped_column(Float, nullable=False)


class FinSnapshot(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fin_snapshots"

    date: Mapped[date] = mapped_column(Date, nullable=False)
    net_worth: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    by_category: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
