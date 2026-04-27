// Thin fetch wrapper for the Flask control-surface API.
// The frontend contains ZERO business logic — all data comes from /api/*.
// Session cookie is set by the Flask /api/session/login endpoint; this
// client always sends credentials so the cookie rides along.

import type {
  SystemArtifactIndex,
  SystemMetaVersion,
  SystemSprintStatus,
} from "./system";

export interface Health {
  status: string;
  version: string;
  last_run_age_seconds: number | null;
  scheduler_next_fire_utc: string | null;
}

export type PresetClass = "baseline" | "diagnostic" | "experimental";

export type PresetDecisionKind =
  | "disabled_planned"
  | "diagnostic_only"
  | "scheduler_excluded"
  | null;

export interface PresetDecision {
  is_product_decision: boolean;
  kind: PresetDecisionKind;
  summary: string;
  requires_enablement: boolean;
}

export interface PresetCard {
  name: string;
  hypothesis: string;
  universe: string[];
  timeframe: string;
  bundle: string[];
  optional_bundle: string[];
  screening_mode: string;
  cost_mode: string;
  status: "stable" | "planned" | "diagnostic" | "not_executable";
  enabled: boolean;
  diagnostic_only: boolean;
  excluded_from_daily_scheduler: boolean;
  excluded_from_candidate_promotion: boolean;
  regime_filter: string | null;
  regime_modes: string[];
  backlog_reason: string | null;
  preset_class: PresetClass;
  rationale: string;
  expected_behavior: string;
  falsification: string[];
  enablement_criteria: string[];
  decision: PresetDecision;
}

export interface PublicArtifactRunBlock {
  run_id: string | null;
  attempted_at_utc?: string | null;
  written_at_utc?: string | null;
  preset: string | null;
  outcome?: "success" | "degenerate" | "error" | null;
  failure_stage?: string | null;
}

export interface PublicArtifactStatus {
  state: "valid" | "absent" | "empty" | "invalid_json" | "unreadable";
  schema_version: string | null;
  public_artifact_status_version: string | null;
  generated_at_utc?: string | null;
  artifact_modified_at_utc: string | null;
  last_attempted_run: PublicArtifactRunBlock | null;
  last_public_artifact_write: PublicArtifactRunBlock | null;
  last_public_write_age_seconds: number | null;
  public_artifacts_stale: boolean | null;
  stale_reason:
    | "degenerate_run_no_public_write"
    | "error_no_public_write"
    | "public_write_never_occurred"
    | null;
  stale_since_utc: string | null;
}

export interface ReportPayload {
  run_id: string | null;
  preset: string | null;
  generated_at_utc: string;
  summary: Record<string, number>;
  top_rejection_reasons: { reason: string; count: number }[];
  candidates: Record<string, unknown>[];
  red_flags: { check?: string; status?: string; message?: string }[];
  verdict: string;
  next_experiment: string;
  [key: string]: unknown;
}

export interface ResearchIntelligenceSummary {
  schema_version: string;
  enforcement_state: "advisory_only";
  viability: {
    status?:
      | "insufficient_data"
      | "promising"
      | "weak"
      | "commercially_questionable"
      | "stop_or_pivot";
    reason_codes?: string[];
    human_summary?: string;
  };
  metrics: Record<string, number | null>;
  information_gain: {
    score?: number;
    bucket?: "none" | "low" | "medium" | "high";
    is_meaningful_campaign?: boolean;
    reasons?: { code: string; weight: number; explanation: string }[];
  };
  advisory_decision_count: number;
  dead_zone_count: number;
  ledger_summary: Record<string, number>;
  spawn_proposals?: {
    proposal_mode?: "normal" | "diagnostic_only";
    proposed_count?: number;
    suppressed_zone_count?: number;
    human_review_required?: boolean;
    top_proposals?: {
      preset_name?: string;
      proposal_type?: string;
      spawn_reason?: string;
      priority_tier?: "HIGH" | "MEDIUM" | "LOW" | "SUPPRESSED";
    }[];
  };
}

export interface RunStatus {
  run_state: Record<string, unknown>;
  run_progress: Record<string, unknown>;
  run_campaign: Record<string, unknown>;
  dashboard_observations: Record<string, unknown>;
  warnings: string[];
  as_of_utc: string;
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    ...init,
  });
  if (res.status === 401) {
    throw new ApiError(401, "authentication required");
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || `request failed: ${res.status}`);
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  presets: () => request<{ presets: PresetCard[] }>("/api/presets"),
  runPreset: (name: string) =>
    request<Record<string, unknown>>(`/api/presets/${encodeURIComponent(name)}/run`, {
      method: "POST",
    }),
  reportLatest: () =>
    request<{ markdown: string | null; payload: ReportPayload | null }>(
      "/api/report/latest"
    ),
  reportHistory: () =>
    request<{ reports: { path: string; run_id: string; modified_at_utc: string }[] }>(
      "/api/report/history"
    ),
  candidatesLatest: () => request<Record<string, unknown>>("/api/candidates/latest"),
  runStatus: () => request<RunStatus>("/api/research/run-status"),
  publicArtifactStatus: () =>
    request<PublicArtifactStatus>("/api/research/public-artifact-status"),
  campaignDigest: () => request<Record<string, unknown>>("/api/campaigns/digest"),
  campaignQueue: () => request<Record<string, unknown>>("/api/campaigns/queue"),
  campaignRegistry: () => request<Record<string, unknown>>("/api/campaigns/registry"),
  campaignPresetState: () => request<Record<string, unknown>>("/api/campaigns/preset-state"),
  campaignTemplates: () => request<Record<string, unknown>>("/api/campaigns/templates"),
  campaignPolicyLatest: () => request<Record<string, unknown>>("/api/campaigns/policy/latest"),
  campaignBudget: () => request<Record<string, unknown>>("/api/campaigns/budget"),
  campaignFamilyState: () => request<Record<string, unknown>>("/api/campaigns/family-state"),
  campaignEvidence: () => request<Record<string, unknown>>("/api/campaigns/evidence"),
  researchIntelligenceSummary: () =>
    request<ResearchIntelligenceSummary>("/api/research/intelligence-summary"),
  systemVersion: () => request<SystemMetaVersion>("/api/system/version"),
  systemArtifactIndex: () =>
    request<SystemArtifactIndex>("/api/research/artifact-index"),
  sprintStatus: () => request<SystemSprintStatus>("/api/research/sprint-status"),
  login: (username: string, password: string) =>
    request<{ ok: boolean; actor?: string; error?: string }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    request<{ ok: boolean }>("/api/session/logout", { method: "POST" }),
};

export { ApiError };
export type {
  SystemArtifactIndex,
  SystemArtifactDirectory,
  SystemFileMeta,
  SystemMetaVersion,
  SystemSprintStatus,
  SprintRegistry,
  SprintProgress,
  SprintReport,
} from "./system";
