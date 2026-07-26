"""The manual bridge: your own logged-in chat windows, in the same collective.

Consumer subscriptions (ChatGPT Plus, Claude Pro, Copilot) cannot be called
programmatically, and automating their web UIs breaks their terms. So the person
is the transport: this builds the same shared-memory briefing an API agent would
receive, you paste it into whichever chat you are signed in to, and paste the
answer back.

The reply is recorded through exactly the same path as an API reply — same
context update, same history, same handover discharge — so a manual agent is a
full member of the collective rather than a note stapled to the side.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repositories as repo, schemas
from ..auth import Principal, require_principal
from ..config import Settings, get_settings
from ..connectors.prompt import build_handover_prompt, build_prompt
from ..connectors.registry import ConnectorRegistry, get_registry
from ..db import get_session
from ..services import handover as handover_service
from ..services.orchestrator import record_reply

router = APIRouter(prefix="/projects/{project_id}/manual", tags=["manual"])

# Where to go to paste the briefing. These are the normal chat interfaces, not
# API consoles — the point is to use the subscription you already pay for.
CHAT_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "copilot": "https://github.com/copilot",
    "gemini": "https://gemini.google.com/app",
    "groq": "https://groq.com/",
    "openrouter": "https://openrouter.ai/chat",
    "local": "http://localhost:11434",
    "echo": "",
}


@router.post("/prompt", response_model=schemas.ManualPromptOut)
async def manual_prompt(
    project_id: uuid.UUID,
    data: schemas.ManualPromptRequest,
    session: AsyncSession = Depends(get_session),
    registry: ConnectorRegistry = Depends(get_registry),
    settings: Settings = Depends(get_settings),
):
    """The briefing to paste into a chat window. Writes nothing.

    Deliberately read-only: a briefing that is copied but never answered must not
    leave a half-finished turn in the history.
    """
    agent = registry.get(data.agent_name).name
    project = await repo.get_project(session, project_id)
    context = await repo.get_context(session, project_id)
    history = await repo.list_events(
        session, project_id, limit=settings.prompt_history_limit
    )
    history.reverse()

    pending = await handover_service.open_handover(session, project_id)
    if pending is not None and pending.from_agent != agent:
        prompt = build_handover_prompt(
            project, context, history, pending, data.message
        )
    else:
        prompt = build_prompt(project, context, history, data.message)

    return schemas.ManualPromptOut(
        agent_name=agent,
        chat_url=CHAT_URLS.get(agent, ""),
        # One block to copy: the system framing matters as much as the briefing,
        # and a chat window has nowhere separate to put it.
        text=f"{prompt.system}\n\n---\n\n{prompt.user}",
    )


@router.post("/reply", response_model=schemas.TurnResponse)
async def manual_reply(
    project_id: uuid.UUID,
    data: schemas.ManualReplyRequest,
    session: AsyncSession = Depends(get_session),
    registry: ConnectorRegistry = Depends(get_registry),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_principal),
):
    """Record what the chat window answered, as that agent's turn."""
    agent = registry.get(data.agent_name).name
    await repo.get_project(session, project_id)

    if data.message.strip():
        await repo.add_event(
            session,
            project_id,
            type="user_message",
            summary=data.message.strip()[: settings.summary_max_chars],
            payload={
                "agent_name": agent,
                "actor": principal.label,
                "transport": "manual",
            },
        )

    result = await record_reply(
        session,
        project_id,
        agent=agent,
        text=data.reply,
        model=data.model or None,
        transport="manual",
        settings=settings,
    )
    return schemas.TurnResponse(
        status="completed",
        agent_name=result.agent_name,
        reply=result.reply,
        summary=result.summary,
        context=result.context,
        event=result.event,
        handover=None,
    )
