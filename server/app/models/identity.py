"""Identity & taxonomy (spec §6.1)."""

from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String, nullable=False)


class Domain(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "domains"

    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # e.g. "nutrition"
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # §7.6 rollup
