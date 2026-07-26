"""The manual bridge is a transport, not a second system.

A reply pasted from a chat window must land in shared memory exactly as an API
reply does, so an agent used manually is a full member of the collective.
"""

from __future__ import annotations

import json

from httpx import AsyncClient


def structured(summary: str, task: str, next_step: str) -> str:
    block = {"summary": summary, "current_task": task, "next_step": next_step}
    return f"Here is the work.\n\n```json\n{json.dumps(block)}\n```"


async def test_prompt_carries_the_shared_memory_briefing(
    client: AsyncClient, project: dict
):
    response = await client.post(
        f"/projects/{project['id']}/manual/prompt",
        json={"agent_name": "chatgpt", "message": "Draft the schema"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["agent_name"] == "chatgpt"
    assert body["chat_url"] == "https://chatgpt.com/"
    # The same briefing an API agent would get: task, next step, and the ask.
    assert "Current task: Write the first module" in body["text"]
    assert "Next step:    Draft the data model" in body["text"]
    assert "Draft the schema" in body["text"]
    # Including the framing that makes the reply parseable back into memory.
    assert '"next_step"' in body["text"]


async def test_prompt_writes_nothing(client: AsyncClient, project: dict):
    """A briefing copied but never answered must leave no trace."""
    before = (await client.get(f"/projects/{project['id']}/events")).json()
    await client.post(
        f"/projects/{project['id']}/manual/prompt",
        json={"agent_name": "claude", "message": "hello"},
    )
    after = (await client.get(f"/projects/{project['id']}/events")).json()
    assert len(after) == len(before)


async def test_a_pasted_reply_updates_memory_like_any_other(
    client: AsyncClient, project: dict
):
    pid = project["id"]
    response = await client.post(
        f"/projects/{pid}/manual/reply",
        json={
            "agent_name": "chatgpt",
            "message": "Draft the schema",
            "reply": structured("Drafted the schema", "Schema", "Write the DDL"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "completed"
    assert body["agent_name"] == "chatgpt"
    assert body["summary"] == "Drafted the schema"
    assert body["context"]["current_task"] == "Schema"
    assert body["context"]["next_step"] == "Write the DDL"
    assert body["context"]["last_agent_used"] == "chatgpt"

    events = (await client.get(f"/projects/{pid}/events")).json()
    assert [e["type"] for e in events[:2]] == ["agent_reply", "user_message"]
    assert events[0]["payload"]["transport"] == "manual"


async def test_a_manual_agent_can_take_over_from_an_api_agent(
    client: AsyncClient, project: dict
):
    """The whole point: your ChatGPT subscription continues Claude's work."""
    pid = project["id"]
    await client.post(
        "/handover",
        json={
            "project_id": pid,
            "from_agent": "claude",
            "reason": "Monthly usage limit reached",
            "suggested_next_step": "Write the DDL for the accounts table",
        },
    )

    # The briefing offered to the manual agent is a takeover briefing.
    prompt = (
        await client.post(
            f"/projects/{pid}/manual/prompt", json={"agent_name": "chatgpt"}
        )
    ).json()
    assert "taking over from claude" in prompt["text"]
    assert "Write the DDL for the accounts table" in prompt["text"]

    # Pasting the answer back clears the alert, as an API turn would.
    await client.post(
        f"/projects/{pid}/manual/reply",
        json={
            "agent_name": "chatgpt",
            "reply": structured("Wrote the DDL", "DDL", "Add the indexes"),
        },
    )
    still_open = (
        await client.get(f"/projects/{pid}/handovers?unresolved_only=true")
    ).json()
    assert still_open == []
    context = (await client.get(f"/projects/{pid}/context")).json()
    assert context["status"] == "active"
    assert context["last_agent_used"] == "chatgpt"


async def test_manual_works_for_an_agent_with_no_api_key(
    client: AsyncClient, project: dict
):
    """No key is needed: the subscription is being used, not the API."""
    agents = {a["name"]: a for a in (await client.get("/agents")).json()}
    assert agents["gemini"]["is_active"] is False  # no key configured in tests

    response = await client.post(
        f"/projects/{project['id']}/manual/reply",
        json={"agent_name": "gemini", "reply": "Two plus two is four."},
    )
    assert response.status_code == 200
    assert response.json()["agent_name"] == "gemini"


async def test_an_unknown_agent_is_rejected(client: AsyncClient, project: dict):
    response = await client.post(
        f"/projects/{project['id']}/manual/reply",
        json={"agent_name": "not-an-agent", "reply": "hello"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "unknown_agent"
