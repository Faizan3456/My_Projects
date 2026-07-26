"""Groq connector.

Groq has a genuine free API tier — no card required — and is the fastest of the
hosted providers by a wide margin, which makes it a good default when a turn
needs answering quickly rather than deeply. OpenAI-compatible wire format.

Get a key at https://console.groq.com/keys
"""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleConnector


class GroqConnector(OpenAICompatibleConnector):
    name = "groq"
    provider = "groq"

    @property
    def model(self) -> str:
        return self.settings.groq_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.groq_api_key:
            return "GROQ_API_KEY is not set"
        return None

    def _base_url(self) -> str:
        return self.settings.groq_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
