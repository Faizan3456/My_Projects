"""Shared implementation for providers speaking the OpenAI chat wire format.

Used by ChatGPT (api.openai.com), Copilot (GitHub Models) and local LLM servers
(Ollama / vLLM / LM Studio, all of which expose /v1/chat/completions).
"""

from __future__ import annotations

import httpx

from .base import AgentConnector, AgentReply, Prompt


class OpenAICompatibleConnector(AgentConnector):
    def _endpoint(self) -> str:
        return f"{self._base_url().rstrip('/')}/chat/completions"

    def _base_url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    async def _complete(
        self, client: httpx.AsyncClient, prompt: Prompt
    ) -> AgentReply:
        messages = [{"role": "system", "content": prompt.system}]
        messages.extend(prompt.history)
        messages.append({"role": "user", "content": prompt.user})

        response = await client.post(
            self._endpoint(),
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": self.settings.agent_max_tokens,
                "temperature": 0.2,
            },
        )
        self._raise_for_status(response)
        body = response.json()
        return AgentReply(
            text=self._first_text(body, "choices", 0, "message", "content"),
            model=body.get("model") or self.model,
            usage=body.get("usage") or {},
            limits=self._rate_limits(response),
        )
