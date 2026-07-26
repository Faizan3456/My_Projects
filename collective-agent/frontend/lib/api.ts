import type {
  Agent,
  AgentUsage,
  Context,
  ManualPrompt,
  ContextStatus,
  Event,
  Handover,
  Project,
  ProjectDetail,
  TurnResponse,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Supplies the bearer token for every request. Installed by the auth provider so
 * this module stays independent of MSAL — and of whether auth is on at all.
 */
type TokenProvider = () => Promise<string | null>;
let getToken: TokenProvider = async () => null;

export function setTokenProvider(provider: TokenProvider): void {
  getToken = provider;
}

async function authHeaders(): Promise<Record<string, string>> {
  try {
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    // A token failure should surface as a 401 from the service rather than as an
    // unhandled rejection in whichever component happened to trigger the call.
    return {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(await authHeaders()),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      0,
      "unreachable",
      `Cannot reach the shared memory service at ${BASE}. Is the backend running?`,
    );
  }

  if (response.status === 204) return undefined as T;

  const body = await response.text();
  const parsed = body ? safeJson(body) : null;

  if (!response.ok) {
    const detail = parsed as { error?: string; message?: string; detail?: unknown };
    throw new ApiError(
      response.status,
      detail?.error ?? "error",
      detail?.message ??
        (typeof detail?.detail === "string"
          ? detail.detail
          : `Request failed with ${response.status}`),
    );
  }
  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

export const api = {
  baseUrl: BASE,

  listProjects: () => request<Project[]>("/projects"),

  createProject: (data: {
    name: string;
    description?: string;
    current_task?: string;
    next_step?: string;
  }) =>
    request<ProjectDetail>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),

  deleteAllProjects: () => request<void>("/projects", { method: "DELETE" }),

  getContext: (id: string) => request<Context>(`/projects/${id}/context`),

  updateContext: (
    id: string,
    data: Partial<{
      current_task: string;
      next_step: string;
      status: ContextStatus;
      last_agent_used: string;
      memory: Record<string, unknown>;
    }>,
  ) =>
    request<Context>(`/projects/${id}/context`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listEvents: (id: string, limit = 50) =>
    request<Event[]>(`/projects/${id}/events?limit=${limit}`),

  addEvent: (id: string, data: { type?: string; summary: string; agent_name?: string }) =>
    request<Event>(`/projects/${id}/events`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listAgents: () => request<Agent[]>("/agents"),

  listUsage: () => request<AgentUsage[]>("/usage"),

  // --- manual bridge: your own chat windows, same shared memory ---

  manualPrompt: (id: string, agentName: string, message: string) =>
    request<ManualPrompt>(`/projects/${id}/manual/prompt`, {
      method: "POST",
      body: JSON.stringify({ agent_name: agentName, message }),
    }),

  manualReply: (
    id: string,
    data: { agent_name: string; message: string; reply: string },
  ) =>
    request<TurnResponse>(`/projects/${id}/manual/reply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listOpenHandovers: (id: string) =>
    request<Handover[]>(`/projects/${id}/handovers?unresolved_only=true`),

  runTurn: (id: string, agent_name: string, message: string) =>
    request<TurnResponse>(`/projects/${id}/turns`, {
      method: "POST",
      body: JSON.stringify({ agent_name, message }),
    }),

  createHandover: (data: {
    project_id: string;
    from_agent: string;
    reason: string;
    last_action?: string;
    suggested_next_step?: string;
  }) =>
    request<Handover>("/handover", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  resolveHandover: (handoverId: string, to_agent: string) =>
    request<Handover>(`/handover/${handoverId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ to_agent }),
    }),
};
