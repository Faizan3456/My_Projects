"""Run one agent turn against a project's shared memory."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..auth import Principal, require_principal
from ..connectors.registry import ConnectorRegistry, get_registry
from ..db import get_session
from ..services.orchestrator import run_turn

router = APIRouter(prefix="/projects", tags=["turns"])


@router.post("/{project_id}/turns", response_model=schemas.TurnResponse)
async def create_turn(
    project_id: uuid.UUID,
    data: schemas.TurnRequest,
    session: AsyncSession = Depends(get_session),
    registry: ConnectorRegistry = Depends(get_registry),
    principal: Principal = Depends(require_principal),
):
    """Fetch context, call the chosen agent, and write the result to memory.

    Returns 200 with `status: "handover_required"` (not an error) when the agent
    hit a limit — the work is not lost, it just needs a different agent.
    """
    result = await run_turn(
        session, project_id, data, registry=registry, actor=principal.label
    )
    return schemas.TurnResponse(
        status=result.status,
        agent_name=result.agent_name,
        reply=result.reply,
        summary=result.summary,
        context=schemas.ContextOut.model_validate(result.context),
        event=(
            schemas.EventOut.model_validate(result.event) if result.event else None
        ),
        handover=(
            schemas.HandoverOut.model_validate(result.handover)
            if result.handover
            else None
        ),
    )
