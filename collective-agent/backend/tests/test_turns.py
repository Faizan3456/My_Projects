"""The continuity guarantees: memory survives agents, and limits hand over."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

import httpx
import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.connectors.base import AgentConnector, AgentReply, Prompt
from app.connectors.registry import ConnectorRegistry, get_registry, set_registry
from app.errors import AgentCallError, AgentLimitError


class ScriptedConnector(AgentConnector):
    """A connector that returns queued replies and records the prompts it saw."""

    provider = "test"

    def __init__(self, settings: Settings, name: str, replies: list[str]) -> None:
        super().__init__(settings)
        self.name = name
        self._replies = list(replies)
        self.prompts: list[Prompt] = []

    @property
    def model(self) -> str:
        return f"{self.name}-test"

    async def complete(self, prompt: Prompt) -> AgentReply:  # skip http client
        self.prompts.append(prompt)
        reply = self._replies.pop(0)
        if reply == "__LIMIT__":
            raise AgentLimitError("Monthly quota exhausted", agent=self.name)
        if reply == "__FAIL__":
            raise AgentCallError("Upstream returned 500", agent=self.name)
        return AgentReply(text=reply, model=self.model, usage={"input_tokens": 10})

    async def _complete(self, client, prompt):  # pragma: no cover - unused
        raise NotImplementedError


def structured(summary: str, task: str, next_step: str, status="active") -> str:
    block = {
        "summary": summary,
        "current_task": task,
        "next_step": next_step,
        "status": status,
    }
    return f"Here is the work.\n\n```json\n{json.dumps(block)}\n```"


@pytest.fixture
def scripted(app):
    """Install scripted connectors in place of the real registry."""
    settings = get_settings()
    registry = ConnectorRegistry(settings)
    connectors: dict[str, ScriptedConnector] = {}

    def install(name: str, replies: list[str]) -> ScriptedConnector:
        connector = ScriptedConnector(settings, name, replies)
        registry.register(connector)
        connectors[name] = connector
        return connector

    app.dependency_overrides[get_registry] = lambda: registry
    yield install, connectors
    app.dependency_overrides.clear()


async def test_turn_writes_the_reply_into_memory(
    client: AsyncClient, project: dict, scripted
):
    install, _ = scripted
    install(
        "claude",
        [structured("Wrote the SQLAlchemy models", "Data model", "Add the API")],
    )

    response = await client.post(
        f"/projects/{project['id']}/turns",
        json={"agent_name": "claude", "message": "Start on the data model"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "completed"
    assert body["summary"] == "Wrote the SQLAlchemy models"
    assert body["context"]["current_task"] == "Data model"
    assert body["context"]["next_step"] == "Add the API"
    assert body["context"]["last_agent_used"] == "claude"
    assert body["event"]["payload"]["structured"] is True

    events = (await client.get(f"/projects/{project['id']}/events")).json()
    assert [e["type"] for e in events[:2]] == ["agent_reply", "user_message"]


async def test_unstructured_reply_still_updates_memory(
    client: AsyncClient, project: dict, scripted
):
    install, _ = scripted
    install("claude", ["I refactored the loader. " * 40])

    body = (
        await client.post(
            f"/projects/{project['id']}/turns", json={"agent_name": "claude"}
        )
    ).json()

    assert body["status"] == "completed"
    assert body["event"]["payload"]["structured"] is False
    assert body["summary"].startswith("I refactored the loader.")
    assert len(body["summary"]) <= get_settings().summary_max_chars + 1
    # No structured next_step was offered, so the stored one is preserved.
    assert body["context"]["next_step"] == "Draft the data model"


async def test_second_agent_sees_the_first_agent_s_work(
    client: AsyncClient, project: dict, scripted
):
    install, connectors = scripted
    install("claude", [structured("Built the schema", "Schema", "Write the router")])
    install("gemini", [structured("Wrote the router", "Router", "Write tests")])
    pid = project["id"]

    await client.post(f"/projects/{pid}/turns", json={"agent_name": "claude"})
    await client.post(f"/projects/{pid}/turns", json={"agent_name": "gemini"})

    briefing = connectors["gemini"].prompts[0].user
    assert "Current task: Schema" in briefing
    assert "Next step:    Write the router" in briefing
    assert "Last agent:   claude" in briefing
    assert "Built the schema" in briefing  # history carried across providers

    context = (await client.get(f"/projects/{pid}/context")).json()
    assert context["current_task"] == "Router"
    assert context["last_agent_used"] == "gemini"


async def test_limit_creates_a_handover_instead_of_losing_work(
    client: AsyncClient, project: dict, scripted
):
    """The manual protocol, with automatic failover switched off.

    With failover on (the default) the work would move to the next agent inside
    the same request — covered by test_a_limit_hands_the_work_on_automatically.
    Here the operator chooses who continues, and the snapshot is what makes that
    possible.
    """
    install, connectors = scripted
    install(
        "chatgpt",
        [structured("Drafted the models", "Models", "Add the events table"),
         "__LIMIT__"],
    )
    install("claude", [structured("Added events table", "Events", "Wire the API")])
    pid = project["id"]

    with failover(AUTO_FAILOVER="false"):
        await client.post(f"/projects/{pid}/turns", json={"agent_name": "chatgpt"})
        limited = await client.post(
            f"/projects/{pid}/turns", json={"agent_name": "chatgpt"}
        )

        # A limit is a routing outcome, not an API error.
        assert limited.status_code == 200
        body = limited.json()
        assert body["status"] == "handover_required"
        assert body["reply"] is None
        assert body["handover"]["from_agent"] == "chatgpt"
        assert "quota" in body["handover"]["reason"].lower()
        assert body["handover"]["last_action"] == "chatgpt: Drafted the models"
        assert body["handover"]["suggested_next_step"] == "Add the events table"
        assert body["context"]["status"] == "handover_required"

        # The next agent is briefed as a takeover and clears the alert.
        resumed = await client.post(
            f"/projects/{pid}/turns", json={"agent_name": "claude"}
        )
        assert resumed.json()["status"] == "completed"

    takeover_prompt = connectors["claude"].prompts[0].user
    assert "taking over from chatgpt" in takeover_prompt
    assert "Add the events table" in takeover_prompt

    open_handovers = (
        await client.get(f"/projects/{pid}/handovers?unresolved_only=true")
    ).json()
    assert open_handovers == []


async def test_agent_failure_is_recorded_and_reported(
    client: AsyncClient, project: dict, scripted
):
    install, _ = scripted
    install("claude", ["__FAIL__"])
    pid = project["id"]

    response = await client.post(f"/projects/{pid}/turns", json={"agent_name": "claude"})
    assert response.status_code == 502
    assert response.json()["error"] == "agent_call_failed"

    # The failure is in the timeline, so the next agent can see it happened.
    events = (await client.get(f"/projects/{pid}/events")).json()
    assert events[0]["type"] == "error"
    assert events[0]["agent_name"] == "claude"

    # A transport failure is not a limit: no handover, project still active.
    assert (await client.get(f"/projects/{pid}/handovers")).json() == []
    context = (await client.get(f"/projects/{pid}/context")).json()
    assert context["status"] == "active"


async def test_unknown_agent_is_rejected(client: AsyncClient, project: dict):
    response = await client.post(
        f"/projects/{project['id']}/turns", json={"agent_name": "skynet"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "unknown_agent"


async def test_unconfigured_agent_reports_what_is_missing(
    client: AsyncClient, project: dict
):
    response = await client.post(
        f"/projects/{project['id']}/turns", json={"agent_name": "claude"}
    )
    assert response.status_code == 424
    assert "ANTHROPIC_API_KEY" in response.json()["message"]


async def test_echo_connector_runs_the_loop_offline(
    client: AsyncClient, project: dict
):
    response = await client.post(
        f"/projects/{project['id']}/turns",
        json={"agent_name": "echo", "message": "say hello"},
    )
    assert response.status_code == 200
    assert response.json()["context"]["last_agent_used"] == "echo"


async def test_echo_connector_can_simulate_a_limit(
    client: AsyncClient, project: dict
):
    response = await client.post(
        f"/projects/{project['id']}/turns",
        json={"agent_name": "echo", "message": "SIMULATE_LIMIT"},
    )
    assert response.json()["status"] == "handover_required"


async def test_a_resumed_turn_is_not_re_triggered_by_history(
    client: AsyncClient, project: dict
):
    """The briefing quotes past turns; that must not re-fire the past turn.

    A connector deciding anything from the prompt has to read the instruction
    for this turn, not the recorded history around it.
    """
    pid = project["id"]
    limited = await client.post(
        f"/projects/{pid}/turns",
        json={"agent_name": "echo", "message": "SIMULATE_LIMIT"},
    )
    assert limited.json()["status"] == "handover_required"

    resumed = await client.post(f"/projects/{pid}/turns", json={"agent_name": "echo"})
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["context"]["status"] == "active"


# --- provider wire formats --------------------------------------------------


async def test_claude_connector_maps_the_messages_api(monkeypatch):
    from app.connectors.claude import ClaudeConnector

    settings = get_settings().model_copy(update={"anthropic_api_key": "sk-test"})
    connector = ClaudeConnector(settings)
    seen: dict = {}

    async def fake_post(self, url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs["json"]
        seen["headers"] = kwargs["headers"]
        return httpx.Response(
            200,
            json={
                "model": settings.anthropic_model,
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 5},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    reply = await connector.complete(Prompt(system="sys", user="hi"))

    assert reply.text == "done"
    assert seen["url"].endswith("/v1/messages")
    assert seen["json"]["system"] == "sys"  # system is top-level, not a message
    assert seen["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert seen["headers"]["x-api-key"] == "sk-test"


async def test_claude_reads_text_after_a_thinking_block(monkeypatch):
    """Reasoning models put `thinking` before `text`; content[0] is not the reply.

    This shipped broken and failed on the first real Opus call in production.
    """
    from app.connectors.claude import ClaudeConnector

    settings = get_settings().model_copy(update={"anthropic_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-5",
                "content": [
                    {"type": "thinking", "thinking": "considering the schema"},
                    {"type": "text", "text": "Use accounts and postings."},
                    {"type": "text", "text": "Add a journal table too."},
                ],
                "usage": {"input_tokens": 12},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    reply = await ClaudeConnector(settings).complete(Prompt(system="s", user="u"))
    # Every text block, in order, and nothing from the thinking block.
    assert reply.text == "Use accounts and postings.\nAdd a journal table too."
    assert "considering" not in reply.text


async def test_claude_with_no_text_block_reports_why(monkeypatch):
    from app.connectors.claude import ClaudeConnector

    settings = get_settings().model_copy(update={"anthropic_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "search"}],
                "stop_reason": "tool_use",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentCallError) as caught:
        await ClaudeConnector(settings).complete(Prompt(system="s", user="u"))
    assert caught.value.details["block_types"] == "tool_use"
    assert caught.value.details["stop_reason"] == "tool_use"


async def test_gemini_reads_text_after_a_thought_part(monkeypatch):
    from app.connectors.gemini import GeminiConnector

    settings = get_settings().model_copy(update={"google_api_key": "key"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True},
                                {"text": "Two tables: accounts, postings."},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    reply = await GeminiConnector(settings).complete(Prompt(system="s", user="u"))
    assert reply.text == "Two tables: accounts, postings."


async def test_gemini_blocked_response_reports_the_reason(monkeypatch):
    from app.connectors.gemini import GeminiConnector

    settings = get_settings().model_copy(update={"google_api_key": "key"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200, json={"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentCallError) as caught:
        await GeminiConnector(settings).complete(Prompt(system="s", user="u"))
    assert caught.value.details["block_reason"] == "SAFETY"


class _StubConnector(AgentConnector):
    """A connector whose behaviour is dictated per test."""

    def __init__(self, name, settings, *, reply=None, error=None):
        super().__init__(settings)
        self.name = name
        self.provider = "stub"
        self._reply = reply
        self._error = error
        self.calls = 0
        self.last_prompt: Prompt | None = None

    @property
    def model(self):
        return f"{self.name}-1"

    @property
    def missing_config(self):
        return None

    async def _complete(self, client, prompt):
        self.calls += 1
        self.last_prompt = prompt
        if self._error:
            raise self._error
        return AgentReply(text=self._reply, model=self.model)


def _pool(settings, **behaviours):
    """A registry containing only the given stub agents."""
    registry = ConnectorRegistry(settings)
    registry._connectors = {}
    for name, spec in behaviours.items():
        registry.register(_StubConnector(name, settings, **spec))
    return registry


@contextmanager
def failover(**env):
    """Set failover configuration for one test.

    It has to go through the environment: `run_turn` resolves its own settings
    via get_settings(), so handing a Settings object to the registry alone does
    not change how the orchestrator behaves.
    """
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update({key: str(value) for key, value in env.items()})
    get_settings.cache_clear()
    try:
        yield get_settings()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

async def test_a_limit_hands_the_work_on_automatically(client, project):
    """The point of the collective: nobody has to pick the next agent."""
    with failover(AUTO_FAILOVER="true", FAILOVER_ORDER="second,third") as settings:
        registry = _pool(
            settings,
            first={"error": AgentLimitError("first is out of quota", agent="first")},
            second={"error": AgentLimitError("second is out of quota", agent="second")},
            third={"reply": 'Done it.\n\n```json\n{"summary": "finished"}\n```'},
        )
        set_registry(registry)
        try:
            response = await client.post(
                f"/projects/{project['id']}/turns",
                json={"agent_name": "first", "message": "do the thing"},
            )
        finally:
            set_registry(None)

    assert response.status_code == 200
    body = response.json()
    # Asked for `first`, answered by `third`, with no second request needed.
    assert body["status"] == "completed"
    assert body["agent_name"] == "third"
    assert body["summary"] == "finished"
    assert registry.get("first").calls == 1
    assert registry.get("second").calls == 1
    assert registry.get("third").calls == 1

    # Both failures are on the record, and neither is left hanging open.
    events = (await client.get(f"/projects/{project['id']}/events")).json()
    handovers = [e for e in events if e["type"] == "handover"]
    assert {h["agent_name"] for h in handovers} == {"first", "second"}
    still_open = (
        await client.get(f"/projects/{project['id']}/handovers?unresolved_only=true")
    ).json()
    assert still_open == []
    context = (await client.get(f"/projects/{project['id']}/context")).json()
    assert context["status"] == "active"


async def test_failover_keeps_the_question_that_was_asked(client, project):
    """Shipped broken: the takeover briefing replaced the user's question, so the
    second agent answered the briefing instead of the person."""
    with failover(AUTO_FAILOVER="true", FAILOVER_ORDER="second") as settings:
        registry = _pool(
            settings,
            first={"error": AgentLimitError("first is out", agent="first")},
            second={"reply": "144"},
        )
        set_registry(registry)
        try:
            await client.post(
                f"/projects/{project['id']}/turns",
                json={
                    "agent_name": "first",
                    "message": "What is 12 times 12? Just the number.",
                },
            )
        finally:
            set_registry(None)

    briefing = registry.get("second").last_prompt.user
    assert "12 times 12" in briefing
    assert "taking over from first" in briefing
    # And it is posed as the outstanding question, not buried in history.
    assert "has not been answered" in briefing


async def test_failover_stops_when_everyone_is_out(client, project):
    with failover(AUTO_FAILOVER="true", FAILOVER_ORDER="second") as settings:
        registry = _pool(
            settings,
            first={"error": AgentLimitError("first is out", agent="first")},
            second={"error": AgentLimitError("second is out", agent="second")},
        )
        set_registry(registry)
        try:
            response = await client.post(
                f"/projects/{project['id']}/turns",
                json={"agent_name": "first", "message": "go"},
            )
        finally:
            set_registry(None)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "handover_required"
    assert body["handover"]["from_agent"] == "second"
    # The alert stands, because the work genuinely did not get done.
    assert body["context"]["status"] == "handover_required"


async def test_failover_is_bounded(client, project):
    """One turn must not be able to burn every provider's quota."""

    def out(name):
        return {"error": AgentLimitError(f"{name} is out", agent=name)}

    with failover(
        AUTO_FAILOVER="true", MAX_FAILOVER_HOPS="1", FAILOVER_ORDER="b,c,d"
    ) as settings:
        registry = _pool(settings, a=out("a"), b=out("b"), c=out("c"), d=out("d"))
        set_registry(registry)
        try:
            await client.post(
                f"/projects/{project['id']}/turns",
                json={"agent_name": "a", "message": "go"},
            )
        finally:
            set_registry(None)

    # The requested agent plus one hop, and no further.
    assert registry.get("a").calls == 1
    assert registry.get("b").calls == 1
    assert registry.get("c").calls == 0
    assert registry.get("d").calls == 0


