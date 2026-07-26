"use client";

import { useEffect, useState } from "react";
import type { Context, ContextStatus } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

const STATUSES: ContextStatus[] = ["active", "blocked", "handover_required", "done"];

interface Props {
  context: Context;
  onSave: (patch: {
    current_task?: string;
    next_step?: string;
    status?: ContextStatus;
  }) => Promise<void>;
}

export function ContextPanel({ context, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [currentTask, setCurrentTask] = useState(context.current_task);
  const [nextStep, setNextStep] = useState(context.next_step);
  const [status, setStatus] = useState<ContextStatus>(context.status);

  // Agents update the context underneath us; keep the form in sync when it does.
  useEffect(() => {
    if (editing) return;
    setCurrentTask(context.current_task);
    setNextStep(context.next_step);
    setStatus(context.status);
  }, [context, editing]);

  async function save() {
    setBusy(true);
    try {
      await onSave({ current_task: currentTask, next_step: nextStep, status });
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  const memoryKeys = Object.keys(context.memory ?? {});

  return (
    <section className="panel">
      <div className="spread">
        <h2>Shared memory</h2>
        <div className="row">
          <StatusBadge status={context.status} />
          <button className="link" onClick={() => setEditing((v) => !v)}>
            {editing ? "Cancel" : "Edit"}
          </button>
        </div>
      </div>

      {editing ? (
        <div className="stack">
          <div>
            <label htmlFor="ctx-task">Current task</label>
            <input
              id="ctx-task"
              value={currentTask}
              onChange={(e) => setCurrentTask(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="ctx-next">Next step</label>
            <input
              id="ctx-next"
              value={nextStep}
              onChange={(e) => setNextStep(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="ctx-status">Status</label>
            <select
              id="ctx-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ContextStatus)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="row">
            <button onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save to memory"}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="field">
            <label>Current task</label>
            <div className="value">
              {context.current_task || <span className="muted">Not set</span>}
            </div>
          </div>
          <div className="field">
            <label>Next step</label>
            <div className="value">
              {context.next_step || <span className="muted">Not set</span>}
            </div>
          </div>
          <div className="field">
            <label>Last agent used</label>
            <div className="value">
              {context.last_agent_used ? (
                <span style={{ textTransform: "capitalize" }}>
                  {context.last_agent_used}
                </span>
              ) : (
                <span className="muted">None yet</span>
              )}
              <span className="muted small">
                {" · updated "}
                {new Date(context.updated_at).toLocaleString()}
              </span>
            </div>
          </div>
          {memoryKeys.length > 0 && (
            <div className="field">
              <label>Durable facts ({memoryKeys.length})</label>
              <pre className="mono">{JSON.stringify(context.memory, null, 2)}</pre>
            </div>
          )}
        </>
      )}
    </section>
  );
}
