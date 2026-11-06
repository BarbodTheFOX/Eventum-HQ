"""M0 tables: users, series, settings, notifications (outbox), audit_events.

Tables for tasks, reels, submissions, reviews, outputs, delegations and
recurrences are added in their own milestones with their own migrations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eventum_hq.models.base import Base, IdMixin, TimestampMixin, UTCDateTime, enum_column
from eventum_hq.models.enums import AccessStatus, NotificationStatus, Role, SeriesKind


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[Role] = mapped_column(enum_column(Role), nullable=False, default=Role.MEMBER)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    access_status: Mapped[AccessStatus] = mapped_column(
        enum_column(AccessStatus), nullable=False, default=AccessStatus.PENDING
    )

    @property
    def can_use_bot(self) -> bool:
        return self.is_active and self.access_status == AccessStatus.APPROVED

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id} role={self.role}>"


class Series(IdMixin, TimestampMixin, Base):
    __tablename__ = "series"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    kind: Mapped[SeriesKind] = mapped_column(enum_column(SeriesKind), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)


class Notification(IdMixin, TimestampMixin, Base):
    """Outbox row. Services write these; the bot layer delivers them."""

    __tablename__ = "notifications"
    __table_args__ = (Index(None, "status", "scheduled_at"),)

    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_column(NotificationStatus), nullable=False, default=NotificationStatus.PENDING
    )


class AuditEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index(None, "entity_type", "entity_id"),)

    # NULL actor = system
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