async def test_echo_is_never_chosen_as_a_fallback(client, project):
    """Echo answers without a model; it must not silently end the chain."""
    with failover(AUTO_FAILOVER="true", FAILOVER_ORDER="echo,real") as settings:
        registry = _pool(
            settings,
            first={"error": AgentLimitError("first is out", agent="first")},
            echo={"reply": "offline nonsense"},
            real={"reply": "Actual answer."},
        )
        set_registry(registry)
        try:
            response = await client.post(
                f"/projects/{project['id']}/turns",
                json={"agent_name": "first", "message": "go"},
            )
        finally:
            set_registry(None)

    assert response.json()["agent_name"] == "real"
    assert registry.get("echo").calls == 0


async def test_failover_can_be_switched_off(client, project):
    with failover(AUTO_FAILOVER="false") as settings:
        registry = _pool(
            settings,
            first={"error": AgentLimitError("first is out", agent="first")},
            second={"reply": "I could have helped."},
        )
        set_registry(registry)
        try:
            response = await client.post(
                f"/projects/{project['id']}/turns",
                json={"agent_name": "first", "message": "go"},
            )
        finally:
            set_registry(None)

    assert response.json()["status"] == "handover_required"
    assert registry.get("second").calls == 0


async def test_a_limit_error_repeats_the_providers_own_reason(monkeypatch):
    """"HTTP 429" is not actionable; "insufficient_quota: ..." is."""
    from app.connectors.chatgpt import ChatGPTConnector

    settings = get_settings().model_copy(update={"openai_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "insufficient_quota",
                    "message": "You exceeded your current quota, please check "
                    "your plan and billing details.",
                }
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentLimitError) as caught:
        await ChatGPTConnector(settings).complete(Prompt(system="s", user="u"))
    assert "insufficient_quota" in caught.value.message
    assert "check your plan and billing" in caught.value.message


