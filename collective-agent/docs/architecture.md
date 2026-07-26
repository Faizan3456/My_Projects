# Collective AI Agent System

## Unified Multi-Agent Memory and Seamless Cross-Platform Continuity

Technical architecture specification and implementation record

Version 1.0 — 25 July 2026

---

## 1. Introduction

This document describes the architecture of the Collective AI Agent System, a
service that lets one person work across several AI agents (Claude, ChatGPT,
Copilot, Gemini, local models) against a single shared memory and a single
project state, with seamless continuity when switching between agents.

The system holds four guarantees:

- Every agent reads the same context, so none of them needs to be re-briefed.
- Work continues when one agent hits a limit; a handover snapshot records
  exactly where to resume.
- Progress is never lost, because the memory service — not the agent's chat
  window — is where state lives.
- The intelligence about *the project* lives in shared memory. The agents are
  interchangeable, stateless tools.

This is an implementation record as well as a design: every endpoint, table and
behaviour described here exists in the accompanying codebase and is covered by
its test suite.

## 2. System overview

The system consists of five parts:

1. A **dashboard** for the operator: pick a project, see its state and history,
   pick an agent, respond to handover alerts.
2. A **shared memory service** — the brain — that owns project context, the
   append-only event log, and the handover protocol.
3. A **PostgreSQL database** providing durable memory.
4. **Agent connectors**, one per provider, translating a single internal prompt
   into each provider's wire format.
5. **External AI agents**, treated as stateless tools with no memory of their
   own.

The critical design rule: nothing except the orchestrator may call a connector.
Every agent call therefore leaves a record in shared memory, which is what makes
any later agent able to take over.

## 3. Model topology

### Dashboard (Next.js 15, React 19, TypeScript)

Displays the current project, current task, next step, last agent used, the
history timeline, the agent selection panel and handover alerts. Talks to the
memory service over REST only; it holds no state the service does not have.

### Shared memory service (FastAPI, Python 3.12)

Stores and retrieves context, logs events, runs turns, and writes handovers.
Async throughout (SQLAlchemy 2.0 + asyncpg), one database transaction per
request.

### Database (PostgreSQL 16)

Five tables: `projects`, `contexts`, `events`, `agents`, `handovers`. The
`contexts` row is the live state; `events` is append-only history.

### Agent connectors

One class per provider, all implementing the same contract: take a `Prompt`,
return an `AgentReply`, and translate provider errors into either
"this agent hit a limit" or "this agent failed".

| Connector | Provider | Endpoint | Credential |
|---|---|---|---|
| `claude` | Anthropic | `/v1/messages` | `ANTHROPIC_API_KEY` |
| `chatgpt` | OpenAI | `/v1/chat/completions` | `OPENAI_API_KEY` |
| `copilot` | GitHub Models | `/chat/completions` | `GITHUB_TOKEN` |
| `gemini` | Google | `:generateContent` | `GOOGLE_API_KEY` |
| `local` | Ollama / vLLM / LM Studio | `/v1/chat/completions` | none |
| `echo` | offline | none | none |

An agent with no credential reports itself inactive and says which variable is
missing, rather than failing at call time. The `echo` connector is an offline
implementation used for demos and tests: it exercises the entire memory and
handover loop without a single API key.

## 4. Architecture diagram

```
              +--------------------------------------+
              |                 User                 |
              |        Browser / Terminal / CLI      |
              +------------------+-------------------+
                                 |
                                 v
              +--------------------------------------+
              |           Dashboard (Next.js)        |
              |  projects | context | timeline | UI  |
              +------------------+-------------------+
                                 | REST / JSON
                                 v
              +--------------------------------------+
              |     Shared Memory Service (FastAPI)  |
              |   /projects  /context  /events       |
              |   /turns     /handover  /agents      |
              |                                      |
              |   Orchestrator: the only caller of   |
              |   any connector                      |
              +------------------+-------------------+
                                 |
                                 v
              +--------------------------------------+
              |          PostgreSQL 16               |
              |  projects | contexts | events        |
              |  agents   | handovers                |
              +------------------+-------------------+
                                 |
                                 v
    +----------------------------------------------------------+
    |                    Agent Connectors                      |
    |  claude | chatgpt | copilot | gemini | local | echo      |
    |                                                          |
    |  fetch context -> build prompt -> call agent ->          |
    |  summarise -> update memory -> log event                 |
    +---------------------------+------------------------------+
                                |
                                v
    +----------------------------------------------------------+
    |                  External AI Agents                      |
    |   Claude | ChatGPT | Copilot | Gemini | Local LLMs        |
    +----------------------------------------------------------+
```

