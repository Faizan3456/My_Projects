"""Identity: nothing spendable is reachable without a verified principal.

Tokens here are signed with a locally generated RSA key that is installed into
the key store, so the real verification path runs — signature, issuer, audience,
expiry and tenant are all genuinely checked, with no network access.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from app.auth import EntraKeyStore, set_key_store
from app.config import get_settings

from .conftest import build_app

TENANT = "e9ba7eeb-8895-4350-8157-d17f5f523df3"
CLIENT = "11111111-2222-3333-4444-555555555555"
KID = "test-signing-key"
SERVICE_TOKEN = "s3rvice-token-for-tests"


class StubKeyStore(EntraKeyStore):
    """Serves one in-memory public key instead of calling Entra ID."""

    def __init__(self, settings, public_key) -> None:
        super().__init__(settings)
        self._keys = {KID: public_key}
        self._fetched_at = time.monotonic()

    async def refresh(self) -> None:
        """Stands in for a real refresh without any network access.

        The key set is unchanged, which is exactly what Entra ID would return
        for a key id it has never published.
        """
        self._fetched_at = time.monotonic()


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(
    signing_key,
    *,
    audience: str = f"api://{CLIENT}",
    issuer: str = f"https://login.microsoftonline.com/{TENANT}/v2.0",
    tid: str = TENANT,
    upn: str = "faizan@openedgetechnologies.com",
    name: str = "Faizan Fayyaz",
    expires_in: int = 600,
    kid: str = KID,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "aud": audience,
            "iss": issuer,
            "iat": now,
            "nbf": now,
            "exp": now + expires_in,
            "tid": tid,
            "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "preferred_username": upn,
            "name": name,
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest_asyncio.fixture
async def entra_client(signing_key, monkeypatch) -> AsyncIterator[AsyncClient]:
    for key, value in {
        "AUTH_MODE": "entra",
        "ENTRA_TENANT_ID": TENANT,
        "ENTRA_CLIENT_ID": CLIENT,
        "SERVICE_TOKEN": SERVICE_TOKEN,
        "ENTRA_ALLOWED_USERS": "",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    set_key_store(StubKeyStore(get_settings(), signing_key.public_key()))

    async with build_app() as app:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=30
        ) as client:
            yield client

    set_key_store(None)
    get_settings.cache_clear()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- the gate ---------------------------------------------------------------


async def test_health_stays_open_for_probes(entra_client: AsyncClient):
    response = await entra_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["auth_mode"] == "entra"


async def test_every_data_route_requires_a_principal(entra_client: AsyncClient):
    pid = uuid.uuid4()
    for method, path in [
        ("get", "/projects"),
        ("post", "/projects"),
        ("get", f"/projects/{pid}/context"),
        ("post", f"/projects/{pid}/context"),
        ("get", f"/projects/{pid}/events"),
        ("post", f"/projects/{pid}/turns"),
        ("get", f"/projects/{pid}/handovers"),
        ("post", "/handover"),
        ("get", "/agents"),
        ("get", "/whoami"),
    ]:
        response = await entra_client.request(method.upper(), path, json={})
        assert response.status_code == 401, f"{method} {path} was reachable"
        assert response.json()["error"] == "unauthenticated"


async def test_a_valid_token_gets_in(entra_client: AsyncClient, signing_key):
    response = await entra_client.get(
        "/whoami", headers=auth(make_token(signing_key))
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "name": "Faizan Fayyaz",
        "kind": "user",
    }


async def test_the_bare_client_id_is_also_accepted_as_audience(
    entra_client: AsyncClient, signing_key
):
    token = make_token(signing_key, audience=CLIENT)
    assert (await entra_client.get("/whoami", headers=auth(token))).status_code == 200


# --- rejections -------------------------------------------------------------


async def test_a_token_for_another_audience_is_rejected(
    entra_client: AsyncClient, signing_key
):
    token = make_token(signing_key, audience="api://some-other-app")
    response = await entra_client.get("/whoami", headers=auth(token))
    assert response.status_code == 401
    assert "Audience" in response.json()["message"] or "aud" in response.json()["message"]


async def test_a_token_from_another_tenant_is_rejected(
    entra_client: AsyncClient, signing_key
):
    other = "99999999-8888-7777-6666-555555555555"
    token = make_token(
        signing_key,
        issuer=f"https://login.microsoftonline.com/{other}/v2.0",
        tid=other,
    )
    assert (await entra_client.get("/whoami", headers=auth(token))).status_code == 401


async def test_a_tenant_swap_inside_a_valid_issuer_is_rejected(
    entra_client: AsyncClient, signing_key
):
    """Right issuer, wrong `tid` — the claim is checked, not just the URL."""
    token = make_token(signing_key, tid="99999999-8888-7777-6666-555555555555")
    response = await entra_client.get("/whoami", headers=auth(token))
    assert response.status_code == 401
    assert "different tenant" in response.json()["message"]


async def test_an_expired_token_is_rejected(entra_client: AsyncClient, signing_key):
    token = make_token(signing_key, expires_in=-30)
    response = await entra_client.get("/whoami", headers=auth(token))
    assert response.status_code == 401
    assert "expired" in response.json()["message"].lower()


async def test_a_token_signed_by_someone_else_is_rejected(entra_client: AsyncClient):
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(attacker)  # same claims, wrong key
    assert (await entra_client.get("/whoami", headers=auth(token))).status_code == 401


async def test_an_unknown_key_id_is_rejected(entra_client: AsyncClient, signing_key):
    token = make_token(signing_key, kid="not-a-key-we-know")
    assert (await entra_client.get("/whoami", headers=auth(token))).status_code == 401


async def test_garbage_is_rejected_without_a_traceback(entra_client: AsyncClient):
    response = await entra_client.get("/whoami", headers=auth("not-a-jwt"))
    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


async def test_an_unsigned_token_is_rejected(entra_client: AsyncClient):
    """The classic alg=none downgrade."""
    token = jwt.encode(
        {
            "aud": f"api://{CLIENT}",
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "tid": TENANT,
        },
        key="",
        algorithm="none",
        headers={"kid": KID},
    )
    assert (await entra_client.get("/whoami", headers=auth(token))).status_code == 401


# --- allow list -------------------------------------------------------------


async def test_an_account_outside_the_allow_list_is_forbidden(
    signing_key, monkeypatch
):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setenv("ENTRA_ALLOWED_USERS", "faizan@openedgetechnologies.com")
    get_settings.cache_clear()
    set_key_store(StubKeyStore(get_settings(), signing_key.public_key()))

    async with build_app() as app:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            allowed = make_token(signing_key)
            assert (
                await client.get("/whoami", headers=auth(allowed))
            ).status_code == 200

            stranger = make_token(signing_key, upn="someone@example.com")
            response = await client.get("/whoami", headers=auth(stranger))
            assert response.status_code == 403
            assert response.json()["error"] == "forbidden"

    set_key_store(None)
    get_settings.cache_clear()


# --- service token ----------------------------------------------------------


async def test_the_service_token_works_for_scripts(entra_client: AsyncClient):
    response = await entra_client.get(
        "/whoami", headers={"X-Service-Token": SERVICE_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "service"


async def test_a_wrong_service_token_is_rejected(entra_client: AsyncClient):
    response = await entra_client.get(
        "/whoami", headers={"X-Service-Token": "wrong"}
    )
    assert response.status_code == 401


async def test_a_service_token_can_run_a_turn(entra_client: AsyncClient):
    headers = {"X-Service-Token": SERVICE_TOKEN}
    project = await entra_client.post(
        "/projects", json={"name": "Service run", "next_step": "do the thing"},
        headers=headers,
    )
    assert project.status_code == 201
    turn = await entra_client.post(
        f"/projects/{project.json()['id']}/turns",
        json={"agent_name": "echo", "message": "go"},
        headers=headers,
    )
    assert turn.status_code == 200
    events = await entra_client.get(
        f"/projects/{project.json()['id']}/events", headers=headers
    )
    # The actor is recorded next to the agent, so history says who asked.
    user_message = [e for e in events.json() if e["type"] == "user_message"][0]
    assert user_message["payload"]["actor"] == "service token (service)"


# --- production guardrail ---------------------------------------------------


async def test_production_refuses_to_start_without_auth(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Refusing to start"):
            async with build_app():
                pass
    finally:
        get_settings.cache_clear()


async def test_production_starts_once_auth_is_configured(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    get_settings.cache_clear()
    try:
        async with build_app() as app:
            assert app is not None
    finally:
        get_settings.cache_clear()
