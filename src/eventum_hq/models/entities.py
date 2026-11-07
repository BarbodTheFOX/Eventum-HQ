"""M0 tables: users, series, settings, notifications (outbox), audit_events.

Tables for tasks, reels, submissions, reviews, outputs, delegations and
recurrences are added in their own milestones with their own migrations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eventum_hq.models.base import Base, IdMixin, TimestampMixin, UTCDateTime, enum_column
from eventum_hq.models.enums import (
    AccessStatus,
    ApprovalChain,
    NotificationStatus,
    ReviewStage,
    Role,
    SeriesKind,
    TaskInputKind,
    TaskKind,
    TaskStatus,
)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    # While access_status is PENDING this is the role the user asked for.
    role: Mapped[Role] = mapped_column(enum_column(Role), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    access_status: Mapped[AccessStatus] = mapped_column(
        enum_column(AccessStatus), nullable=False, default=AccessStatus.PENDING
    )
    # for the "over capacity" warning in reports (F17); empty = no warning
    weekly_capacity_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


class Task(IdMixin, TimestampMixin, Base):
    """One unit of work with one assignee (handoff §4.1, §7).

    ``content_item_id`` and ``recurrence_id`` get their foreign keys in M3 / M5,
    when ``content_items`` and ``recurrences`` exist.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index(None, "assignee_id", "status"),
        Index(None, "status", "due_at"),
        UniqueConstraint("recurrence_id", "recurrence_date"),
    )

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # T-0001
    content_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[TaskKind] = mapped_column(enum_column(TaskKind), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="RESTRICT"), nullable=True
    )
    assignee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus), nullable=False)
    review_stage: Mapped[ReviewStage | None] = mapped_column(enum_column(ReviewStage), nullable=True)
    approval_chain: Mapped[ApprovalChain] = mapped_column(
        enum_column(ApprovalChain), nullable=False
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # F17
    first_submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revision_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recurrence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    external_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class TaskInput(IdMixin, TimestampMixin, Base):
    """Input needed to do a task: timecodes, cover text/photos, or a brief."""

    __tablename__ = "task_inputs"

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    content_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[TaskInputKind] = mapped_column(enum_column(TaskInputKind), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{file_id, file_unique_id, type, archive_message_id, size}]
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    provided_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provided_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
