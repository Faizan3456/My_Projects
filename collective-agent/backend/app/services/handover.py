"""Handover protocol.

A handover is the moment one agent stops and another must pick up. It writes
three things atomically: a snapshot row, a `handover` event, and a context whose
status is `handover_required` so the dashboard can raise an alert.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, repositories as repo, schemas
from ..models import utcnow


def snapshot_context(context: models.Context) -> dict[str, Any]:
    return {
        "current_task": context.current_task,
        "next_step": context.next_step,
        "status": context.status,
        "last_agent_used": context.last_agent_used,
        "memory": dict(context.memory),
        "captured_at": utcnow().isoformat(),
    }


async def create_handover(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    from_agent: str,
    reason: str,
    last_action: str = "",
    suggested_next_step: str = "",
    to_agent: str | None = None,
) -> tuple[models.Handover, models.Context]:
    context = await repo.get_context(session, project_id)
    handover = await repo.add_handover(
        session,
        project_id=project_id,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
        last_action=last_action,
        # Fall back to the stored next step: a handover with no forward
        # instruction is useless to the next agent.
        suggested_next_step=suggested_next_step or context.next_step,
        context_snapshot=snapshot_context(context),
    )
    await repo.add_event(
        session,
        project_id,
        type="handover",
        agent_name=from_agent,
        summary=f"{from_agent} handed over: {reason}",
        payload={
            "handover_id": str(handover.id),
            "reason": reason,
            "last_action": last_action,
            "suggested_next_step": handover.suggested_next_step,
            "to_agent": to_agent,
        },
    )
    context = await repo.update_context(
        session,
        project_id,
        schemas.ContextUpdate(
            status="handover_required",
            next_step=handover.suggested_next_step,
            last_agent_used=from_agent,
        ),
    )
    return handover, context


async def open_handover(
    session: AsyncSession, project_id: uuid.UUID
) -> models.Handover | None:
    """Most recent unresolved handover for a project, if any."""
    pending = await repo.list_handovers(
        session, project_id, unresolved_only=True, limit=1
    )
    return pending[0] if pending else None


async def resolve_handover(
    session: AsyncSession,
    handover: models.Handover,
    *,
    to_agent: str,
    reactivate: bool = True,
) -> models.Handover:
    handover.to_agent = to_agent
    handover.resolved_at = utcnow()
    await repo.add_event(
        session,
        handover.project_id,
        type="context_update",
        agent_name=to_agent,
        summary=f"{to_agent} picked up the handover from {handover.from_agent}",
        payload={"handover_id": str(handover.id)},
    )
    if reactivate:
        await repo.update_context(
            session,
            handover.project_id,
            schemas.ContextUpdate(status="active"),
        )
    await session.flush()
    return handover
