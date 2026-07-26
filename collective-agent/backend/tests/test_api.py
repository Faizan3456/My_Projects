from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_health_lists_active_agents(client: AsyncClient):
    body = (await client.get("/healthz")).json()
    assert body["status"] == "ok"
    # Only the offline connector is configured in the test environment.
    assert body["active_agents"] == ["echo"]


async def test_agents_report_why_they_are_inactive(client: AsyncClient):
    agents = {a["name"]: a for a in (await client.get("/agents")).json()}
    assert set(agents) == {
        "chatgpt",
        "claude",
        "copilot",
        "echo",
        "gemini",
        "groq",
        "local",
        "openrouter",
    }
    assert agents["echo"]["is_active"] is True
    assert agents["claude"]["is_active"] is False
    assert "ANTHROPIC_API_KEY" in agents["claude"]["reason"]
    # The free-tier providers name their own variable too, so the dashboard can
    # tell the operator exactly what to set.
    assert "GROQ_API_KEY" in agents["groq"]["reason"]
    assert "OPENROUTER_API_KEY" in agents["openrouter"]["reason"]


async def test_clearing_one_chat_leaves_the_others(client: AsyncClient):
    keep = (await client.post("/projects", json={"name": "keep"})).json()
    drop = (await client.post("/projects", json={"name": "drop"})).json()

    assert (await client.delete(f"/projects/{drop['id']}")).status_code == 204

    remaining = [p["id"] for p in (await client.get("/projects")).json()]
    assert remaining == [keep["id"]]
    # Its history went with it.
    assert (await client.get(f"/projects/{drop['id']}/events")).status_code == 404


async def test_clearing_all_chats_empties_everything(client: AsyncClient):
    for name in ("one", "two", "three"):
        await client.post("/projects", json={"name": name})

    assert (await client.delete("/projects")).status_code == 204
    assert (await client.get("/projects")).json() == []


async def test_clearing_all_chats_on_an_empty_system_is_fine(client: AsyncClient):
    assert (await client.delete("/projects")).status_code == 204
    assert (await client.delete("/projects")).status_code == 204


async def test_project_starts_with_a_context(client: AsyncClient, project: dict):
    assert project["context"]["current_task"] == "Write the first module"
    assert project["context"]["status"] == "active"

    listed = (await client.get("/projects")).json()
    assert [p["id"] for p in listed] == [project["id"]]


async def test_duplicate_project_name_conflicts(client: AsyncClient, project: dict):
    response = await client.post("/projects", json={"name": project["name"]})
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


async def test_unknown_project_is_404(client: AsyncClient):
    response = await client.get(f"/projects/{uuid.uuid4()}/context")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


async def test_context_update_merges_memory_and_logs_an_event(
    client: AsyncClient, project: dict
):
    pid = project["id"]
    first = await client.post(
        f"/projects/{pid}/context",
        json={"next_step": "Review the schema", "memory": {"repo": "acme/api"}},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/projects/{pid}/context", json={"memory": {"branch": "main"}}
    )
    assert second.json()["memory"] == {"repo": "acme/api", "branch": "main"}
    assert second.json()["next_step"] == "Review the schema"

    replaced = await client.post(
        f"/projects/{pid}/context?replace_memory=true",
        json={"memory": {"only": "this"}},
    )
    assert replaced.json()["memory"] == {"only": "this"}

    types = [e["type"] for e in (await client.get(f"/projects/{pid}/events")).json()]
    assert types.count("context_update") == 3


async def test_invalid_status_is_rejected(client: AsyncClient, project: dict):
    response = await client.post(
        f"/projects/{project['id']}/context", json={"status": "napping"}
    )
    assert response.status_code == 422


async def test_events_are_newest_first(client: AsyncClient, project: dict):
    pid = project["id"]
    for n in range(3):
        await client.post(
            f"/projects/{pid}/events",
            json={"type": "note", "summary": f"note {n}", "agent_name": "claude"},
        )
    events = (await client.get(f"/projects/{pid}/events?limit=3")).json()
    assert [e["summary"] for e in events] == ["note 2", "note 1", "note 0"]


async def test_project_delete_cascades(client: AsyncClient, project: dict):
    pid = project["id"]
    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    assert (await client.get(f"/projects/{pid}")).status_code == 404
    assert (await client.get(f"/projects/{pid}/events")).status_code == 404