## 5. System flowchart

```
        +-------------------------+
        |  User starts/continues  |
        +------------+------------+
                     |
                     v
        +-------------------------+
        |  Dashboard: select      |
        |  project and agent      |
        +------------+------------+
                     |
                     v
        +-------------------------+
        |  GET /context           |
        |  GET /events            |
        |  GET /handovers?open    |
        +------------+------------+
                     |
                     v
        +-------------------------+
        |  POST /projects/{id}/   |
        |  turns {agent, message} |
        +------------+------------+
                     |
                     v
        +-------------------------+
        |  Orchestrator builds    |
        |  the briefing prompt    |
        |  (takeover variant if   |
        |   a handover is open)   |
        +------------+------------+
                     |
                     v
        +-------------------------+
        |  Connector calls the    |
        |  external agent         |
        +------+-----------+------+
               |           |
      limit    |           |  reply
      reached  |           |
               v           v
    +---------------+   +--------------------------+
    | Write         |   | Parse reply -> summary,  |
    | handover      |   | current_task, next_step, |
    | snapshot      |   | status                   |
    | + event       |   +-------------+------------+
    | status =      |                 |
    | handover_     |                 v
    | required      |   +--------------------------+
    +-------+-------+   | Update context           |
            |           | Append agent_reply event |
            |           | Resolve open handover    |
            |           +-------------+------------+
            |                         |
            v                         v
    +---------------+     +--------------------------+
    | Dashboard     |     | Dashboard refresh:       |
    | raises a      |     | new task, next step,     |
    | handover      |     | timeline entry           |
    | alert with    |     +--------------------------+
    | alternative   |
    | agents        |
    +---------------+
```

## 6. Behaviour description

1. The user selects a project. The dashboard loads context, history and any open
   handover.
2. The user selects an agent. Only agents with credentials are selectable; the
   rest show the missing variable.
3. The user sends an instruction, or sends nothing — an empty message means
   "carry out the stored next step".
4. The orchestrator fetches the context and the last N events (default 12) and
   builds one briefing containing: project name and description, current task,
   next step, status, last agent used, durable memory facts, recent history, and
   the instruction for this turn.
5. If a handover is open and a *different* agent is now being used, the
   orchestrator builds the takeover variant instead: it names the agent that
   stopped, why it stopped, its last action, and the point to resume from.
6. The connector calls the agent. The reply is parsed into a memory update.
7. Context is updated, an `agent_reply` event is appended, and any open handover
   is marked resolved.
8. If the agent reports a limit, a handover snapshot is written instead, the
   context status becomes `handover_required`, and the API returns HTTP 200 with
   `status: "handover_required"` — a limit is a routing outcome, not an error.
9. The dashboard raises an alert offering the other configured agents. Choosing
   one runs the next turn from the snapshot, and the work continues.

## 7. Data model

### projects

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `name` | varchar(200) | unique |
| `description` | text | nullable |
| `created_at` | timestamptz | default `now()` |

### contexts — the live state, one row per project

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `project_id` | uuid | unique, FK -> projects, cascade delete |
| `current_task` | text | what is in progress |
| `next_step` | text | the single next action |
| `status` | varchar(32) | `active`, `blocked`, `handover_required`, `done` |
| `last_agent_used` | varchar(64) | nullable |
| `memory` | jsonb | durable facts every agent is told |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | touched on every write |

A `CHECK` constraint enforces the status vocabulary in the database, not only in
the application.

