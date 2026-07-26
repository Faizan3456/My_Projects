"""Local LLM connector for any OpenAI-compatible server.

Works with Ollama (`http://localhost:11434/v1`), vLLM, LM Studio and
llama.cpp's server. No credential is required; the connector is inactive until
LOCAL_LLM_BASE_URL is set.
"""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleConnector


class LocalLLMConnector(OpenAICompatibleConnector):
    name = "local"
    provider = "local"

    @property
    def model(self) -> str:
        return self.settings.local_llm_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.local_llm_base_url:
            return "LOCAL_LLM_BASE_URL is not set"
        return None

    def _base_url(self) -> str:
        return self.settings.local_llm_base_url

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}
