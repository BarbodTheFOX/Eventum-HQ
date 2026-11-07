"""Enums shared by models and services. Values equal names (stored as text)."""

from enum import StrEnum


class Role(StrEnum):
    """Team roles (handoff v1.1 §3.1)."""

    OWNER = "OWNER"  # Barbod — developer, full access
    DIRECTOR = "DIRECTOR"  # Farid — founder, all final approvals
    PROJECT_MANAGER = "PROJECT_MANAGER"  # Ali
    CONTENT_SPECIALIST = "CONTENT_SPECIALIST"  # Amin
    DESIGNER = "DESIGNER"  # Mohadeseh
    EDITOR = "EDITOR"  # Sina


class AccessStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Capability(StrEnum):
    CREATE_TASK = "CREATE_TASK"
    VIEW_ALL_TASKS = "VIEW_ALL_TASKS"
    RECEIVE_OVERDUE_ALERTS = "RECEIVE_OVERDUE_ALERTS"
    RECEIVE_WEEKLY_REPORT = "RECEIVE_WEEKLY_REPORT"
    CREATE_REEL = "CREATE_REEL"
    REVIEW_L1 = "REVIEW_L1"
    APPROVE_FINAL = "APPROVE_FINAL"
    PUBLISH = "PUBLISH"
    MANAGE_USERS = "MANAGE_USERS"
    DELEGATE = "DELEGATE"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class SeriesKind(StrEnum):
    REEL = "REEL"
    LONGFORM = "LONGFORM"
    CAMPAIGN = "CAMPAIGN"
    OTHER = "OTHER"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
