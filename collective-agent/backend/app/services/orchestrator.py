"""The turn loop: the one place agents and shared memory meet.

    fetch context -> build prompt -> call agent -> summarise -> update memory
    -> add event -> (on limit) create handover

Nothing else in the system talks to a connector, so every agent call is
guaranteed to be recorded in shared memory.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, repositories as repo, schemas
from ..config import Settings, get_settings
from ..connectors import build_handover_prompt, build_prompt
from ..connectors.registry import ConnectorRegistry, get_registry
from ..errors import AgentCallError, AgentLimitError
from . import handover as handover_service
from .reply_parser import parse_reply

log = logging.getLogger(__name__)


@dataclass(slots=True)
class TurnResult:
    status: str  # "completed" | "handover_required"
    agent_name: str
    context: models.Context
    reply: str | None = None
    summary: str | None = None
    event: models.Event | None = None
    handover: models.Handover | None = None


async def run_turn(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: schemas.TurnRequest,
    *,
    registry: ConnectorRegistry | None = None,
    settings: Settings | None = None,
    actor: str = "",
) -> TurnResult:
    settings = settings or get_settings()
    registry = registry or get_registry()
    connector = registry.get(request.agent_name)
    agent = connector.name

    # 1. Fetch context and history from shared memory.
    project = await repo.get_project(session, project_id)
    context = await repo.get_context(session, project_id)
    history = await repo.list_events(
        session, project_id, limit=settings.prompt_history_limit
    )
    history.reverse()  # prompts read better oldest-first

    if request.message.strip():
        await repo.add_event(
            session,
            project_id,
            type="user_message",
            summary=request.message.strip()[: settings.summary_max_chars],
            payload={"agent_name": agent, "actor": actor},
        )

    # 2. Build the prompt. A different agent arriving after a handover gets the
    #    takeover briefing instead of the standard one.
    pending = await handover_service.open_handover(session, project_id)
    taking_over = pending is not None and pending.from_agent != agent
    if taking_over and not request.message.strip():
        prompt = build_handover_prompt(project, context, history, pending)
    else:
        prompt = build_prompt(project, context, history, request.message)

    # 3. Call the agent, falling through the pool as limits are hit.
    #
    # This is what makes it a collective rather than a switchboard: hitting a
    # quota is an expected condition, so the work moves to the next agent
    # automatically and the reason is recorded on the way past. Bounded by
    # max_failover_hops so one turn cannot burn every provider's quota.
    attempts = _failover_chain(registry, agent, settings)
    reply = None
    last_handover: models.Handover | None = None

    for position, candidate in enumerate(attempts):
        connector = registry.get(candidate)
        agent = connector.name

        if position > 0:
            # The taking-over agent is briefed on why the previous one stopped —
            # and still receives the question that was actually asked.
            prompt = build_handover_prompt(
                project, context, history, last_handover, request.message
            )

        try:
            reply = await connector.complete(prompt)
            break
        except AgentLimitError as exc:
            log.warning("agent %s hit a limit on project %s", agent, project_id)
            last_handover, context = await handover_service.create_handover(
                session,
                project_id=project_id,
                from_agent=agent,
                reason=exc.message,
                last_action=_last_action(history),
                suggested_next_step=context.next_step,
            )
            continue
        except AgentCallError as exc:
            await repo.add_event(
                session,
                project_id,
                type="error",
                agent_name=agent,
                summary=exc.message,
                payload={"code": exc.code},
            )
            # A broken credential is not a limit, so it does not consume a
            # failover hop's worth of goodwill — but the chain continues, since
            # the point is to get the work done by someone.
            if position + 1 < len(attempts):
                continue
            # Commit before re-raising: the request handler rolls back on the way
            # out, and a failure the user never sees in the timeline is a failure
            # the next agent cannot learn from.
            await session.commit()
            raise

    if reply is None:
        # Everyone available was tried and none could continue.
        await session.commit()
        return TurnResult(
            status="handover_required",
            agent_name=agent,
            context=context,
            handover=last_handover,
        )

    # 4-7. Fold the reply into shared memory.
    return await record_reply(
        session,
        project_id,
        agent=agent,
        text=reply.text,
        model=reply.model,
        usage=reply.usage,
        limits=reply.limits,
        settings=settings,
    )


async def record_reply(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    agent: str,
    text: str,
    model: str | None = None,
    usage: dict | None = None,
    limits: dict | None = None,
    transport: str = "api",
    settings: Settings | None = None,
) -> TurnResult:
    """Fold an agent's reply into shared memory.

    Shared by the API path and the manual bridge, so a reply pasted in from a
    chat window updates context, history and handovers exactly as an API reply
    does. Two code paths writing memory differently is how the two transports
    would drift apart.
    """
    settings = settings or get_settings()

    # Summarise into a memory update.
    parsed = parse_reply(text, summary_max_chars=settings.summary_max_chars)

    context = await repo.update_context(
        session,
        project_id,
        schemas.ContextUpdate(
            current_task=parsed.current_task,
            next_step=parsed.next_step,
            status=parsed.status or "active",
            last_agent_used=agent,
        ),
    )

    event = await repo.add_event(
        session,
        project_id,
        type="agent_reply",
        agent_name=agent,
        summary=parsed.summary,
        payload={
            "model": model,
            "usage": usage or {},
            "limits": limits or {},
            "structured": parsed.structured,
            "transport": transport,
            "reply": text,
        },
    )

    # The work continued, so every open handover is discharged — not just the
    # newest. One turn can pass through several agents, and leaving the earlier
    # ones open made the dashboard claim a handover was still needed after the
    # work had already moved on.
    for stale in await repo.list_handovers(
        session, project_id, unresolved_only=True, limit=50
    ):
        await handover_service.resolve_handover(
            session, stale, to_agent=agent, reactivate=False
        )

    return TurnResult(
        status="completed",
        agent_name=agent,
        context=context,
        reply=text,
        summary=parsed.summary,
        event=event,
    )


def _failover_chain(
    registry: ConnectorRegistry, requested: str, settings: Settings
) -> list[str]:
    """The agent asked for, then whoever else could take over.

    `echo` never appears as a fallback: it replies without calling a model, so it
    would end the chain with a reply that looks like an answer but is not one.
    """
    chain = [requested]
    if not settings.auto_failover:
        return chain

    configured = [c.name for c in registry.active()]
    preferred = [name for name in settings.failover_sequence if name in configured]
    remaining = [name for name in configured if name not in preferred]

    for name in preferred + remaining:
        if len(chain) > settings.max_failover_hops:
            break
        if name == requested or name == "echo":
            continue
        chain.append(name)
    return chain


def _last_action(history: list[models.Event]) -> str:
    for event in reversed(history):
        if event.type in ("agent_reply", "user_message"):
            return f"{event.agent_name or 'user'}: {event.summary}"
    return ""
