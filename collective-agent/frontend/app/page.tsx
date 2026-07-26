"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type {
  Agent,
  AgentUsage,
  Context,
  Event,
  Handover,
  ManualPrompt,
  Project,
} from "@/lib/types";
import { SignInGate, useAuth } from "./AuthProvider";
import { Composer } from "./components/Composer";
import { Conversation } from "./components/Conversation";
import { ManualBridge } from "./components/ManualBridge";
import { ModelRail } from "./components/ModelRail";
import { UsagePanel } from "./components/UsagePanel";

const POLL_MS = 10_000;

export default function Page() {
  return (
    <SignInGate>
      <Chat />
    </SignInGate>
  );
}

/**
 * A single conversation, one input, one agent picker, one usage readout.
 *
 * Projects still exist underneath — they are the shared memory every agent
 * reads — but the interface does not ask about them: the newest conversation is
 * opened automatically and "New chat" makes another.
 */
function Chat() {
  const { required, userName, signOut } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [usage, setUsage] = useState<AgentUsage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [handover, setHandover] = useState<Handover | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [manual, setManual] = useState(false);
  const [bridge, setBridge] = useState<{
    prompt: ManualPrompt;
    message: string;
  } | null>(null);

  // Don't let a slow poll overwrite state from a newer conversation.
  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedId;

  const report = useCallback((cause: unknown) => {
    setError(
      cause instanceof ApiError
        ? cause.message
        : "Something went wrong. Check the console.",
    );
    if (!(cause instanceof ApiError)) console.error(cause);
  }, []);

  const loadShell = useCallback(async () => {
    try {
      const [projectList, agentList, usageList] = await Promise.all([
        api.listProjects(),
        api.listAgents(),
        api.listUsage(),
      ]);
      setProjects(projectList);
      setAgents(agentList);
      setUsage(usageList);
      setSelectedAgent((current) => {
        if (current && agentList.some((a) => a.name === current && a.is_active))
          return current;
        // Prefer a real model over the offline stub when one is configured.
        const real = agentList.find((a) => a.is_active && a.name !== "echo");
        return (real ?? agentList.find((a) => a.is_active))?.name ?? null;
      });
      setSelectedId((current) => current ?? projectList[0]?.id ?? null);
      setError(null);
    } catch (cause) {
      report(cause);
    } finally {
      setLoading(false);
    }
  }, [report]);

  const loadConversation = useCallback(
    async (projectId: string) => {
      try {
        const [ctx, eventList, open] = await Promise.all([
          api.getContext(projectId),
          api.listEvents(projectId),
          api.listOpenHandovers(projectId),
        ]);
        if (selectedRef.current !== projectId) return;
        setContext(ctx);
        setEvents(eventList);
        setHandover(open[0] ?? null);
        setError(null);
      } catch (cause) {
        report(cause);
      }
    },
    [report],
  );

  useEffect(() => {
    void loadShell();
  }, [loadShell]);

  useEffect(() => {
    if (!selectedId) {
      setContext(null);
      setEvents([]);
      setHandover(null);
      return;
    }
    void loadConversation(selectedId);
    // Another agent (or another operator) may write to this project; keep the
    // view close to the shared state without a socket layer.
    const timer = setInterval(() => {
      if (!busy) void loadConversation(selectedId);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [selectedId, loadConversation, busy]);

  async function newChat() {
    try {
      const created = await api.createProject({
        name: `Chat ${new Date().toLocaleString()}`,
      });
      setProjects((prev) => [created, ...prev]);
      setSelectedId(created.id);
      setEvents([]);
      setHandover(null);
    } catch (cause) {
      report(cause);
    }
  }

  /** The current conversation, creating one silently on the first message. */
  async function ensureConversation(): Promise<string | null> {
    if (selectedId) return selectedId;
    try {
      const created = await api.createProject({
        name: `Chat ${new Date().toLocaleString()}`,
      });
      setProjects((prev) => [created, ...prev]);
      setSelectedId(created.id);
      return created.id;
    } catch (cause) {
      report(cause);
      return null;
    }
  }

  /** Manual bridge: build the briefing, then wait for the pasted answer. */
  async function startManual(message: string) {
    if (!selectedAgent) return;
    const projectId = await ensureConversation();
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const prompt = await api.manualPrompt(projectId, selectedAgent, message);
      setBridge({ prompt, message });
    } catch (cause) {
      report(cause);
    } finally {
      setBusy(false);
    }
  }

  async function saveManualReply(reply: string) {
    const projectId = selectedId;
    if (!projectId || !bridge) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.manualReply(projectId, {
        agent_name: bridge.prompt.agent_name,
        message: bridge.message,
        reply,
      });
      setContext(result.context);
      setBridge(null);
      await loadConversation(projectId);
      setUsage(await api.listUsage());
    } catch (cause) {
      report(cause);
    } finally {
      setBusy(false);
    }
  }

  /** Delete the open conversation, and drop back to whatever remains. */
  async function clearChat() {
    if (!selectedId) return;
    if (!window.confirm("Delete this conversation and its history?")) return;
    try {
      await api.deleteProject(selectedId);
      const remaining = projects.filter((p) => p.id !== selectedId);
      setProjects(remaining);
      setBridge(null);
      setSelectedId(remaining[0]?.id ?? null);
    } catch (cause) {
      report(cause);
    }
  }

  async function clearAll() {
    if (
      !window.confirm(
        "Delete every conversation? This cannot be undone.",
      )
    )
      return;
    try {
      await api.deleteAllProjects();
      setProjects([]);
      setSelectedId(null);
      setEvents([]);
      setContext(null);
      setHandover(null);
      setBridge(null);
    } catch (cause) {
      report(cause);
    }
  }

  async function runTurn(agentName: string, message: string) {
    const projectId = await ensureConversation();
    if (!projectId) return;

    setBusy(true);
    setError(null);
    try {
      const result = await api.runTurn(projectId, agentName, message);
      setContext(result.context);
      setHandover(result.handover);
      setSelectedAgent(agentName);
      await loadConversation(projectId);
      setUsage(await api.listUsage());
    } catch (cause) {
      report(cause);
      await loadConversation(projectId);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <h1>Collective</h1>
        </div>

        <div className="row" style={{ gap: 10 }}>
          <UsagePanel usage={usage} />
          {required && userName && (
            <button
              className="ghost"
              onClick={signOut}
              title={`Signed in as ${userName}`}
            >
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className="stage">
        <ModelRail
          agents={agents}
          selected={selectedAgent}
          lastUsed={context?.last_agent_used ?? null}
          manual={manual}
          hasChat={Boolean(selectedId)}
          onSelect={setSelectedAgent}
          onNewChat={newChat}
          onClearChat={clearChat}
          onClearAll={clearAll}
        />

        <div className="thread">
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="conversation empty">
              <span className="spinner" />
            </div>
          ) : (
            <Conversation
              events={events}
              busy={busy}
              pendingAgent={selectedAgent}
            />
          )}

          {bridge ? (
            <ManualBridge
              prompt={bridge.prompt}
              busy={busy}
              onSubmit={saveManualReply}
              onCancel={() => setBridge(null)}
            />
          ) : (
            <Composer
              canSend={Boolean(selectedAgent)}
              busy={busy}
              manual={manual}
              onToggleManual={setManual}
              onRun={(message) =>
                manual
                  ? startManual(message)
                  : selectedAgent
                    ? runTurn(selectedAgent, message)
                    : Promise.resolve()
              }
            />
          )}
        </div>
      </main>
    </>
  );
}