async def test_a_non_json_error_body_still_reads_sensibly(monkeypatch):
    from app.connectors.chatgpt import ChatGPTConnector

    settings = get_settings().model_copy(update={"openai_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(502, text="<html>\n  Bad gateway\n</html>")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentCallError) as caught:
        await ChatGPTConnector(settings).complete(Prompt(system="s", user="u"))
    # Collapsed to one line rather than dumped raw with its newlines.
    assert "<html> Bad gateway </html>" in caught.value.message


async def test_429_becomes_a_limit_error(monkeypatch):
    from app.connectors.chatgpt import ChatGPTConnector

    settings = get_settings().model_copy(update={"openai_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(429, text="Rate limit reached for gpt-4o")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentLimitError):
        await ChatGPTConnector(settings).complete(Prompt(system="s", user="u"))


async def test_context_overflow_becomes_a_limit_error(monkeypatch):
    from app.connectors.gemini import GeminiConnector

    settings = get_settings().model_copy(update={"google_api_key": "key"})

    async def fake_post(self, url, **kwargs):
        # Providers report this as a 400, but it still means "hand over".
        return httpx.Response(
            400, text='{"error":{"message":"maximum context length exceeded"}}'
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentLimitError):
        await GeminiConnector(settings).complete(Prompt(system="s", user="u"))


async def test_server_error_is_not_a_limit_error(monkeypatch):
    from app.connectors.chatgpt import ChatGPTConnector

    settings = get_settings().model_copy(update={"openai_api_key": "sk-test"})

    async def fake_post(self, url, **kwargs):
        return httpx.Response(500, text="internal server error")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(AgentCallError):
        await ChatGPTConnector(settings).complete(Prompt(system="s", user="u"))
