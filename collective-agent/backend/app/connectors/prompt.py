"""Prompt construction — where shared memory becomes agent input.

Every agent receives the same briefing, which is what makes them
interchangeable: current task, next step, durable memory, recent history, and
the reply format the orchestrator parses back into memory.
"""

from __future__ import annotations

import json
from typing import Iterable

from .. import models
from .base import Prompt

SYSTEM_TEMPLATE = """\
You are one of several interchangeable AI agents working on a shared project.
You have no memory of your own. Everything you know about this project is in the
briefing below, which comes from a shared memory service. Other agents have
worked on this project before you and may continue after you.

Rules:
1. Continue the work from the stated next step. Do not restart from scratch.
2. Do not ask the user to repeat context that is already in the briefing.
3. Be concrete. Produce the actual work (code, text, analysis), not a plan to
   plan.
4. If you cannot finish, say exactly where you stopped so the next agent can
   resume.
5. End every reply with a fenced json block, and nothing after it:

```json
{{
  "summary": "one or two sentences on what you just did",
  "current_task": "the task now in progress",
  "next_step": "the single next action for whoever works on this next",
  "status": "active | blocked | done"
}}
```

Project: {project_name}
{project_description}\
"""

BRIEFING_TEMPLATE = """\
=== SHARED MEMORY BRIEFING ===
Current task: {current_task}
Next step:    {next_step}
Status:       {status}
Last agent:   {last_agent}

Durable project memory:
{memory}

Recent history (oldest first):
{history}
=== END BRIEFING ===

{instruction}\
"""

CONTINUE_INSTRUCTION = (
    "No new instruction was given. Carry out the next step above."
)


def _format_memory(memory: dict[str, object]) -> str:
    if not memory:
        return "  (none recorded)"
    return "\n".join(
        f"  - {key}: {json.dumps(value, default=str)}"
        for key, value in sorted(memory.items())
    )


def _format_history(events: Iterable[models.Event]) -> str:
    lines = [
        f"  [{event.created_at:%Y-%m-%d %H:%M}] "
        f"{event.agent_name or 'user'} / {event.type}: {event.summary}"
        for event in events
    ]
    return "\n".join(lines) if lines else "  (no prior activity)"


def build_prompt(
    project: models.Project,
    context: models.Context,
    history: list[models.Event],
    user_message: str = "",
) -> Prompt:
    """Assemble the briefing. `history` is expected oldest-first."""
    system = SYSTEM_TEMPLATE.format(
        project_name=project.name,
        project_description=project.description or "(no description)",
    )
    instruction = user_message.strip() or CONTINUE_INSTRUCTION
    user = BRIEFING_TEMPLATE.format(
        current_task=context.current_task or "(not set yet)",
        next_step=context.next_step or "(not set yet)",
        status=context.status,
        last_agent=context.last_agent_used or "(none yet)",
        memory=_format_memory(context.memory),
        history=_format_history(history),
        instruction=instruction,
    )
    return Prompt(system=system, user=user, instruction=instruction)


def build_handover_prompt(
    project: models.Project,
    context: models.Context,
    history: list[models.Event],
    handover: models.Handover,
    user_message: str = "",
) -> Prompt:
    """Prompt for the agent picking up after another agent stopped.

    When the person asked something in this same turn, that question stays the
    instruction and the handover is only context. Replacing it with the takeover
    text loses the actual request — the agent then answers the briefing instead
    of the person.
    """
    takeover = (
        f"You are taking over from {handover.from_agent}, which stopped "
        f"because: {handover.reason}\n"
        f"Its last action was: {handover.last_action or '(not recorded)'}\n"
    )
    if user_message.strip():
        instruction = (
            f"{takeover}\n"
            f"Answer this, which is what was asked and has not been answered "
            f"yet:\n\n{user_message.strip()}"
        )
    else:
        instruction = (
            f"{takeover}"
            f"It suggested this next step: "
            f"{handover.suggested_next_step or context.next_step or '(none)'}\n\n"
            "Resume from exactly that point. Do not redo completed work."
        )
    return build_prompt(project, context, history, instruction)
