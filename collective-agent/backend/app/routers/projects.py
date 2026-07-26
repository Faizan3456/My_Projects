"""Projects, their live context, and their history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo, schemas
from ..db import get_session

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[schemas.ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)):
    return await repo.list_projects(session)


@router.post(
    "", response_model=schemas.ProjectDetailOut, status_code=status.HTTP_201_CREATED
)
async def create_project(
    data: schemas.ProjectCreate, session: AsyncSession = Depends(get_session)
):
    project = await repo.create_project(session, data)
    await repo.add_event(
        session,
        project.id,
        type="note",
        summary=f"Project {project.name!r} created",
    )
    return project


@router.get("/{project_id}", response_model=schemas.ProjectDetailOut)
async def get_project(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await repo.get_project(session, project_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def clear_all_projects(
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete every conversation and everything in it.

    Irreversible, so the dashboard confirms first. A separate route rather than a
    flag on the single delete, so it cannot be reached by a malformed id.
    """
    for project in await repo.list_projects(session):
        await session.delete(project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_project(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Response:
    await repo.delete_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- context ---------------------------------------------------------------


@router.get("/{project_id}/context", response_model=schemas.ContextOut)
async def get_context(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await repo.get_context(session, project_id)


@router.post("/{project_id}/context", response_model=schemas.ContextOut)
async def update_context(
    project_id: uuid.UUID,
    data: schemas.ContextUpdate,
    session: AsyncSession = Depends(get_session),
    replace_memory: bool = Query(
        False,
        description="Replace the memory object instead of merging keys into it.",
    ),
):
    context = await repo.update_context(
        session, project_id, data, merge_memory=not replace_memory
    )
    changed = ", ".join(sorted(data.model_dump(exclude_unset=True))) or "nothing"
    await repo.add_event(
        session,
        project_id,
        type="context_update",
        agent_name=data.last_agent_used,
        summary=f"Context updated ({changed})",
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    return context


# --- events ----------------------------------------------------------------


@router.get("/{project_id}/events", response_model=list[schemas.EventOut])
async def list_events(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    await repo.get_project(session, project_id)
    return await repo.list_events(session, project_id, limit=limit, offset=offset)


@router.post(
    "/{project_id}/events",
    response_model=schemas.EventOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_event(
    project_id: uuid.UUID,
    data: schemas.EventCreate,
    session: AsyncSession = Depends(get_session),
):
    await repo.get_project(session, project_id)
    return await repo.add_event(
        session,
        project_id,
        type=data.type,
        summary=data.summary,
        agent_name=data.agent_name,
        payload=data.payload,
    )


# --- handovers for one project ---------------------------------------------


@router.get("/{project_id}/handovers", response_model=list[schemas.HandoverOut])
async def list_handovers(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    unresolved_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
):
    await repo.get_project(session, project_id)
    return await repo.list_handovers(
        session, project_id, unresolved_only=unresolved_only, limit=limit
    )
