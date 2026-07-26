"""Offline connector used for demos, smoke tests and CI.

It never calls the network. It answers in the same structured format the real
connectors are asked for, so the whole memory/handover loop can be exercised
without a single API key. Send the message "SIMULATE_LIMIT" to make it raise a
limit error and trigger the handover path.
"""

from __future__ import annotations

import json

import httpx

from ..errors import AgentLimitError
from .base import AgentConnector, AgentReply, Prompt

LIMIT_TRIGGER = "SIMULATE_LIMIT"


class EchoConnector(AgentConnector):
    name = "echo"
    provider = "offline"

    @property
    def model(self) -> str:
        return "echo-1"

    @property
    def missing_config(self) -> str | None:
        if not self.settings.enable_echo_connector:
            return "ENABLE_ECHO_CONNECTOR is false"
        return None

    async def _complete(
        self, client: httpx.AsyncClient, prompt: Prompt
    ) -> AgentReply:
        # Read the instruction only, not the briefing: the trigger phrase will
        # still be sitting in the project history on every later turn.
        instruction = prompt.instruction.strip() or prompt.user.strip()
        if LIMIT_TRIGGER in instruction:
            raise AgentLimitError(
                "Simulated limit reached", agent=self.name, simulated=True
            )

        block = {
            "summary": f"Echo agent acknowledged: {instruction[:200]}",
            "next_step": "Review the echo output and pick a real agent.",
            "status": "active",
        }
        return AgentReply(
            text=(
                f"Working offline on: {instruction}\n\n"
                "No external model was called.\n\n"
                "```json\n" + json.dumps(block, indent=2) + "\n```"
            ),
            model=self.model,
            usage={"input_tokens": len(prompt.user.split())},
        )
