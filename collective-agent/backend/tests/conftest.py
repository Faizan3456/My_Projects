from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Configure before app modules read settings. The suite must not inherit the
# developer's .env, or a local DATABASE_URL / DB_AUTO_CREATE would change what
# the tests actually exercise.
os.environ["COLLECTIVE_IGNORE_ENV_FILE"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DB_AUTO_CREATE"] = "true"
os.environ["ENABLE_ECHO_CONNECTOR"] = "true"
# Most tests are about memory and agents, not identity. test_auth.py rebuilds the
# app with AUTH_MODE=entra to cover the real verification path.
os.environ["AUTH_MODE"] = "disabled"
os.environ["ENVIRONMENT"] = "development"
for key in (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "LOCAL_LLM_BASE_URL",
):
    os.environ[key] = ""

from app import db as db_module  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _settings():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url.startswith("sqlite"), "tests must not hit postgres"
    return settings


@asynccontextmanager
async def build_app() -> AsyncIterator:
    """A fresh app on a fresh in-memory database.

    A StaticPool keeps the single SQLite connection alive so every session in
    the test observes the same in-memory database.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    db_module._engine = engine
    db_module._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    application = create_app()
    try:
        async with application.router.lifespan_context(application):
            yield application
    finally:
        await engine.dispose()
        db_module._engine = None
        db_module._sessionmaker = None


@pytest_asyncio.fixture
async def app() -> AsyncIterator:
    async with build_app() as application:
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=30
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def project(client: AsyncClient) -> dict:
    response = await client.post(
        "/projects",
        json={
            "name": "Collective test project",
            "description": "Exercises the shared memory loop",
            "current_task": "Write the first module",
            "next_step": "Draft the data model",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
