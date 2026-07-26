export type ContextStatus = "active" | "blocked" | "handover_required" | "done";

export type EventType =
  | "note"
  | "user_message"
  | "agent_reply"
  | "context_update"
  | "handover"
  | "error";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ProjectDetail extends Project {
  context: Context | null;
}

export interface Context {
  id: string;
  project_id: string;
  current_task: string;
  next_step: string;
  status: ContextStatus;
  last_agent_used: string | null;
  memory: Record<string, unknown>;
  updated_at: string;
}

export interface Event {
  id: string;
  project_id: string;
  agent_name: string | null;
  type: EventType;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Agent {
  name: string;
  provider: string;
  model: string | null;
  is_active: boolean;
  reason: string | null;
}

/**
 * What an agent has spent here and what the provider says is left.
 * `limits` mirrors the provider's rate-limit headers; it is empty for providers
 * that publish none. No provider exposes a spendable credit balance.
 */
export interface AgentUsage {
  agent: string;
  model: string | null;
  is_active: boolean;
  unavailable_reason: string | null;
  turns: number;
  input_tokens: number;
  output_tokens: number;
  limits: {
    requests_remaining?: number;
    requests_limit?: number;
    tokens_remaining?: number;
    tokens_limit?: number;
    resets_at?: string;
  };
  last_used_at: string | null;
  stopped_reason: string | null;
}

/** A briefing to paste into a chat window you are already signed in to. */
export interface ManualPrompt {
  agent_name: string;
  chat_url: string;
  text: string;
}

export interface Handover {
  id: string;
  project_id: string;
  from_agent: string;
  to_agent: string | null;
  reason: string;
  last_action: string;
  suggested_next_step: string;
  context_snapshot: Record<string, unknown>;
  resolved_at: string | null;
  created_at: string;
}

export interface TurnResponse {
  status: "completed" | "handover_required";
  agent_name: string;
  reply: string | null;
  summary: string | null;
  context: Context;
  event: Event | null;
  handover: Handover | null;
}
