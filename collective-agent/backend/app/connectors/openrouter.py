"""OpenRouter connector.

One key, many models, including free variants (model ids ending `:free`) that
cost nothing but are rate-limited — exactly the condition the handover protocol
exists for. OpenAI-compatible wire format.

Get a key at https://openrouter.ai/keys
"""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleConnector


class OpenRouterConnector(OpenAICompatibleConnector):
    name = "openrouter"
    provider = "openrouter"

    @property
    def model(self) -> str:
        return self.settings.openrouter_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.openrouter_api_key:
            return "OPENROUTER_API_KEY is not set"
        return None

    def _base_url(self) -> str:
        return self.settings.openrouter_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            # OpenRouter attributes traffic with these; they are optional but
            # keep the account's dashboard meaningful.
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": "Collective AI Agent System",
        }
