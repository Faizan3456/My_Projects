# Collective AI Agent System

One shared memory and one project state across many AI agents. Work with Claude,
ChatGPT, Copilot, Gemini or a local model against the same context — and when one
hits a limit, another picks up exactly where it stopped.

The intelligence about *the project* lives in the memory service. The agents are
interchangeable, stateless tools.

```
Dashboard (Next.js)  ->  Shared Memory Service (FastAPI)  ->  PostgreSQL
                              |
                              +->  Connectors: claude · chatgpt · copilot
                                   gemini · local · echo
```

Full specification: [docs/architecture.md](docs/architecture.md) ·
[docs/architecture.pdf](docs/architecture.pdf) · Deployment runbook:
[deploy/README.md](deploy/README.md)

Deployment target: **agents.openedgetechnologies.com**, behind Microsoft Entra ID
sign-in restricted to the OpenEdge Technologies directory.

---

## Quickstart

### Docker

```bash
cp .env.example .env && docker compose up --build
```

### Without Docker

```bash
make setup                # venv + python deps + npm install + .env
docker compose up -d db   # or point DATABASE_URL at any PostgreSQL 14+
make backend              # http://localhost:8000  (docs at /docs)
make frontend             # http://localhost:3000
```

**No API keys are needed to try it.** The offline `echo` agent exercises the
entire loop — turns, memory writes, limits, handovers, resumes:

```bash
make demo
```

Add keys to `.env` to turn real agents on. Each one becomes selectable in the
dashboard the moment its variable is set; until then it is listed as inactive
with the name of the variable it wants.

| Agent | Variable | Notes |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | Anthropic Messages API |
| `chatgpt` | `OPENAI_API_KEY` | OpenAI chat completions |
| `copilot` | `GITHUB_TOKEN` | via GitHub Models; `COPILOT_BASE_URL` can point at any OpenAI-compatible gateway |
| `gemini` | `GOOGLE_API_KEY` | Google generateContent |
| `local` | `LOCAL_LLM_BASE_URL` | Ollama (`http://localhost:11434/v1`), vLLM, LM Studio |
| `echo` | — | offline; send `SIMULATE_LIMIT` to force a handover |

## How a turn works

`POST /projects/{id}/turns {"agent_name": "claude", "message": ""}`

1. Fetch the context and recent events from shared memory.
2. Build one briefing: project, current task, next step, status, last agent,
   durable memory, recent history, and this turn's instruction. An empty message
   means "carry out the stored next step".
3. Call the agent through its connector.
4. Parse the reply — agents are asked to end with a fenced JSON block giving
   `summary`, `current_task`, `next_step`, `status`; prose is summarised if they
   don't.
5. Update the context, append an `agent_reply` event, resolve any open handover.

If the agent reports a limit, the service writes a handover snapshot instead and
returns **HTTP 200** with `status: "handover_required"` — a limit is a routing
outcome, not an error. The dashboard then offers the other configured agents, and
the next one gets a takeover briefing naming what stopped, why, and where to
resume.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Version and which agents are active |
| `GET` `POST` | `/projects` | List / create projects |
| `GET` `DELETE` | `/projects/{id}` | Project with context / delete everything under it |
| `GET` `POST` | `/projects/{id}/context` | Read / patch the live state (`memory` merges; `?replace_memory=true` overwrites) |
| `GET` `POST` | `/projects/{id}/events` | Append-only history |
| `POST` | `/projects/{id}/turns` | Run one agent turn |
| `GET` | `/projects/{id}/handovers` | Handovers, `?unresolved_only=true` for open ones |
| `POST` | `/handover` | Record a handover explicitly (e.g. a limit you hit in a provider's own UI) |
| `GET` `POST` | `/handover/{id}` · `/handover/{id}/resolve` | Read / accept a snapshot |
| `GET` | `/agents` | Catalogue with active state and missing-variable reasons |

Errors: `{"error": code, "message": text, "details": {}}` with
`not_found` 404, `conflict` 409, `unknown_agent` 400,
`agent_not_configured` 424, `agent_call_failed` 502.

## Layout

```
backend/
  app/
    main.py            app factory, lifespan, health
    config.py          settings; COLLECTIVE_IGNORE_ENV_FILE=1 for hermetic runs
    models.py          SQLAlchemy models (portable types: runs on sqlite in tests)
    schemas.py         request/response contracts
    repositories.py    every read/write of persistent memory
    routers/           projects · turns · handover · agents
    connectors/        base · prompt · claude · chatgpt · copilot · gemini
                       local · echo · registry
    services/          orchestrator (the turn loop) · handover · reply_parser
  db/schema.sql        PostgreSQL DDL, applied by docker-compose on first boot
  scripts/demo.py      drives the full loop against a running API
  tests/               40 tests, no network access
frontend/
  app/                 dashboard page + components
  lib/api.ts           typed client
docs/
  architecture.md      the specification
  build_pdf.py         renders it to architecture.pdf
```

## Tests

```bash
make test
```

40 tests, no network and no PostgreSQL required (in-memory SQLite). They cover
CRUD and cascade behaviour, the turn loop with scripted connectors, cross-agent
continuity, limit-versus-failure classification, each provider's wire format,
reply parsing degradation, and prompt construction.

## Authentication

Local development runs open (`AUTH_MODE=disabled`). Deployments run one of:

- **`entra`** — the dashboard signs in against the OpenEdge Technologies tenant
  and sends the access token as `Authorization: Bearer <jwt>`. The API verifies it
  against the tenant's published signing keys and checks issuer, audience, expiry
  and `tid`; nothing is trusted from unverified claims. Optionally restricted
  further with `ENTRA_ALLOWED_USERS`.
- **`token`** — a shared secret in `X-Service-Token`, for scripts and cron.

`/healthz` stays open for load-balancer probes. Everything else requires a
principal, and `POST /projects/{id}/turns` records who asked alongside which agent
answered.

The app refuses to boot with `ENVIRONMENT=production` and `AUTH_MODE=disabled`,
because an open turn endpoint spends real money on provider API calls.

Scripts authenticate with the service token:

```bash
SERVICE_TOKEN=... python backend/scripts/demo.py https://agents.openedgetechnologies.com/api
```

## Notes and limitations

- **`DB_AUTO_CREATE=true`** creates tables from the ORM at startup, which is
  convenient locally. Production sets it false and relies on
  `backend/db/schema.sql`; there is no migration tool wired up yet, so schema
  changes need Alembic before the second release.
- **No rate limiting.** A signed-in account can spend the provider budget as fast
  as the agents will answer.
- **The dashboard polls every 10 seconds.** Fine for one operator; a websocket or
  SSE channel would be the next step for a team watching one project.
- **History is summarised, not paginated into prompts.** Each turn sees the last
  `PROMPT_HISTORY_LIMIT` event summaries (default 12). Long projects will need
  either a rolling summary or retrieval; the event log has everything required to
  add that later.
- **Copilot** has no public completion API, so the connector targets GitHub
  Models. See the note in `app/connectors/copilot.py`.
