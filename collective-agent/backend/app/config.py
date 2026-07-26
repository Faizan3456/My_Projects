"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Tests (and anything else that must not inherit a developer's local file) set
# COLLECTIVE_IGNORE_ENV_FILE=1 so configuration comes from the environment only.
_ENV_FILES: tuple[str, ...] | None = (
    None if os.environ.get("COLLECTIVE_IGNORE_ENV_FILE") == "1" else (".env", "../.env")
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- service ---
    app_name: str = "Collective AI Agent System"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # --- database ---
    # asyncpg driver URL. docker-compose overrides the host to "db".
    database_url: str = (
        "postgresql+asyncpg://collective:collective@localhost:5432/collective"
    )
    # Create tables on startup. Fine for dev; use db/schema.sql in production.
    db_auto_create: bool = True
    db_echo: bool = False

    # --- authentication ---
    # "entra" (Microsoft Entra ID), "token" (shared secret only), or "disabled".
    # Production refuses to start on "disabled".
    auth_mode: str = "disabled"
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    # Optional allow list of UPNs / object ids. Empty means any account in the
    # tenant may sign in.
    entra_allowed_users: str = ""
    # Shared secret for scripts and cron (X-Service-Token header).
    service_token: str = ""
    jwks_ttl_seconds: int = 3600

    # --- memory / prompt shaping ---
    prompt_history_limit: int = 12
    summary_max_chars: int = 600

    # --- connectors ---
    # Any provider without a key is reported as inactive by GET /agents.
    anthropic_api_key: str = ""
    # Sonnet by default: markedly faster than Opus and strong enough for this
    # workload. Set ANTHROPIC_MODEL=claude-opus-5 when depth matters more.
    anthropic_model: str = "claude-sonnet-5"
    anthropic_base_url: str = "https://api.anthropic.com"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # GitHub Copilot has no public completion API; Copilot-branded models are
    # served through GitHub Models, which speaks the OpenAI wire format.
    github_token: str = ""
    copilot_model: str = "gpt-4o"
    copilot_base_url: str = "https://models.inference.ai.azure.com"

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Free API tier, no card, and the fastest hosted option.
    # Key: https://console.groq.com/keys
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # One key, many models. Ids ending ":free" cost nothing but are rate-limited.
    # Key: https://openrouter.ai/keys
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "https://agents.openedgetechnologies.com"

    # Any OpenAI-compatible local server (Ollama, vLLM, LM Studio, llama.cpp).
    local_llm_base_url: str = ""
    local_llm_model: str = "llama3.1"

    # Deterministic offline connector, for demos and tests.
    enable_echo_connector: bool = True

    # --- collective behaviour ---
    # When an agent hits its limit, hand the work to the next configured agent
    # automatically instead of stopping and waiting to be told.
    auto_failover: bool = True
    # How many further agents may be tried for one turn. Bounded so a bad prompt
    # cannot burn every provider's quota in a single request.
    max_failover_hops: int = 3
    # Preference order, comma separated. Names not listed are tried afterwards in
    # registry order. `echo` is never chosen automatically — it answers without
    # calling a model, which would end the chain with a useless reply.
    failover_order: str = "claude,groq,openrouter,chatgpt,gemini,copilot,local"

    agent_timeout_seconds: float = 120.0
    # A cap, not a target: it costs nothing when replies are short, and stops
    # long ones being cut off mid-sentence (which also loses the trailing memory
    # block, forcing a fallback summary).
    agent_max_tokens: int = 8000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def failover_sequence(self) -> list[str]:
        return [name.strip() for name in self.failover_order.split(",") if name.strip()]

    @property
    def entra_allowed_user_list(self) -> set[str]:
        return {
            entry.strip().lower()
            for entry in self.entra_allowed_users.split(",")
            if entry.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
