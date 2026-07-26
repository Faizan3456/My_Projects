"use client";

import type { Agent } from "@/lib/types";

/**
 * The model list, down the side. Choosing one here is the only agent control:
 * the composer stays a plain text box.
 */
interface Props {
  agents: Agent[];
  selected: string | null;
  lastUsed: string | null;
  /** Manual mode uses your own login, so a missing API key is no obstacle. */
  manual: boolean;
  hasChat: boolean;
  onSelect: (name: string) => void;
  onNewChat: () => void;
  onClearChat: () => void;
  onClearAll: () => void;
}

export function ModelRail({
  agents,
  selected,
  lastUsed,
  manual,
  hasChat,
  onSelect,
  onNewChat,
  onClearChat,
  onClearAll,
}: Props) {
  return (
    <nav className="rail" aria-label="Models">
      <button className="new-chat" onClick={onNewChat}>
        New chat
      </button>

      <div className="rail-tools">
        <button
          className="ghost small"
          onClick={onClearChat}
          disabled={!hasChat}
          title="Delete this conversation"
        >
          Clear chat
        </button>
        <button
          className="ghost small danger"
          onClick={onClearAll}
          title="Delete every conversation"
        >
          Clear all
        </button>
      </div>

      <h2 className="rail-title">Models</h2>
      <ul>
        {agents.map((agent) => {
          const active = agent.name === selected;
          const usable = agent.is_active || manual;
          return (
            <li key={agent.name}>
              <button
                className={active ? "model-option selected" : "model-option"}
                onClick={() => usable && onSelect(agent.name)}
                disabled={!usable}
                title={
                  manual && !agent.is_active
                    ? "No API key — usable with your own login"
                    : (agent.reason ?? agent.model ?? agent.name)
                }
                aria-pressed={active}
              >
                <span className="model-line">
                  <span className="model-title">{agent.name}</span>
                  {agent.name === lastUsed && (
                    <span className="model-flag">last</span>
                  )}
                </span>
                <span className="model-sub">
                  {agent.is_active
                    ? agent.model
                    : manual
                      ? "your login"
                      : "no key"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
