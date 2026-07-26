"""Handover endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo, schemas
from ..db import get_session
from ..services import handover as handover_service

router = APIRouter(prefix="/handover", tags=["handover"])


@router.post(
    "", response_model=schemas.HandoverOut, status_code=status.HTTP_201_CREATED
)
async def create_handover(
    data: schemas.HandoverCreate, session: AsyncSession = Depends(get_session)
):
    """Record that an agent stopped and the work needs a new owner.

    Called by the orchestrator automatically when a connector reports a limit,
    and available to clients that detect a limit themselves (e.g. a user hitting
    a plan cap inside a chat UI).
    """
    await repo.get_project(session, data.project_id)
    handover, _ = await handover_service.create_handover(
        session,
        project_id=data.project_id,
        from_agent=data.from_agent,
        reason=data.reason,
        last_action=data.last_action,
        suggested_next_step=data.suggested_next_step,
        to_agent=data.to_agent,
    )
    return handover


@router.get("/{handover_id}", response_model=schemas.HandoverOut)
async def get_handover(
    handover_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await repo.get_handover(session, handover_id)


@router.post("/{handover_id}/resolve", response_model=schemas.HandoverOut)
async def resolve_handover(
    handover_id: uuid.UUID,
    data: schemas.HandoverResolve,
    session: AsyncSession = Depends(get_session),
):
    """Mark a handover as accepted by `to_agent` and reactivate the project."""
    handover = await repo.get_handover(session, handover_id)
    return await handover_service.resolve_handover(
        session, handover, to_agent=data.to_agent
    )
