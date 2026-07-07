"""Declarative base + common columns.

Every table carries (spec §6): a client-generated UUID primary key (so offline rows
never collide, §20), and ``created_at`` / ``updated_at`` / ``deleted_at`` (soft-delete)
for sync. Day-bucketed tables additionally store ``effective_day`` (§10), defined on
the individual models where it applies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """created/updated/deleted timestamps required on every table for sync (§6, §20)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UUIDPKMixin:
    """Client-generatable UUID primary key (§6)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
