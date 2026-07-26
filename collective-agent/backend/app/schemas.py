"""Request / response contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ContextStatus = Literal["active", "blocked", "handover_required", "done"]
EventType = Literal[
    "note", "user_message", "agent_reply", "context_update", "handover", "error"
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- projects ---------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    current_task: str = ""
    next_step: str = ""


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class ProjectDetailOut(ProjectOut):
    context: "ContextOut | None" = None


# --- contexts ---------------------------------------------------------------


class ContextUpdate(BaseModel):
    """Partial update. Omitted fields keep their stored value."""

    current_task: str | None = None
    next_step: str | None = None
    status: ContextStatus | None = None
    last_agent_used: str | None = None
    memory: dict[str, Any] | None = None


class ContextOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    current_task: str
    next_step: str
    status: ContextStatus
    last_agent_used: str | None
    memory: dict[str, Any]
    updated_at: datetime


# --- events -----------------------------------------------------------------


class EventCreate(BaseModel):
    type: EventType = "note"
    summary: str = Field(min_length=1)
    agent_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    agent_name: str | None
    type: EventType
    summary: str
    payload: dict[str, Any]
    created_at: datetime


# --- agents -----------------------------------------------------------------


class AgentUsageOut(BaseModel):
    """What an agent has spent here, and what the provider says remains."""

    agent: str
    model: str | None
    is_active: bool
    unavailable_reason: str | None = None
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Rate-limit headers from the provider's most recent response. Empty for
    # providers that publish none (Gemini) or that have not been called yet.
    limits: dict[str, Any] = Field(default_factory=dict)
    last_used_at: datetime | None = None
    # Why this agent last stopped, if it did — usually a rate or quota limit.
    stopped_reason: str | None = None


class AgentOut(BaseModel):
    name: str
    provider: str
    model: str | None = None
    is_active: bool
    reason: str | None = Field(
        default=None, description="Why the agent is inactive, if it is."
    )


# --- handover ---------------------------------------------------------------


class HandoverCreate(BaseModel):
    project_id: uuid.UUID
    from_agent: str
    reason: str = Field(min_length=1)
    last_action: str = ""
    suggested_next_step: str = ""
    to_agent: str | None = None


class HandoverOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    from_agent: str
    to_agent: str | None
    reason: str
    last_action: str
    suggested_next_step: str
    context_snapshot: dict[str, Any]
    resolved_at: datetime | None
    created_at: datetime


class HandoverResolve(BaseModel):
    to_agent: str = Field(min_length=1)


# --- turns ------------------------------------------------------------------


class TurnRequest(BaseModel):
    agent_name: str = Field(min_length=1)
    message: str = Field(
        default="",
        description="Optional user instruction for this turn. Empty means "
        "'continue from the stored next step'.",
    )


class ManualPromptRequest(BaseModel):
    agent_name: str = Field(min_length=1)
    message: str = ""


class ManualPromptOut(BaseModel):
    agent_name: str
    # The chat interface to paste into, not an API console.
    chat_url: str
    text: str


class ManualReplyRequest(BaseModel):
    agent_name: str = Field(min_length=1)
    # What was asked, so the transcript reads as a conversation.
    message: str = ""
    reply: str = Field(min_length=1, description="Pasted from the chat window")
    model: str = ""


class TurnResponse(BaseModel):
    status: Literal["completed", "handover_required"]
    agent_name: str
    reply: str | None = None
    summary: str | None = None
    context: ContextOut
    event: EventOut | None = None
    handover: HandoverOut | None = None


ProjectDetailOut.model_rebuild()
