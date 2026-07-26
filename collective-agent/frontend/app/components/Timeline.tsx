"use client";

import type { Event, EventType } from "@/lib/types";

const LABELS: Record<EventType, string> = {
  note: "note",
  user_message: "you",
  agent_reply: "reply",
  context_update: "memory",
  handover: "handover",
  error: "error",
};

function badgeClass(type: EventType): string {
  if (type === "handover") return "badge handover_required";
  if (type === "error") return "badge error";
  if (type === "agent_reply") return "badge active";
  return "badge";
}

export function Timeline({ events }: { events: Event[] }) {
  if (events.length === 0) {
    return (
      <section className="panel">
        <h2>History</h2>
        <p className="muted small" style={{ margin: 0 }}>
          Nothing recorded yet.
        </p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>History ({events.length})</h2>
      <ul className="timeline">
        {events.map((event) => {
          const reply = typeof event.payload?.reply === "string" ? event.payload.reply : null;
          return (
            <li key={event.id}>
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              <div>
                <div className="row" style={{ gap: 6, marginBottom: 2 }}>
                  <span className="who" style={{ textTransform: "capitalize" }}>
                    {event.agent_name ?? "You"}
                  </span>
                  <span className={badgeClass(event.type)}>{LABELS[event.type]}</span>
                </div>
                <div className="summary">{event.summary}</div>
                {reply && (
                  <details>
                    <summary>Full reply</summary>
                    <pre>{reply}</pre>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
