"""What every agent is told — the reason they are interchangeable."""

from __future__ import annotations

from datetime import datetime, timezone

from app import models
from app.connectors.prompt import (
    CONTINUE_INSTRUCTION,
    build_handover_prompt,
    build_prompt,
)


def make_fixtures():
    project = models.Project(name="Ledger", description="Double-entry ledger")
    context = models.Context(
        current_task="Schema design",
        next_step="Add the postings table",
        status="active",
        last_agent_used="chatgpt",
        memory={"repo": "acme/ledger", "stack": ["python", "postgres"]},
    )
    events = [
        models.Event(
            type="agent_reply",
            agent_name="chatgpt",
            summary="Created the accounts table",
            created_at=datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
            payload={},
        )
    ]
    return project, context, events


def test_briefing_carries_the_whole_shared_state():
    project, context, events = make_fixtures()
    prompt = build_prompt(project, context, events, "Write the migration")

    assert "Ledger" in prompt.system
    assert "Double-entry ledger" in prompt.system
    # The reply contract the orchestrator parses must be in the system prompt.
    assert '"next_step"' in prompt.system

    assert "Current task: Schema design" in prompt.user
    assert "Next step:    Add the postings table" in prompt.user
    assert "Last agent:   chatgpt" in prompt.user
    assert '- repo: "acme/ledger"' in prompt.user
    assert "Created the accounts table" in prompt.user
    assert prompt.user.rstrip().endswith("Write the migration")


def test_instruction_is_available_apart_from_the_briefing():
    project, context, events = make_fixtures()
    prompt = build_prompt(project, context, events, "Write the migration")
    assert prompt.instruction == "Write the migration"
    assert "Current task" not in prompt.instruction


def test_an_empty_message_becomes_continue_from_the_next_step():
    project, context, events = make_fixtures()
    prompt = build_prompt(project, context, events, "   ")
    assert prompt.instruction == CONTINUE_INSTRUCTION
    assert CONTINUE_INSTRUCTION in prompt.user


def test_empty_memory_and_history_read_cleanly():
    project = models.Project(name="Fresh", description=None)
    context = models.Context(current_task="", next_step="", status="active", memory={})
    prompt = build_prompt(project, context, [])
    assert "(no description)" in prompt.system
    assert "(none recorded)" in prompt.user
    assert "(no prior activity)" in prompt.user
    assert "Current task: (not set yet)" in prompt.user


def test_takeover_prompt_names_the_previous_agent_and_where_to_resume():
    project, context, events = make_fixtures()
    handover = models.Handover(
        from_agent="chatgpt",
        reason="Weekly cap reached",
        last_action="Created the accounts table",
        suggested_next_step="Add the postings table",
    )
    prompt = build_handover_prompt(project, context, events, handover)

    assert "taking over from chatgpt" in prompt.user
    assert "Weekly cap reached" in prompt.user
    assert "Add the postings table" in prompt.user
    assert "Do not redo completed work." in prompt.user
