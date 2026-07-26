"""Connector contract shared by every provider.

An external agent is treated as a stateless tool: it is handed a fully-formed
prompt built from shared memory and returns text. It holds no state of its own,
so any agent can pick up any project at any point.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import Settings
from ..errors import AgentCallError, AgentLimitError, AgentNotConfiguredError

# Substrings that mean "this agent cannot continue" rather than "this call was
# malformed". Matched case-insensitively against provider error bodies.
LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "quota",
    "insufficient_quota",
    "too many requests",
    "overloaded",
    "capacity",
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "usage limit",
    "billing hard limit",
)
LIMIT_STATUS_CODES = frozenset({429, 529})


@dataclass(slots=True)
class Prompt:
    system: str
    user: str
    # Prior turns, oldest first: [{"role": "user"|"assistant", "content": ...}]
    history: list[dict[str, str]] = field(default_factory=list)
    # The instruction for this turn on its own, without the memory briefing that
    # surrounds it in `user`. Connectors send `user`; this field is for logic
    # that must not confuse the ask with the recorded history.
    instruction: str = ""


@dataclass(slots=True)
class AgentReply:
    text: str
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    # Remaining rate-limit budget reported by the provider on this response.
    # No provider exposes a spendable credit balance through the API, so this is
    # the closest thing to "how much is left" that can be shown truthfully.
    limits: dict[str, Any] = field(default_factory=dict)


class AgentConnector(abc.ABC):
    """Base connector. Subclasses implement a single provider's wire format."""

    name: str = ""
    provider: str = ""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --- capability reporting ---

    @property
    @abc.abstractmethod
    def model(self) -> str | None:
        """Model id this connector will call."""

    @property
    def is_configured(self) -> bool:
        return self.missing_config is None

    @property
    def missing_config(self) -> str | None:
        """Human-readable reason the connector cannot run, or None."""
        return None

    # --- calling ---

    async def complete(self, prompt: Prompt) -> AgentReply:
        if not self.is_configured:
            raise AgentNotConfiguredError(
                f"Agent {self.name!r} is not configured: {self.missing_config}",
                agent=self.name,
            )
        async with httpx.AsyncClient(
            timeout=self.settings.agent_timeout_seconds
        ) as client:
            try:
                return await self._complete(client, prompt)
            except (AgentLimitError, AgentCallError):
                raise
            except httpx.TimeoutException as exc:
                raise AgentCallError(
                    f"Agent {self.name!r} timed out after "
                    f"{self.settings.agent_timeout_seconds:g}s",
                    agent=self.name,
                ) from exc
            except httpx.HTTPError as exc:
                raise AgentCallError(
                    f"Agent {self.name!r} is unreachable: {exc}",
                    agent=self.name,
                ) from exc

    @abc.abstractmethod
    async def _complete(
        self, client: httpx.AsyncClient, prompt: Prompt
    ) -> AgentReply: ...

    # --- shared error mapping ---

    @staticmethod
    def _explain(body: str) -> str:
        """Pull the provider's own sentence out of an error body.

        "hit a limit (HTTP 429)" tells nobody what to do; "insufficient_quota:
        You exceeded your current quota" is actionable. Providers nest the text
        differently, so try the known shapes before falling back to raw text.
        """
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return " ".join(body.split())[:200]

        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or ""
            code = error.get("code") or error.get("type") or ""
            if message and code and str(code) not in str(message):
                return f"{code}: {message}"[:300]
            if message:
                return str(message)[:300]
        if isinstance(error, str):
            return error[:300]
        if isinstance(data, dict) and isinstance(data.get("message"), str):
            return data["message"][:300]
        return " ".join(body.split())[:200]

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        body = response.text[:2000]
        lowered = body.lower()
        detail = self._explain(body)
        hit_limit = response.status_code in LIMIT_STATUS_CODES or any(
            marker in lowered for marker in LIMIT_MARKERS
        )
        if hit_limit:
            raise AgentLimitError(
                f"{self.name} hit a limit (HTTP {response.status_code}) — {detail}",
                agent=self.name,
                status_code=response.status_code,
                body=body,
            )
        raise AgentCallError(
            f"{self.name} failed (HTTP {response.status_code}) — {detail}",
            agent=self.name,
            status_code=response.status_code,
            body=body,
        )

    # Header names differ per provider; the meaning does not.
    RATE_LIMIT_HEADERS = {
        "requests_remaining": (
            "anthropic-ratelimit-requests-remaining",
            "x-ratelimit-remaining-requests",
        ),
        "requests_limit": (
            "anthropic-ratelimit-requests-limit",
            "x-ratelimit-limit-requests",
        ),
        "tokens_remaining": (
            "anthropic-ratelimit-tokens-remaining",
            "x-ratelimit-remaining-tokens",
        ),
        "tokens_limit": (
            "anthropic-ratelimit-tokens-limit",
            "x-ratelimit-limit-tokens",
        ),
        "resets_at": (
            "anthropic-ratelimit-requests-reset",
            "x-ratelimit-reset-requests",
        ),
    }

    def _rate_limits(self, response: httpx.Response) -> dict[str, Any]:
        """Remaining allowance, read from whichever headers the provider sends."""
        found: dict[str, Any] = {}
        for field_name, candidates in self.RATE_LIMIT_HEADERS.items():
            for header in candidates:
                value = response.headers.get(header)
                if value is None:
                    continue
                found[field_name] = int(value) if value.isdigit() else value
                break
        return found

    def _first_text(self, value: Any, *path: str | int) -> str:
        """Walk a decoded JSON body, raising a clear error if the shape is off."""
        node: Any = value
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError) as exc:
                raise AgentCallError(
                    f"Agent {self.name!r} returned an unexpected response shape",
                    agent=self.name,
                    missing=key,
                ) from exc
        if not isinstance(node, str):
            raise AgentCallError(
                f"Agent {self.name!r} returned a non-text response",
                agent=self.name,
            )
        return node
