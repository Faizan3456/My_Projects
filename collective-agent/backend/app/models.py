"""Persistent memory schema.

Column types are deliberately portable (generic Uuid / JSON / TIMESTAMP with
timezone) so the same models run on PostgreSQL in production and on SQLite in
the test suite. db/schema.sql holds the hand-written PostgreSQL DDL that these
models mirror.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --- vocabularies -----------------------------------------------------------

CONTEXT_STATUSES = ("active", "blocked", "handover_required", "done")
EVENT_TYPES = (
    "note",
    "user_message",
    "agent_reply",
    "context_update",
    "handover",
    "error",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON}


class TimestampPK:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


# --- tables -----------------------------------------------------------------


class Project(TimestampPK, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    context: Mapped["Context | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )


class Context(TimestampPK, Base):
    """The single live state row for a project — the 'where are we' record."""

    __tablename__ = "contexts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'blocked', 'handover_required', 'done')",
            name="ck_contexts_status",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_task: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active"
    )
    last_agent_used: Mapped[str | None] = mapped_column(String(64))
    # Free-form durable facts the agents should always be told about.
    memory: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )

    project: Mapped[Project] = relationship(back_populates="context")


class Event(TimestampPK, Base):
    """Append-only history. Never updated, never deleted."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "type IN ('note', 'user_message', 'agent_reply', "
            "'context_update', 'handover', 'error')",
            name="ck_events_type",
        ),
        Index("ix_events_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    project: Mapped[Project] = relationship(back_populates="events")


class Agent(TimestampPK, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class Handover(TimestampPK, Base):
    """Snapshot written when one agent stops and another must pick up."""

    __tablename__ = "handovers"
    __table_args__ = (
        Index("ix_handovers_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_agent: Mapped[str] = mapped_column(String(64), nullable=False)
    to_agent: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    last_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_next_step: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    # Full copy of the context at handover time, so the snapshot stays truthful
    # even after the live context row moves on.
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