### events — append-only history

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `project_id` | uuid | FK -> projects, cascade delete |
| `agent_name` | varchar(64) | null for user and system entries |
| `type` | varchar(32) | `note`, `user_message`, `agent_reply`, `context_update`, `handover`, `error` |
| `summary` | text | short, human-readable; this is what later prompts quote |
| `payload` | jsonb | full reply, token usage, model id, error code |
| `created_at` | timestamptz | indexed with `project_id` |

Events are never updated and never deleted. The `summary` field is what makes
history cheap to replay into a prompt: agents are given summaries, not
transcripts.

### agents — catalogue mirror

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `name` | varchar(64) | unique, e.g. `claude` |
| `provider` | varchar(64) | e.g. `anthropic` |
| `model` | varchar(128) | resolved model id |
| `is_active` | boolean | whether a credential is present |
| `created_at` | timestamptz | |

The connector registry is the source of truth; this table is refreshed at
startup and on every `GET /agents`, so reports can join against it.

### handovers — snapshots

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `project_id` | uuid | FK -> projects, cascade delete |
| `from_agent` | varchar(64) | the agent that stopped |
| `to_agent` | varchar(64) | the agent that picked up, when known |
| `reason` | text | why it stopped |
| `last_action` | text | the last thing that happened before stopping |
| `suggested_next_step` | text | where to resume |
| `context_snapshot` | jsonb | full copy of the context at handover time |
| `resolved_at` | timestamptz | null while the alert is open |
| `created_at` | timestamptz | |

The snapshot is a copy, not a reference, so it stays truthful after the live
context moves on. A partial index over unresolved rows serves the dashboard
alert query.

## 8. API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness, version, and which agents are active |
| `GET` | `/projects` | List projects, newest first |
| `POST` | `/projects` | Create a project and its initial context |
| `GET` | `/projects/{id}` | Project with its context |
| `DELETE` | `/projects/{id}` | Delete a project and everything under it |
| `GET` | `/projects/{id}/context` | Current context |
| `POST` | `/projects/{id}/context` | Partial context update; `memory` merges by default, `?replace_memory=true` overwrites |
| `GET` | `/projects/{id}/events` | History, newest first, paginated |
| `POST` | `/projects/{id}/events` | Append an event |
| `POST` | `/projects/{id}/turns` | Run one agent turn against shared memory |
| `GET` | `/projects/{id}/handovers` | Handovers, optionally only unresolved |
| `POST` | `/handover` | Record a handover explicitly |
| `GET` | `/handover/{id}` | One handover snapshot |
| `POST` | `/handover/{id}/resolve` | Mark accepted by an agent and reactivate |
| `GET` | `/agents` | Agent catalogue with active state and reasons |

Errors are returned as `{"error": code, "message": text, "details": {...}}`.
Codes: `not_found` (404), `conflict` (409), `unknown_agent` (400),
`agent_not_configured` (424), `agent_call_failed` (502),
`agent_limit_reached` (503, only when a limit is raised outside a turn).

OpenAPI documentation is served at `/docs`.

## 9. Agent connector logic

Every turn runs the same seven steps, in `app/services/orchestrator.py`:

1. **Fetch context** and the most recent events from shared memory.
2. **Build the prompt** — briefing plus this turn's instruction. If a handover
   is open and the agent differs from the one that stopped, build the takeover
   variant.
3. **Call the agent** through its connector.
4. **Summarise** the reply into a memory update.
5. **Update the context**: current task, next step, status, last agent used.
6. **Append an event** carrying the summary, the full reply, the model id and
   token usage.
7. **Resolve any open handover**, because the work has demonstrably continued.

### The reply contract

Agents are asked to end every reply with a fenced JSON block:

```json
{
  "summary": "one or two sentences on what you just did",
  "current_task": "the task now in progress",
  "next_step": "the single next action for whoever works on this next",
  "status": "active | blocked | done"
}
```

Real models sometimes ignore the format, so parsing degrades in three steps:
fenced JSON, then a trailing bare JSON object, then a sentence-boundary summary
of the prose with code blocks stripped. Memory is never left unwritten because a
model forgot the contract. When several JSON blocks are present the last one
wins, so an example quoted mid-reply cannot hijack the update.

