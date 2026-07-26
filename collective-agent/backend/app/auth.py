"""Authentication.

Two ways in, both optional per environment:

* **Entra ID** — the dashboard signs the user in against the tenant and sends the
  resulting access token as `Authorization: Bearer <jwt>`. The token is verified
  against the tenant's published signing keys; nothing is trusted from its
  unverified claims.
* **Service token** — a shared secret in `X-Service-Token`, for scripts and
  cron. No identity, so it is recorded as a service principal.

`AUTH_MODE=disabled` exists for local development only; the app refuses to start
with it in production, because an open turn endpoint spends real money on
provider API calls.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import jwt
from fastapi import Depends, Request

from .config import Settings, get_settings
from .errors import CollectiveError

log = logging.getLogger(__name__)

AUTH_MODES = ("entra", "token", "disabled")
ENTRA_BASE = "https://login.microsoftonline.com"


class AuthenticationError(CollectiveError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(CollectiveError):
    status_code = 403
    code = "forbidden"


class AuthConfigurationError(CollectiveError):
    status_code = 500
    code = "auth_misconfigured"


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request."""

    subject: str
    name: str
    kind: Literal["user", "service", "anonymous"]

    @property
    def label(self) -> str:
        return f"{self.name} ({self.kind})"


ANONYMOUS = Principal(subject="local", name="local development", kind="anonymous")


# --- signing keys -----------------------------------------------------------


class EntraKeyStore:
    """Caches the tenant's JWKS, refreshing when a key id is unknown."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    @property
    def jwks_url(self) -> str:
        return (
            f"{ENTRA_BASE}/{self.settings.entra_tenant_id}"
            "/discovery/v2.0/keys"
        )

    def _stale(self) -> bool:
        return (
            time.monotonic() - self._fetched_at > self.settings.jwks_ttl_seconds
        )

    async def key_for(self, kid: str) -> Any:
        if kid not in self._keys or self._stale():
            await self.refresh()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthenticationError(
                "Token was signed with an unknown key", kid=kid
            ) from None

    async def refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                jwks = jwt.PyJWKSet.from_dict(response.json())
        except httpx.HTTPError as exc:
            raise AuthenticationError(
                f"Cannot reach the Entra ID signing keys: {exc}"
            ) from exc
        except jwt.PyJWKSetError as exc:
            raise AuthenticationError(
                f"Entra ID returned an unusable key set: {exc}"
            ) from exc
        self._keys = {key.key_id: key.key for key in jwks.keys if key.key_id}
        self._fetched_at = time.monotonic()
        log.info("loaded %d Entra ID signing keys", len(self._keys))


_key_store: EntraKeyStore | None = None


def get_key_store() -> EntraKeyStore:
    global _key_store
    if _key_store is None:
        _key_store = EntraKeyStore(get_settings())
    return _key_store


def set_key_store(store: EntraKeyStore | None) -> None:
    """Override the process-wide key store (tests)."""
    global _key_store
    _key_store = store


# --- verification -----------------------------------------------------------


def audiences(settings: Settings) -> list[str]:
    """Both forms Entra may issue for a SPA calling its own API."""
    client_id = settings.entra_client_id
    return [client_id, f"api://{client_id}"]


async def principal_from_jwt(token: str, settings: Settings) -> Principal:
    if not settings.entra_tenant_id or not settings.entra_client_id:
        raise AuthConfigurationError(
            "AUTH_MODE=entra requires ENTRA_TENANT_ID and ENTRA_CLIENT_ID"
        )

    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Malformed token: {exc}") from exc
    if not kid:
        raise AuthenticationError("Token has no key id")

    key = await get_key_store().key_for(kid)

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=audiences(settings),
            issuer=f"{ENTRA_BASE}/{settings.entra_tenant_id}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Token rejected: {exc}") from exc

    # A token from another tenant can still carry a valid signature chain, so the
    # tenant id is checked explicitly rather than inferred from the issuer alone.
    if claims.get("tid") != settings.entra_tenant_id:
        raise AuthenticationError("Token was issued by a different tenant")

    upn = (
        claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("email")
        or ""
    )
    allowed = settings.entra_allowed_user_list
    if allowed and upn.lower() not in allowed and claims.get("oid") not in allowed:
        raise AuthorizationError(
            f"{upn or 'this account'} is not on the allow list for this service"
        )

    return Principal(
        subject=claims.get("oid") or claims.get("sub") or "unknown",
        name=claims.get("name") or upn or "Entra user",
        kind="user",
    )


def principal_from_service_token(token: str, settings: Settings) -> Principal:
    expected = settings.service_token
    if not expected:
        raise AuthConfigurationError(
            "A service token was presented but SERVICE_TOKEN is not set"
        )
    # Constant-time: a timing oracle on a shared secret is a real leak.
    if not secrets.compare_digest(token, expected):
        raise AuthenticationError("Service token is not valid")
    return Principal(subject="service-token", name="service token", kind="service")


# --- dependency -------------------------------------------------------------


async def require_principal(request: Request) -> Principal:
    """FastAPI dependency guarding every route except `/healthz`."""
    settings = get_settings()
    mode = settings.auth_mode.strip().lower()

    if mode not in AUTH_MODES:
        raise AuthConfigurationError(
            f"AUTH_MODE must be one of {', '.join(AUTH_MODES)}, not {mode!r}"
        )

    service_token = request.headers.get("x-service-token")
    if service_token:
        if mode == "disabled":
            return ANONYMOUS
        return principal_from_service_token(service_token, settings)

    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")

    if mode == "disabled":
        return ANONYMOUS

    if mode == "token":
        raise AuthenticationError(
            "This service requires an X-Service-Token header"
        )

    if scheme.lower() != "bearer" or not credential:
        raise AuthenticationError(
            "Sign in with Microsoft Entra ID and send the access token as "
            "'Authorization: Bearer <token>'"
        )
    return await principal_from_jwt(credential, settings)


CurrentPrincipal = Depends(require_principal)


def assert_production_is_protected(settings: Settings) -> None:
    """Fail fast rather than serve spendable endpoints to the internet."""
    if settings.environment.lower() != "production":
        if settings.auth_mode == "disabled":
            log.warning(
                "AUTH_MODE=disabled — every endpoint is open. Never do this "
                "outside local development."
            )
        return
    if settings.auth_mode.strip().lower() == "disabled":
        raise RuntimeError(
            "Refusing to start: ENVIRONMENT=production with AUTH_MODE=disabled "
            "would expose the turn endpoint, which spends real money on "
            "provider API calls. Set AUTH_MODE=entra (or token)."
        )
