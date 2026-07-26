"""Connector registry: name -> connector instance."""

from __future__ import annotations

from ..config import Settings, get_settings
from ..errors import UnknownAgentError
from .base import AgentConnector
from .chatgpt import ChatGPTConnector
from .claude import ClaudeConnector
from .copilot import CopilotConnector
from .echo import EchoConnector
from .gemini import GeminiConnector
from .groq import GroqConnector
from .local import LocalLLMConnector
from .openrouter import OpenRouterConnector

CONNECTOR_CLASSES: tuple[type[AgentConnector], ...] = (
    ClaudeConnector,
    ChatGPTConnector,
    CopilotConnector,
    GeminiConnector,
    GroqConnector,
    OpenRouterConnector,
    LocalLLMConnector,
    EchoConnector,
)


class ConnectorRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._connectors: dict[str, AgentConnector] = {
            cls.name: cls(self.settings) for cls in CONNECTOR_CLASSES
        }

    def get(self, name: str) -> AgentConnector:
        try:
            return self._connectors[name.strip().lower()]
        except KeyError:
            raise UnknownAgentError(
                f"Unknown agent {name!r}. Known agents: "
                + ", ".join(sorted(self._connectors)),
                agent=name,
            ) from None

    def register(self, connector: AgentConnector) -> None:
        """Add or replace a connector (used by tests and custom providers)."""
        self._connectors[connector.name] = connector

    def all(self) -> list[AgentConnector]:
        return [self._connectors[name] for name in sorted(self._connectors)]

    def active(self) -> list[AgentConnector]:
        return [c for c in self.all() if c.is_configured]


_registry: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry


def set_registry(registry: ConnectorRegistry | None) -> None:
    """Override the process-wide registry (tests)."""
    global _registry
    _registry = registry
