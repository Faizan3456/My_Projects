-- Collective AI Agent System — PostgreSQL schema.
-- Mirrors backend/app/models.py. Applied automatically by docker-compose
-- (mounted into the postgres init directory); apply by hand with:
--   psql "$DATABASE_URL" -f backend/db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One live state row per project: "where are we, what is next".
CREATE TABLE IF NOT EXISTS contexts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL UNIQUE
                    REFERENCES projects(id) ON DELETE CASCADE,
    current_task    TEXT NOT NULL DEFAULT '',
    next_step       TEXT NOT NULL DEFAULT '',
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    last_agent_used VARCHAR(64),
    memory          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_contexts_status CHECK (
        status IN ('active', 'blocked', 'handover_required', 'done')
    )
);

-- Append-only history. Never updated, never deleted.
CREATE TABLE IF NOT EXISTS events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name VARCHAR(64),
    type       VARCHAR(32) NOT NULL,
    summary    TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_events_type CHECK (
        type IN ('note', 'user_message', 'agent_reply',
                 'context_update', 'handover', 'error')
    )
);

CREATE INDEX IF NOT EXISTS ix_events_project_created
    ON events (project_id, created_at);

CREATE TABLE IF NOT EXISTS agents (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(64) NOT NULL UNIQUE,
    provider   VARCHAR(64) NOT NULL,
    model      VARCHAR(128),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Snapshot written when one agent stops and another must pick up.
CREATE TABLE IF NOT EXISTS handovers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL
                        REFERENCES projects(id) ON DELETE CASCADE,
    from_agent          VARCHAR(64) NOT NULL,
    to_agent            VARCHAR(64),
    reason              TEXT NOT NULL,
    last_action         TEXT NOT NULL DEFAULT '',
    suggested_next_step TEXT NOT NULL DEFAULT '',
    context_snapshot    JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_handovers_project_created
    ON handovers (project_id, created_at);

-- Open handovers are what the dashboard alerts on.
CREATE INDEX IF NOT EXISTS ix_handovers_unresolved
    ON handovers (project_id) WHERE resolved_at IS NULL;
