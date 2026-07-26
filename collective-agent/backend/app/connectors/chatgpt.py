"""OpenAI ChatGPT connector."""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleConnector


class ChatGPTConnector(OpenAICompatibleConnector):
    name = "chatgpt"
    provider = "openai"

    @property
    def model(self) -> str:
        return self.settings.openai_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.openai_api_key:
            return "OPENAI_API_KEY is not set"
        return None

    def _base_url(self) -> str:
        return self.settings.openai_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
