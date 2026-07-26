"""Usage and remaining allowance per agent.

There is no "credits remaining" call to make: Anthropic, OpenAI and Google do not
expose a spendable balance to API keys. What can be reported honestly is

* what this system has spent — token counts recorded on every turn, and
* what the provider says is left — the rate-limit headers on the last response.

Both come out of the event log, so no extra bookkeeping can drift out of sync
with what actually happened.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo, schemas
from ..connectors.registry import ConnectorRegistry, get_registry
from ..db import get_session

router = APIRouter(tags=["usage"])


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


@router.get("/usage", response_model=list[schemas.AgentUsageOut])
async def agent_usage(
    session: AsyncSession = Depends(get_session),
    registry: ConnectorRegistry = Depends(get_registry),
):
    """Per-agent totals across every project, newest limit reading wins."""
    events = await repo.recent_agent_events(session, limit=1000)

    totals: dict[str, dict] = {}
    for event in events:  # newest first
        agent = event.agent_name or "unknown"
        row = totals.setdefault(
            agent,
            {
                "turns": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "limits": {},
                "last_used_at": None,
                "stopped_reason": None,
            },
        )
        if event.type == "agent_reply":
            usage = event.payload.get("usage") or {}
            row["turns"] += 1
            # Anthropic says input_tokens, OpenAI prompt_tokens, Gemini
            # promptTokenCount. Same quantity, three spellings.
            row["input_tokens"] += (
                _int(usage.get("input_tokens"))
                + _int(usage.get("prompt_tokens"))
                + _int(usage.get("promptTokenCount"))
            )
            row["output_tokens"] += (
                _int(usage.get("output_tokens"))
                + _int(usage.get("completion_tokens"))
                + _int(usage.get("candidatesTokenCount"))
            )
            if not row["limits"]:
                row["limits"] = event.payload.get("limits") or {}
            if row["last_used_at"] is None:
                row["last_used_at"] = event.created_at
        elif event.type == "handover" and row["stopped_reason"] is None:
            row["stopped_reason"] = event.payload.get("reason") or event.summary

    return [
        schemas.AgentUsageOut(
            agent=connector.name,
            model=connector.model,
            is_active=connector.is_configured,
            unavailable_reason=connector.missing_config,
            **totals.get(
                connector.name,
                {
                    "turns": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "limits": {},
                    "last_used_at": None,
                    "stopped_reason": None,
                },
            ),
        )
        for connector in registry.all()
    ]
