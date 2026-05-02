// Read-only client for the v3.15.15.18 mobile-first Agent Control PWA.
// All five endpoints are GET-only and return JSON. Anything that goes
// wrong on the wire (missing endpoint, 404, 500, parse error, network
// down) collapses to a `not_available` envelope so the UI never has
// to invent data. Nothing on this surface is allowed to mutate.

export type AgentControlStatusEnvelope = {
  status: "ok" | "not_available";
  reason?: string;
  data?: unknown;
};

export interface FrozenHashesPayload {
  status: "ok" | "not_available";
  reason?: string;
  data?: Record<string, string>;
}

export interface AgentControlStatus {
  kind: "agent_control_status";
  schema_version: number;
  governance_status: AgentControlStatusEnvelope;
  frozen_hashes: FrozenHashesPayload;
}

export interface AgentControlActivity {
  kind: "agent_control_activity";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    schema_version: number;
    report_kind: string;
    ledger_path: string;
    ledger_present: boolean;
    ledger_event_count: number;
    chain_status: string;
    rows: Array<Record<string, unknown>>;
  };
}

export interface AgentControlWorkloop {
  kind: "agent_control_workloop";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: Record<string, unknown>;
  artifact_path: string;
}

export interface AgentControlPRLifecycle {
  kind: "agent_control_pr_lifecycle";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    final_recommendation: string;
    prs: Array<Record<string, unknown>>;
    [k: string]: unknown;
  };
  artifact_path: string;
}

export interface AgentControlNotifications {
  kind: "agent_control_notifications";
  schema_version: number;
  status: "ok" | "not_available";
  mode?: string;
  data: Array<Record<string, unknown>>;
  next_release_with_push?: string;
}

export interface AgentControlProposals {
  kind: "agent_control_proposals";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    final_recommendation: string;
    proposals: Array<Record<string, unknown>>;
    counts?: Record<string, unknown>;
    [k: string]: unknown;
  };
  artifact_path: string;
}

const BASE = "/api/agent-control";

async function getJson<T>(path: string): Promise<T> {
  try {
    const res = await fetch(path, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      // Surface as not_available rather than throwing — the cards
      // need a renderable payload even when the wiring step in
      // dashboard/dashboard.py has not yet landed.
      return {
        status: "not_available",
        reason: `http_${res.status}`,
      } as unknown as T;
    }
    const body = (await res.json()) as T;
    return body;
  } catch (err) {
    return {
      status: "not_available",
      reason: `fetch_error: ${(err as Error)?.name || "Error"}`,
    } as unknown as T;
  }
}

export const agentControlApi = {
  status: () => getJson<AgentControlStatus>(`${BASE}/status`),
  activity: () => getJson<AgentControlActivity>(`${BASE}/activity`),
  workloop: () => getJson<AgentControlWorkloop>(`${BASE}/workloop`),
  prLifecycle: () =>
    getJson<AgentControlPRLifecycle>(`${BASE}/pr-lifecycle`),
  notifications: () =>
    getJson<AgentControlNotifications>(`${BASE}/notifications`),
  proposals: () => getJson<AgentControlProposals>(`${BASE}/proposals`),
};
