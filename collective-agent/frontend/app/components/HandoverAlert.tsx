"use client";

import type { Agent, Handover } from "@/lib/types";

interface Props {
  handover: Handover;
  agents: Agent[];
  busy: boolean;
  onContinueWith: (agentName: string) => void;
}

export function HandoverAlert({ handover, agents, busy, onContinueWith }: Props) {
  const alternatives = agents.filter(
    (agent) => agent.is_active && agent.name !== handover.from_agent,
  );

  return (
    <section className="alert">
      <h2>Handover required</h2>
      <p style={{ margin: "0 0 8px" }}>
        <strong style={{ textTransform: "capitalize" }}>{handover.from_agent}</strong>{" "}
        stopped: {handover.reason}
      </p>
      {handover.last_action && (
        <p className="small" style={{ margin: "0 0 4px" }}>
          <span className="muted">Last action: </span>
          {handover.last_action}
        </p>
      )}
      {handover.suggested_next_step && (
        <p className="small" style={{ margin: "0 0 10px" }}>
          <span className="muted">Resume at: </span>
          {handover.suggested_next_step}
        </p>
      )}
      {alternatives.length > 0 ? (
        <div className="row">
          <span className="small muted">Continue with:</span>
          {alternatives.map((agent) => (
            <button
              key={agent.name}
              className="ghost"
              disabled={busy}
              onClick={() => onContinueWith(agent.name)}
              style={{ textTransform: "capitalize" }}
            >
              {agent.name}
            </button>
          ))}
        </div>
      ) : (
        <p className="small" style={{ margin: 0 }}>
          No other agent is configured. Add a provider key to continue this work.
        </p>
      )}
    </section>
  );
}
