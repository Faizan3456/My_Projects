from __future__ import annotations

from httpx import AsyncClient


async def test_manual_handover_flags_the_project(client: AsyncClient, project: dict):
    pid = project["id"]
    response = await client.post(
        "/handover",
        json={
            "project_id": pid,
            "from_agent": "chatgpt",
            "reason": "Weekly message cap reached",
            "last_action": "Wrote the migration for the contexts table",
            "suggested_next_step": "Add the events index",
        },
    )
    assert response.status_code == 201, response.text
    handover = response.json()
    # The snapshot preserves the context as it was, not as it becomes.
    assert handover["context_snapshot"]["next_step"] == "Draft the data model"
    assert handover["context_snapshot"]["status"] == "active"

    context = (await client.get(f"/projects/{pid}/context")).json()
    assert context["status"] == "handover_required"
    assert context["next_step"] == "Add the events index"
    assert context["last_agent_used"] == "chatgpt"

    events = (await client.get(f"/projects/{pid}/events")).json()
    assert events[0]["type"] == "handover"
    assert "Weekly message cap" in events[0]["summary"]

    open_ones = (
        await client.get(f"/projects/{pid}/handovers?unresolved_only=true")
    ).json()
    assert [h["id"] for h in open_ones] == [handover["id"]]


async def test_handover_without_a_suggestion_falls_back_to_next_step(
    client: AsyncClient, project: dict
):
    response = await client.post(
        "/handover",
        json={
            "project_id": project["id"],
            "from_agent": "gemini",
            "reason": "Context window exhausted",
        },
    )
    assert response.json()["suggested_next_step"] == "Draft the data model"


async def test_resolving_a_handover_reactivates_the_project(
    client: AsyncClient, project: dict
):
    pid = project["id"]
    handover = (
        await client.post(
            "/handover",
            json={
                "project_id": pid,
                "from_agent": "claude",
                "reason": "Rate limited",
            },
        )
    ).json()

    resolved = await client.post(
        f"/handover/{handover['id']}/resolve", json={"to_agent": "gemini"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["to_agent"] == "gemini"
    assert resolved.json()["resolved_at"] is not None

    context = (await client.get(f"/projects/{pid}/context")).json()
    assert context["status"] == "active"

    still_open = (
        await client.get(f"/projects/{pid}/handovers?unresolved_only=true")
    ).json()
    assert still_open == []
