"use client";

import { useState } from "react";
import type { Project } from "@/lib/types";

interface Props {
  projects: Project[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: (data: {
    name: string;
    description?: string;
    current_task?: string;
    next_step?: string;
  }) => Promise<void>;
}

export function ProjectList({
  projects,
  selectedId,
  loading,
  onSelect,
  onCreate,
}: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [currentTask, setCurrentTask] = useState("");
  const [nextStep, setNextStep] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      await onCreate({
        name: name.trim(),
        current_task: currentTask.trim(),
        next_step: nextStep.trim(),
      });
      setName("");
      setCurrentTask("");
      setNextStep("");
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="spread">
        <h2>Projects</h2>
        <button className="link" onClick={() => setOpen((v) => !v)}>
          {open ? "Cancel" : "New"}
        </button>
      </div>

      {open && (
        <form className="stack" onSubmit={submit} style={{ marginBottom: 12 }}>
          <div>
            <label htmlFor="np-name">Name</label>
            <input
              id="np-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Payments rewrite"
              autoFocus
            />
          </div>
          <div>
            <label htmlFor="np-task">Current task</label>
            <input
              id="np-task"
              value={currentTask}
              onChange={(e) => setCurrentTask(e.target.value)}
              placeholder="Design the ledger schema"
            />
          </div>
          <div>
            <label htmlFor="np-next">Next step</label>
            <input
              id="np-next"
              value={nextStep}
              onChange={(e) => setNextStep(e.target.value)}
              placeholder="List the required tables"
            />
          </div>
          <button type="submit" disabled={!name.trim() || busy}>
            {busy ? "Creating…" : "Create project"}
          </button>
        </form>
      )}

      <div className="stack" style={{ gap: 4 }}>
        {projects.length === 0 && (
          <p className="muted small" style={{ margin: 0 }}>
            {loading
              ? "Loading projects…"
              : "No projects yet. Create one to start a shared memory."}
          </p>
        )}
        {projects.map((project) => (
          <button
            key={project.id}
            className="project"
            aria-current={project.id === selectedId}
            onClick={() => onSelect(project.id)}
          >
            {project.name}
            <small>{project.description ?? "No description"}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
