"""Google Gemini connector (generateContent API)."""

from __future__ import annotations

import httpx

from ..errors import AgentCallError
from .base import AgentConnector, AgentReply, Prompt


class GeminiConnector(AgentConnector):
    name = "gemini"
    provider = "google"

    @property
    def model(self) -> str:
        return self.settings.gemini_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.google_api_key:
            return "GOOGLE_API_KEY is not set"
        return None

    async def _complete(
        self, client: httpx.AsyncClient, prompt: Prompt
    ) -> AgentReply:
        contents = [
            {
                # Gemini names the assistant role "model".
                "role": "model" if turn["role"] == "assistant" else "user",
                "parts": [{"text": turn["content"]}],
            }
            for turn in prompt.history
        ]
        contents.append({"role": "user", "parts": [{"text": prompt.user}]})

        base = self.settings.gemini_base_url.rstrip("/")
        response = await client.post(
            f"{base}/models/{self.model}:generateContent",
            params={"key": self.settings.google_api_key},
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": prompt.system}]},
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": self.settings.agent_max_tokens,
                    "temperature": 0.2,
                },
            },
        )
        self._raise_for_status(response)
        body = response.json()
        return AgentReply(
            text=self._join_parts(body),
            model=self.model,
            usage=body.get("usageMetadata") or {},
            # Gemini publishes no rate-limit headers; this stays empty and the
            # dashboard shows usage only for it.
            limits=self._rate_limits(response),
        )

    def _join_parts(self, body: dict) -> str:
        """Concatenate the text parts of the first candidate.

        As with Anthropic, text is not guaranteed to be the first part: thinking
        models put a thought part ahead of it, and a blocked response has no text
        part at all — only a finishReason worth reporting.
        """
        candidates = body.get("candidates") or []
        if not candidates:
            raise AgentCallError(
                f"Agent {self.name!r} returned no candidates",
                agent=self.name,
                block_reason=str(
                    (body.get("promptFeedback") or {}).get("blockReason")
                ),
            )
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text = "\n".join(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
        if not text:
            raise AgentCallError(
                f"Agent {self.name!r} returned no text part",
                agent=self.name,
                finish_reason=str(candidates[0].get("finishReason")),
            )
        return text
