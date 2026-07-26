"""Data access. Every read/write of persistent memory goes through here."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, schemas
from .errors import ConflictError, NotFoundError

# --- projects ---------------------------------------------------------------


async def list_projects(session: AsyncSession) -> list[models.Project]:
    result = await session.execute(
        select(models.Project).order_by(models.Project.created_at.desc())
    )
    return list(result.scalars())


async def get_project(
    session: AsyncSession, project_id: uuid.UUID
) -> models.Project:
    project = await session.get(models.Project, project_id)
    if project is None:
        raise NotFoundError(f"No project with id {project_id}")
    return project


async def create_project(
    session: AsyncSession, data: schemas.ProjectCreate
) -> models.Project:
    existing = await session.execute(
        select(models.Project).where(models.Project.name == data.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"A project named {data.name!r} already exists")

    project = models.Project(name=data.name, description=data.description)
    project.context = models.Context(
        current_task=data.current_task,
        next_step=data.next_step,
        status="active",
        memory={},
    )
    session.add(project)
    await session.flush()
    return project


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> None:
    project = await get_project(session, project_id)
    await session.delete(project)


# --- contexts ---------------------------------------------------------------


async def get_context(
    session: AsyncSession, project_id: uuid.UUID
) -> models.Context:
    result = await session.execute(
        select(models.Context).where(models.Context.project_id == project_id)
    )
    context = result.scalar_one_or_none()
    if context is None:
        # A project always has a context; a missing one means the project is
        # missing too (or was created outside the API).
        await get_project(session, project_id)
        context = models.Context(project_id=project_id, status="active", memory={})
        session.add(context)
        await session.flush()
    return context


async def update_context(
    session: AsyncSession,
    project_id: uuid.UUID,
    data: schemas.ContextUpdate,
    *,
    merge_memory: bool = True,
) -> models.Context:
    context = await get_context(session, project_id)
    patch = data.model_dump(exclude_unset=True, exclude_none=True)

    memory = patch.pop("memory", None)
    for field, value in patch.items():
        setattr(context, field, value)
    if memory is not None:
        # Reassign rather than mutate: SQLAlchemy does not track in-place JSON
        # edits without a MutableDict.
        context.memory = {**context.memory, **memory} if merge_memory else memory

    context.updated_at = models.utcnow()
    await session.flush()
    return context


# --- events -----------------------------------------------------------------


async def list_events(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    newest_first: bool = True,
) -> list[models.Event]:
    order = (
        models.Event.created_at.desc()
        if newest_first
        else models.Event.created_at.asc()
    )
    result = await session.execute(
        select(models.Event)
        .where(models.Event.project_id == project_id)
        .order_by(order, models.Event.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


async def recent_agent_events(
    session: AsyncSession, *, limit: int = 1000
) -> list[models.Event]:
    """Agent replies and handovers across all projects, newest first."""
    result = await session.execute(
        select(models.Event)
        .where(models.Event.type.in_(("agent_reply", "handover")))
        .order_by(models.Event.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def add_event(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    type: str,
    summary: str,
    agent_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> models.Event:
    event = models.Event(
        project_id=project_id,
        type=type,
        summary=summary,
        agent_name=agent_name,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
    return event


# --- handovers --------------------------------------------------------------


async def add_handover(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    from_agent: str,
    reason: str,
    last_action: str,
    suggested_next_step: str,
    context_snapshot: dict[str, Any],
    to_agent: str | None = None,
) -> models.Handover:
    handover = models.Handover(
        project_id=project_id,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
        last_action=last_action,
        suggested_next_step=suggested_next_step,
        context_snapshot=context_snapshot,
    )
    session.add(handover)
    await session.flush()
    return handover


async def get_handover(
    session: AsyncSession, handover_id: uuid.UUID
) -> models.Handover:
    handover = await session.get(models.Handover, handover_id)
    if handover is None:
        raise NotFoundError(f"No handover with id {handover_id}")
    return handover


async def list_handovers(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    unresolved_only: bool = False,
    limit: int = 20,
) -> list[models.Handover]:
    stmt = select(models.Handover).where(models.Handover.project_id == project_id)
    if unresolved_only:
        stmt = stmt.where(models.Handover.resolved_at.is_(None))
    stmt = stmt.order_by(models.Handover.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars())


# --- agents (registry mirror) ----------------------------------------------


async def upsert_agent(
    session: AsyncSession,
    *,
    name: str,
    provider: str,
    model: str | None,
    is_active: bool,
) -> models.Agent:
    result = await session.execute(
        select(models.Agent).where(models.Agent.name == name)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = models.Agent(name=name, provider=provider)
        session.add(agent)
    agent.provider = provider
    agent.model = model
    agent.is_active = is_active
    await session.flush()
    return agent


async def list_agents(session: AsyncSession) -> list[models.Agent]:
    result = await session.execute(
        select(models.Agent).order_by(models.Agent.name)
    )
    return list(result.scalars())
