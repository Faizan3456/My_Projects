"""GitHub Copilot connector.

Copilot's IDE completion API is not publicly callable outside the editor
extensions. The supported way to reach the same model family with a GitHub
credential is GitHub Models, which is OpenAI-wire-compatible, so this connector
targets that endpoint with a GITHUB_TOKEN. Point COPILOT_BASE_URL at any other
OpenAI-compatible gateway (e.g. Azure OpenAI) if your org uses one instead.
"""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleConnector


class CopilotConnector(OpenAICompatibleConnector):
    name = "copilot"
    provider = "github"

    @property
    def model(self) -> str:
        return self.settings.copilot_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.github_token:
            return "GITHUB_TOKEN is not set"
        return None

    def _base_url(self) -> str:
        return self.settings.copilot_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Content-Type": "application/json",
        }
