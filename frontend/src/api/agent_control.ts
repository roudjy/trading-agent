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
  workloop_runtime?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      runtime_version?: string;
      generated_at_utc?: string;
      mode?: string;
      iteration?: number;
      duration_ms?: number;
      safe_to_execute?: boolean;
      loop_health?: {
        consecutive_failures?: number;
        iterations_completed?: number;
        iterations_failed?: number;
      };
      counts?: { total?: number; by_state?: Record<string, number> };
      final_recommendation?: string;
      source_states?: Array<{ source: string; state: string }>;
    };
  };
  recurring_maintenance?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      module_version?: string;
      generated_at_utc?: string;
      mode?: string;
      safe_to_execute?: boolean;
      counts?: { total?: number; by_status?: Record<string, number> };
      final_recommendation?: string;
      jobs?: Array<{
        job_type: string;
        last_status: string;
        enabled?: boolean;
        consecutive_failures?: number;
        next_run_after_utc?: string | null;
      }>;
    };
  };
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

export interface AgentControlApprovalInbox {
  kind: "agent_control_approval_inbox";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    final_recommendation: string;
    items: Array<Record<string, unknown>>;
    counts?: {
      total?: number;
      by_severity?: Record<string, number>;
      by_category?: Record<string, number>;
      by_status?: Record<string, number>;
    };
    [k: string]: unknown;
  };
  artifact_path: string;
}

export interface AgentControlExecuteSafe {
  kind: "agent_control_execute_safe";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    report_kind: string;
    git_clean: boolean;
    git_dirty_count: number;
    gh_provider?: { status?: string };
    actions: Array<{
      action_id: string;
      action_type: string;
      title: string;
      summary: string;
      risk_class: string;
      eligibility: string;
      blocked_reason: string | null;
      [k: string]: unknown;
    }>;
    counts?: Record<string, unknown>;
  };
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
  approvalInbox: () =>
    getJson<AgentControlApprovalInbox>(`${BASE}/approval-inbox`),
  executeSafe: () =>
    getJson<AgentControlExecuteSafe>(`${BASE}/execute-safe`),
};