### Limit detection

A limit is recognised from HTTP 429 and 529, or from provider error text
matching known markers (rate limit, quota, overloaded, context length, usage
limit, billing hard limit). This matters because providers report a context
overflow as HTTP 400: the status code alone is not enough to tell "hand over"
from "this call was malformed".

Anything else — 500s, timeouts, unreachable hosts — is a call failure, not a
limit. It is written to the timeline as an `error` event and committed before the
error propagates, so a failure the operator sees in the UI is also a failure the
next agent can read about.

### Prompt hygiene

The `Prompt` object carries the instruction for the current turn separately from
the briefing text that surrounds it. Connector logic that inspects the request
must read the instruction, never the briefing: the briefing quotes past turns,
and matching against it re-fires old instructions on every later turn. This was a
real defect found during end-to-end testing, and it is covered by a regression
test.

## 10. Handover protocol

A handover is the moment one agent stops and another must pick up. It writes
three things in a single transaction:

1. A **snapshot row** in `handovers`: reason, last action, suggested next step,
   and a full copy of the context.
2. A **`handover` event**, so the timeline shows the break.
3. A **context update** setting `status = handover_required` and pointing
   `next_step` at the suggested resume point. A handover with no forward
   instruction is useless, so an empty suggestion falls back to the stored next
   step.

Handovers are created automatically when a connector reports a limit, and can be
created explicitly via `POST /handover` — which is how a client reports a limit
it detected itself, for example a user hitting a plan cap inside a provider's own
chat UI.

A handover is discharged either implicitly, when any agent completes a turn on
the project, or explicitly via `POST /handover/{id}/resolve`, which also returns
the project to `active`.

## 11. Dashboard behaviour

The dashboard shows, at all times:

- the project list, with the selected project highlighted;
- current task, next step, status badge, last agent used, and durable memory;
- the history timeline, newest first, with full agent replies collapsed behind a
  disclosure;
- the agent panel: every connector, its model, and whether it is ready or which
  variable it is missing;
- handover alerts, naming the agent that stopped, the reason, the last action,
  the resume point, and one button per alternative agent.

Context fields are editable in place, so the operator can correct the memory the
agents read. The view polls the service every ten seconds — another operator, or
another agent, may be writing to the same project — and pauses polling while a
turn is in flight. Light and dark themes both ship.

## 12. Deviations from the original specification

The original specification was followed except where implementation demanded
more; each addition is listed here.

| Addition | Why |
|---|---|
| `handovers` table | The specification put handover data in an event summary. A snapshot needs structured, queryable fields and a copy of the context, and the dashboard needs to query open handovers cheaply. The `handover` event is still written. |
| `POST /projects/{id}/turns` | The specification described the connector loop but gave it no endpoint. Without one, each client would reimplement the loop and could skip the memory write. |
| `POST /handover/{id}/resolve` | A handover that can be created but never closed leaves a permanent alert. |
| `contexts.memory` (jsonb) | Durable facts (repository, stack, conventions) do not belong in a task field and should not have to be re-derived from history each turn. |
| `echo` connector | Makes the whole system demonstrable and testable with no API keys and no network. |
| `agents` reported from the registry | The specification's `agents` table would drift from reality. Configuration is now the source of truth and the table mirrors it. |
| Copilot via GitHub Models | Copilot's IDE completion API is not publicly callable. GitHub Models serves the same model family over the OpenAI wire format with a `GITHUB_TOKEN`, and the base URL can be pointed at any OpenAI-compatible gateway instead. |

## 13. Identity and deployment

The system is deployed at `agents.openedgetechnologies.com`. The apex domain and
`www` are untouched: they continue to serve the existing Hostinger site, and this
service occupies a subdomain on a VPS.

### Topology in production

```
internet -> Caddy (:80/:443, automatic TLS)
              |-- /api/*  -> backend  (FastAPI, internal only)
              +-- /*      -> frontend (Next.js, internal only)
                                |
                              db (PostgreSQL, internal only, named volume)
```

