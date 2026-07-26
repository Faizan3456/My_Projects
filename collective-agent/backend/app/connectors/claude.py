"""Anthropic Claude connector (Messages API)."""

from __future__ import annotations

import httpx

from ..errors import AgentCallError
from .base import AgentConnector, AgentReply, Prompt

ANTHROPIC_VERSION = "2023-06-01"


class ClaudeConnector(AgentConnector):
    name = "claude"
    provider = "anthropic"

    @property
    def model(self) -> str:
        return self.settings.anthropic_model

    @property
    def missing_config(self) -> str | None:
        if not self.settings.anthropic_api_key:
            return "ANTHROPIC_API_KEY is not set"
        return None

    async def _complete(
        self, client: httpx.AsyncClient, prompt: Prompt
    ) -> AgentReply:
        messages = [*prompt.history, {"role": "user", "content": prompt.user}]
        response = await client.post(
            f"{self.settings.anthropic_base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                # Anthropic takes the system prompt as a top-level parameter
                # rather than a message with role="system".
                "system": prompt.system,
                "messages": messages,
                "max_tokens": self.settings.agent_max_tokens,
            },
        )
        self._raise_for_status(response)
        body = response.json()
        return AgentReply(
            text=self._join_text_blocks(body),
            model=body.get("model") or self.model,
            usage=body.get("usage") or {},
            limits=self._rate_limits(response),
        )

    def _join_text_blocks(self, body: dict) -> str:
        """Concatenate the text blocks of a Messages response.

        The reply is a list of content blocks and text is not guaranteed to be
        first: reasoning models emit a `thinking` block ahead of it, and tool use
        adds `tool_use` blocks. Indexing content[0] breaks on all of those.
        """
        blocks = body.get("content")
        if not isinstance(blocks, list):
            raise AgentCallError(
                f"Agent {self.name!r} returned no content array", agent=self.name
            )
        text = "\n".join(
            block["text"]
            for block in blocks
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ).strip()
        if not text:
            raise AgentCallError(
                f"Agent {self.name!r} returned no text block",
                agent=self.name,
                # Naming the shapes we did get makes the next failure obvious.
                block_types=",".join(
                    str(b.get("type")) for b in blocks if isinstance(b, dict)
                )
                or "none",
                stop_reason=str(body.get("stop_reason")),
            )
        return text
