"use client";

import type { Agent } from "@/lib/types";

interface Props {
  agents: Agent[];
  selected: string | null;
  lastUsed: string | null;
  onSelect: (name: string) => void;
}

export function AgentPanel({ agents, selected, lastUsed, onSelect }: Props) {
  return (
    <section className="panel">
      <h2>Agents</h2>
      <div className="stack" style={{ gap: 6 }}>
        {agents.map((agent) => (
          <button
            key={agent.name}
            className="agent"
            aria-current={agent.name === selected}
            disabled={!agent.is_active}
            title={agent.reason ?? `${agent.provider} · ${agent.model ?? "default"}`}
            onClick={() => onSelect(agent.name)}
          >
            <span>
              <span className="name">{agent.name}</span>
              <br />
              <span className="muted small">{agent.model ?? agent.provider}</span>
            </span>
            <span className={`badge ${agent.is_active ? "active" : "off"}`}>
              {agent.name === lastUsed ? "last used" : agent.is_active ? "ready" : "no key"}
            </span>
          </button>
        ))}
      </div>
      <p className="muted small" style={{ marginBottom: 0 }}>
        Any ready agent can pick up this project — they all read the same memory.
      </p>
    </section>
  );
}