Only Caddy publishes a port. The API and the database are reachable solely on the
internal container network, and the dashboard calls the API on its own origin
under `/api`, so no cross-origin request is ever made.

### Authentication

Two mechanisms, selected by `AUTH_MODE`:

- **`entra`** — Microsoft Entra ID. The dashboard is a SPA registered in the
  OpenEdge Technologies directory; it signs the user in with the authorization
  code flow and PKCE, then sends the resulting access token for
  `api://<client-id>/access_as_user` as a bearer token. The API fetches the
  tenant's JWKS, caches it, and verifies signature, issuer, audience, expiry and
  the `tid` claim. A token bearing a valid signature from another tenant is
  rejected explicitly, because the issuer URL alone is not proof of tenancy.
  `ENTRA_ALLOWED_USERS` can narrow access to named accounts.
- **`token`** — a shared secret in `X-Service-Token`, compared in constant time,
  for scripts and scheduled jobs. It carries no identity, so it is recorded as a
  service principal.

There is no client secret anywhere in the system: a public client using PKCE has
nothing to store, so there is nothing to rotate or leak.

`/healthz` is deliberately unauthenticated so a probe can reach it. Every other
route requires a principal, and each turn records the actor beside the agent, so
history answers both "which agent did this" and "who asked for it".

### The guardrail

The application refuses to start when `ENVIRONMENT=production` and
`AUTH_MODE=disabled`. This is not defensive decoration: the turn endpoint spends
real money on provider APIs, and a misordered environment variable is exactly the
kind of mistake that would otherwise ship silently.

### What is deployed by whom

The Entra app registration, the auth layer, the production images, the reverse
proxy configuration and the deploy scripts are all in place and were exercised
locally end to end. Two steps require credentials that live outside this system:
the DNS `A` record for `agents.` at Namecheap, and SSH access to the VPS. Both
are documented in `deploy/README.md`.

## 14. Running locally

### With Docker

```
cp .env.example .env      # optional: add provider keys
docker compose up --build
```

Dashboard on `http://localhost:3000`, API on `http://localhost:8000`, OpenAPI
docs on `http://localhost:8000/docs`.

### Without Docker

```
make setup                # venv, python deps, npm install, .env
docker compose up -d db   # or point DATABASE_URL at any PostgreSQL
make backend              # http://localhost:8000
make frontend             # http://localhost:3000
```

`make test` runs the backend suite. `make demo` drives a project through a turn,
a simulated limit, a handover and a resume, with no keys configured.

The database schema is applied automatically by `docker compose` on first boot
from `backend/db/schema.sql`; that file can also be applied by hand with `psql`.
For local development without it, `DB_AUTO_CREATE=true` lets the service create
the tables from the ORM models at startup.

## 15. Verification

The backend suite covers, with no network access:

- project, context and event CRUD, including memory merge versus replace, status
  vocabulary rejection, and cascade delete;
- the full turn loop with scripted connectors, asserting that a second agent's
  briefing contains the first agent's task, next step and history;
- limit handling: a limit produces a handover with the right last action and
  resume point, returns HTTP 200, and the next agent receives the takeover
  briefing and clears the alert;
- failure handling: a 500 is not treated as a limit, is recorded as an `error`
  event, and leaves the project active;
- provider wire formats: Anthropic's top-level `system` parameter, HTTP 429 as a
  limit, a context-overflow 400 as a limit, and a 500 as a call failure;
- reply parsing: fenced JSON, bare trailing JSON, last-block-wins, invalid
  status rejection, malformed JSON falling back to prose, code-block stripping,
  and sentence-boundary truncation;
- prompt construction: briefing contents, instruction isolation, empty-state
  rendering, and the takeover variant.

Beyond the suite, the system was run end to end against PostgreSQL 16 with the
hand-written `schema.sql` as the only migration: a project was created, a turn
run, a limit forced, a handover raised in the dashboard, and a second agent —
a different connector — resumed the work from the snapshot and cleared the
alert.
