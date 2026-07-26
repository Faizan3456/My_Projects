"""Shared Memory Service — the brain of the Collective AI Agent System."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, repositories as repo
from .auth import assert_production_is_protected, require_principal
from .config import get_settings
from .connectors.registry import get_registry
from .db import create_all, dispose, get_sessionmaker
from .errors import register_error_handlers
from .routers import agents, handover, manual, projects, turns, usage

log = logging.getLogger(__name__)


async def sync_agent_catalogue() -> None:
    """Mirror the connector registry into the agents table."""
    async with get_sessionmaker()() as session:
        for connector in get_registry().all():
            await repo.upsert_agent(
                session,
                name=connector.name,
                provider=connector.provider,
                model=connector.model,
                is_active=connector.is_configured,
            )
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    if settings.db_auto_create:
        await create_all()
    try:
        await sync_agent_catalogue()
    except Exception:  # a cold database should not stop the API from booting
        log.exception("could not sync the agent catalogue at startup")
    active = [c.name for c in get_registry().active()]
    log.info("active agents: %s", ", ".join(active) or "none")
    yield
    await dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    assert_production_is_protected(settings)
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="One shared memory and one project state across many AI agents.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    # Every route below requires a principal. /healthz is deliberately outside
    # this, so a load balancer can probe it unauthenticated.
    guarded = [Depends(require_principal)]
    app.include_router(projects.router, dependencies=guarded)
    app.include_router(turns.router, dependencies=guarded)
    app.include_router(manual.router, dependencies=guarded)
    app.include_router(agents.router, dependencies=guarded)
    app.include_router(usage.router, dependencies=guarded)
    app.include_router(handover.router, dependencies=guarded)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "environment": settings.environment,
            "auth_mode": settings.auth_mode,
            "active_agents": [c.name for c in get_registry().active()],
        }

    @app.get("/whoami", tags=["meta"])
    async def whoami(principal=Depends(require_principal)) -> dict[str, str]:
        """Lets the dashboard confirm a token is accepted before doing work."""
        return {
            "subject": principal.subject,
            "name": principal.name,
            "kind": principal.kind,
        }

    return app


app = create_app()
