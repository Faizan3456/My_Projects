"""Agent catalogue.

The connector registry is the source of truth for which agents exist and which
are usable; the `agents` table is a mirror kept up to date on every read so
reporting queries can join against it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo, schemas
from ..connectors.registry import ConnectorRegistry, get_registry
from ..db import get_session

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[schemas.AgentOut])
async def list_agents(
    session: AsyncSession = Depends(get_session),
    registry: ConnectorRegistry = Depends(get_registry),
):
    out: list[schemas.AgentOut] = []
    for connector in registry.all():
        await repo.upsert_agent(
            session,
            name=connector.name,
            provider=connector.provider,
            model=connector.model,
            is_active=connector.is_configured,
        )
        out.append(
            schemas.AgentOut(
                name=connector.name,
                provider=connector.provider,
                model=connector.model,
                is_active=connector.is_configured,
                reason=connector.missing_config,
            )
        )
    return out
