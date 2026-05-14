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
  approval_policy?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      module_version?: string;
      schema_version?: number;
      decision_count?: number;
      approval_category_count?: number;
      high_or_unknown_is_executable?: boolean;
      execute_safe_requires_dependabot_low_or_medium?: boolean;
      execute_safe_requires_two_layer_opt_in?: boolean;
    };
  };
  autonomy_metrics?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      module_version?: string;
      metrics_version?: string;
      generated_at_utc?: string;
      final_recommendation?: string;
      safe_to_execute?: boolean;
      throughput_summary?: {
        proposals_total?: number;
        inbox_items_total?: number;
        pr_lifecycle_prs_seen?: number;
        recurring_jobs_total?: number;
        runtime_sources_total?: number;
      };
      operator_burden_summary?: {
        needs_human_total?: number;
        blocked_total?: number;
        estimated_operator_actions_total?: number;
      };
      reliability_summary?: {
        runtime_consecutive_failures?: number;
        missing_artifact_count?: number;
        malformed_artifact_count?: number;
      };
      safety_summary?: {
        high_or_unknown_executable_count?: number;
        summary?: string;
      };
    };
  };
  roadmap_protocol?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      module_version?: string;
      schema_version?: number;
      generated_at_utc?: string;
      item_id?: string;
      title?: string;
      item_type?: string;
      risk_class?: string;
      decision?: string;
      status_field?: string;
      implementation_allowed?: boolean;
      executable?: boolean;
      safe_to_execute?: boolean;
      blocked_reason?: string | null;
      proposed_release_id?: string;
      proposed_branch?: string;
    };
  };
  // v3.15.16.9b — Loop closure subsection on the Status card.
  // Surfaces whether the v3.15.16.8 detection -> v3.15.16.9 templating
  // -> operator-PR -> loop-closure cycle has completed. Bounded
  // payload only: counts, top blocking_component, top branch_name,
  // last_refreshed_utc, loop_state. NEVER carries proposed_patch
  // body, pr_body, full events / templates lists.
  //
  // v3.15.16.9c — ``roadmap_priority_wiring`` rides at the envelope
  // level (sibling of ``status`` / ``reason`` / ``data``) so the
  // operator sees the canonical bootstrap event proof independently
  // of the aggregate ``loop_state``. Closed vocabulary on
  // ``state`` and (when ``state == "not_available"``) ``reason``.
  loop_closure?: {
    status: "ok" | "not_available";
    reason?: string;
    data?: {
      loop_state: "open" | "resolved" | "stale";
      human_needed: {
        events_total: number;
        by_reason: Record<string, number>;
        top_blocking_component: string | null;
        generated_at_utc: string;
      };
      governance_bootstrap: {
        templates_total: number;
        top_branch_name: string | null;
        generated_at_utc: string;
      };
      approval_inbox: {
        human_needed_derived_rows: number;
        generated_at_utc: string;
      };
      last_refreshed_utc: string;
    };
    roadmap_priority_wiring?: {
      state: "open" | "resolved" | "not_available";
      reason: string | null;
      event_id: string | null;
      blocking_component: string | null;
      source_reason: string | null;
      template_branch: string | null;
      inbox_row_present: boolean;
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

// v3.15.16.5 — read-only Next-Up surface backed by
// reporting.roadmap_priority's chosen_next_up projection.
// Strictly bounded subset of logs/roadmap_priority/latest.json;
// the full candidates / filtered_out arrays stay in the file. The
// PWA card surfaces the chosen item, recommendation pill,
// rationale, protocol plan summary, backlog counts, and a derived
// needs_human boolean. No mutation surface; no action verbs.
export interface AgentControlNextUp {
  kind: "agent_control_next_up";
  schema_version: number;
  status: "ok" | "not_available";
  reason?: string;
  data?: {
    module_version?: string;
    generated_at_utc?: string;
    final_recommendation: string;
    safe_to_execute: boolean;
    chosen_next_up: {
      proposal_id?: string;
      title?: string;
      summary?: string;
      proposal_type?: string;
      risk_class?: string;
      rationale?: string;
      protocol_plan_summary?: {
        decision?: string;
        implementation_allowed?: boolean;
        requires_human?: boolean;
        risk_class?: string;
        item_type?: string;
        proposed_branch?: string;
        proposed_release_id?: string;
        required_tests?: string[];
        expected_artifacts?: string[];
      };
    } | null;
    counts: {
      proposals_total?: number;
      eligible_total?: number;
      filtered_out_total?: number;
      filtered_out_by_reason?: Record<string, number>;
    };
    needs_human: boolean;
  };
  artifact_path?: string;
}

// v3.15.16.N5c — read-only N5a merge-recommendation surface.
// Closed-schema rows projected by reporting.development_merge_recommendation
// and surfaced via dashboard.api_merge_recommendation (UNWIRED → wired by
// PR #191). Every field is a bounded scalar (no PR body, no diff, no commit
// message). The PWA renders these as read-only; no merge / approve / reject /
// deploy verb is exposed in the UI, and the closed
// recommendation_action vocabulary uses ``recommend_human_*`` prefixes that
// are explicitly NOT the executable verbs themselves.
export interface AgentControlMergeRecommendationRow {
  recommendation_id: string;
  pr_number: number;
  head_sha: string;
  head_ref: string;
  base_ref: string;
  observer_classification: string;
  inbox_blocked_count: number;
  inbox_critical_count: number;
  inbox_needs_review_count: number;
  recommendation_action: string;
  recommendation_reason: string;
  evaluated_at: string;
}

export interface AgentControlMergeRecommendationList {
  kind: "agent_control_merge_recommendation_list";
  schema_version: number;
  module_version?: string;
  status: "ok" | "not_available";
  reason?: string;
  rows: AgentControlMergeRecommendationRow[];
  counts?: { rows?: number };
  generated_at_utc?: string;
  artifact_path?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
}

export interface AgentControlMergeRecommendationDetail {
  kind: "agent_control_merge_recommendation_detail";
  schema_version: number;
  module_version?: string;
  status:
    | "ok"
    | "not_available"
    | "not_found"
    | "invalid_recommendation_id";
  reason?: string;
  row?: AgentControlMergeRecommendationRow;
  generated_at_utc?: string;
  artifact_path?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
}

// v3.15.16.N5b.phase1 — read-only N5b Phase 1 dry-run merge-preflight
// surface. Closed-schema candidate rows projected by
// reporting.development_merge_preflight and surfaced via
// dashboard.api_merge_preflight (UNWIRED → wired by operator-applied
// two-line dashboard.py diff). Every field is a bounded scalar (no PR
// body, no diff, no commit message). The PWA renders these as
// read-only; the closed dry_run_verdict vocabulary uses ``would_*``
// prefixes that are explicitly NOT executable verbs. Live merge
// execution is N5b Phase 2/3/4 territory and is not implemented;
// every envelope mirrors the projector's discipline invariants
// (dry_run_only=true, live_merge_implemented=false,
// deploy_coupled=false, level6_enabled=false).
export interface AgentControlMergePreflightRow {
  preflight_id: string;
  recommendation_id: string;
  pr_number: number;
  expected_head_sha: string;
  observed_head_sha: string;
  base_ref: string;
  head_ref: string;
  merge_state: string;
  checks_state: string;
  recommendation_action: string;
  recommendation_reason: string;
  token_required_for_live: boolean;
  dry_run_verdict: string;
  live_merge_implemented: boolean;
  stop_conditions: string[];
  audit_note: string;
  generated_at_utc: string;
  evidence_freshness_seconds: number;
}

export interface AgentControlMergePreflightList {
  kind: "agent_control_merge_preflight_list";
  schema_version: number;
  module_version?: string;
  status: "ok" | "not_available";
  reason?: string;
  rows: AgentControlMergePreflightRow[];
  counts?: {
    rows?: number;
    by_dry_run_verdict?: Record<string, number>;
  };
  generated_at_utc?: string;
  artifact_path?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
  level6_enabled?: boolean;
  dry_run_only?: boolean;
  live_merge_implemented?: boolean;
  deploy_coupled?: boolean;
}

export interface AgentControlMergePreflightDetail {
  kind: "agent_control_merge_preflight_detail";
  schema_version: number;
  module_version?: string;
  status:
    | "ok"
    | "not_available"
    | "not_found"
    | "invalid_preflight_id";
  reason?: string;
  row?: AgentControlMergePreflightRow;
  generated_at_utc?: string;
  artifact_path?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
  level6_enabled?: boolean;
  dry_run_only?: boolean;
  live_merge_implemented?: boolean;
  deploy_coupled?: boolean;
}

// v3.15.16.N4c — read-only diagnostic surface over the already-wired
// N4b approval-token runtime gate. All three endpoints already live
// in dashboard.api_approval_token_gate; this client provides only
// the consumer-side typing and the bounded request bodies for the
// diagnostics UI. The verify body mirrors the operator's VPS Phase B
// smoke contract verbatim — including the ``expected_intent`` field,
// which the current backend silently ignores but which forward-
// compatibly binds the contract if the backend ever validates it.
// **Claim-only**: token verification performs NO approve / reject /
// merge / deploy action.
export interface AgentControlApprovalTokenStatus {
  kind: "approval_token_status";
  schema_version: number;
  module_version?: string;
  status: "ok" | "error";
  error?: string;
  reason?: string;
  is_configured?: boolean;
  current_kid?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
}

export interface AgentControlApprovalTokenMintBody {
  intent: string;
  event_id: string;
  evidence_hash: string;
}

export interface AgentControlApprovalTokenMintResponse {
  status: string;
  token?: string | null;
  kid?: string;
  intent?: string;
  event_id?: string;
  issued_at_utc?: string;
  expires_at_utc?: string;
  reason?: string;
  error?: string;
}

export interface AgentControlApprovalTokenVerifyBody {
  token: string;
  expected_intent: string;
  expected_event_id: string;
  expected_evidence_hash: string;
}

export interface AgentControlApprovalTokenVerifyResponse {
  status: string;
  outcome?: string;
  reason?: string;
  error?: string;
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

// N5c — merge-recommendation client: the N5a API returns well-formed
// envelopes even on 4xx (``not_found`` → 404, ``invalid_recommendation_id``
// → 400, ``not_available`` → 404). The shared ``getJson`` helper would
// collapse all of those to ``not_available``, hiding the API's
// closed-vocabulary status from the read-only PWA. This helper honours
// the JSON body on 4xx so the UI can render the precise state — still
// without any mutating verb on the wire.
async function getJsonEnvelope<T extends { status?: string }>(
  path: string,
): Promise<T> {
  try {
    const res = await fetch(path, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    let body: T | null = null;
    try {
      body = (await res.json()) as T;
    } catch {
      body = null;
    }
    if (body && typeof body === "object" && body.status) {
      return body;
    }
    return {
      status: "not_available",
      reason: res.ok ? "malformed" : `http_${res.status}`,
    } as unknown as T;
  } catch (err) {
    return {
      status: "not_available",
      reason: `fetch_error: ${(err as Error)?.name || "Error"}`,
    } as unknown as T;
  }
}

// v3.15.16.N4c — POST envelope helper that honours the body even
// on non-2xx. The N4b verify endpoint returns HTTP 400 for the
// closed outcomes ``replay_detected`` and ``binding_mismatch``;
// without parsing the 4xx body, the diagnostic UI would collapse
// those into a generic "rejected" state and lose the operator's
// ability to distinguish them. Same shape as ``getJsonEnvelope``
// but for POST with a JSON body. Never logs / never echoes secrets.
async function postJsonEnvelope<T extends { status?: string }>(
  path: string,
  body: unknown,
): Promise<T> {
  try {
    const res = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    let parsed: T | null = null;
    try {
      parsed = (await res.json()) as T;
    } catch {
      parsed = null;
    }
    if (parsed && typeof parsed === "object" && parsed.status) {
      return parsed;
    }
    return {
      status: "error",
      reason: res.ok ? "malformed" : `http_${res.status}`,
    } as unknown as T;
  } catch (err) {
    return {
      status: "error",
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
  nextUp: () => getJson<AgentControlNextUp>(`${BASE}/next-up`),
  mergeRecommendationList: () =>
    getJsonEnvelope<AgentControlMergeRecommendationList>(
      `${BASE}/merge-recommendation/list`,
    ),
  mergeRecommendationDetail: (recommendationId: string) =>
    getJsonEnvelope<AgentControlMergeRecommendationDetail>(
      `${BASE}/merge-recommendation/detail/${encodeURIComponent(
        recommendationId,
      )}`,
    ),
  // v3.15.16.N5b.phase1 — read-only N5b Phase 1 merge-preflight
  // client. Mirrors the N5c merge-recommendation pattern (both are
  // closed-vocabulary GET-only surfaces). The same getJsonEnvelope
  // helper honours 4xx bodies so the UI can render the precise
  // closed status (``not_found`` / ``invalid_preflight_id`` /
  // ``not_available``) instead of a generic fetch failure.
  mergePreflightList: () =>
    getJsonEnvelope<AgentControlMergePreflightList>(
      `${BASE}/merge-preflight/list`,
    ),
  mergePreflightDetail: (preflightId: string) =>
    getJsonEnvelope<AgentControlMergePreflightDetail>(
      `${BASE}/merge-preflight/detail/${encodeURIComponent(preflightId)}`,
    ),
  approvalTokenStatus: () =>
    getJsonEnvelope<AgentControlApprovalTokenStatus>(
      `${BASE}/approval-token/status`,
    ),
  approvalTokenMint: (body: AgentControlApprovalTokenMintBody) =>
    postJsonEnvelope<AgentControlApprovalTokenMintResponse>(
      `${BASE}/approval-token/mint`,
      body,
    ),
  approvalTokenVerify: (body: AgentControlApprovalTokenVerifyBody) =>
    postJsonEnvelope<AgentControlApprovalTokenVerifyResponse>(
      `${BASE}/approval-token/verify`,
      body,
    ),
  // =====================================================================
  // v3.15.16.A15.B2.0d — Agent Activity Center read-only client.
  //
  // All six endpoints under /api/agent-control/activity/* are GET-only
  // and use the same getJsonEnvelope helper as merge-recommendation /
  // merge-preflight so closed-vocab error codes (invalid_enum /
  // invalid_format / not_in_last_snapshot / aggregator_missing) pass
  // through with their HTTP status preserved.
  //
  // No POST / PUT / PATCH / DELETE. No XMLHttpRequest. No sendBeacon.
  // No push subscription. No backend write side-effect.
  // =====================================================================
  activityToday: () =>
    getJsonEnvelope<ActivityTodayEnvelope>(
      `${ACTIVITY_BASE}/today`,
    ),
  activityItemsList: (params?: ActivityItemsListParams) =>
    getJsonEnvelope<ActivityItemsListEnvelope>(
      `${ACTIVITY_BASE}/items${activityQs(params)}`,
    ),
  activityItemsDetail: (itemId: string) =>
    getJsonEnvelope<ActivityItemsDetailEnvelope>(
      `${ACTIVITY_BASE}/items/${encodeURIComponent(
        boundedActivityItemId(itemId),
      )}`,
    ),
  activityAgents: () =>
    getJsonEnvelope<ActivityAgentsEnvelope>(
      `${ACTIVITY_BASE}/agents`,
    ),
  activityArtifacts: () =>
    getJsonEnvelope<ActivityArtifactsEnvelope>(
      `${ACTIVITY_BASE}/artifacts`,
    ),
  activityInvariants: () =>
    getJsonEnvelope<ActivityInvariantsEnvelope>(
      `${ACTIVITY_BASE}/invariants`,
    ),
};

// =========================================================================
// v3.15.16.A15.B2.0d — Agent Activity Center read-only client types
//
// Closed-vocabulary unions and envelope shapes for the six AAC endpoints,
// mirroring docs/governance/agent_activity_center_aggregator_schema.md
// (§6-§10) and docs/governance/agent_activity_center_api_contract.md
// (§3).
// =========================================================================

const ACTIVITY_BASE = "/api/agent-control/activity";
const MAX_ACTIVITY_ITEM_ID_LEN = 128;

function boundedActivityItemId(raw: string): string {
  if (typeof raw !== "string") return "";
  const safe = raw.replace(/[^A-Za-z0-9_.\-]/g, "");
  return safe.slice(0, MAX_ACTIVITY_ITEM_ID_LEN);
}

const _ACTIVITY_QS_ALLOWED = [
  "stage",
  "owner_role",
  "human_needed",
  "updated_since",
] as const;

function activityQs(p?: ActivityItemsListParams): string {
  if (!p) return "";
  const parts: string[] = [];
  for (const key of _ACTIVITY_QS_ALLOWED) {
    const value = p[key];
    if (value === undefined || value === null) continue;
    if (value === "") continue;
    parts.push(
      `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`,
    );
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export type ActivityStage =
  | "discovered"
  | "queued"
  | "delegated"
  | "planned"
  | "dry_run_ready"
  | "pr_proposed"
  | "pr_opened"
  | "ci_feedback"
  | "needs_human"
  | "merge_candidate"
  | "done_blocked";

export type ActivitySeverity = "info" | "warn" | "human" | "error";

export type ActivityRisk = "low" | "medium" | "high" | "critical";

export type ActivityFreshnessState =
  | "fresh"
  | "stale"
  | "missing"
  | "malformed";

export type ActivityInvariantTone =
  | "on"
  | "off"
  | "danger_off"
  | "info"
  | "unknown";

export type ActivityArtifactGroup =
  | "queue"
  | "loops"
  | "step5"
  | "gates"
  | "generated"
  | "digest"
  | "seed";

export interface ActivityWorkItem {
  item_id: string;
  title: string;
  source_kind: string;
  source_path: string;
  current_stage: ActivityStage;
  owner_role: string;
  risk: ActivityRisk;
  human_needed: boolean;
  latest_verdict: string;
  next_action: string;
  updated_at: string;
  summary: string;
  event_ids?: string[];
}

export interface ActivityAgentEvent {
  event_id: string;
  item_id: string;
  timestamp: string;
  agent_role: string;
  module: string;
  event_type: string;
  summary: string;
  decision: string;
  reason: string;
  artifact_path: string;
  severity: ActivitySeverity;
}

export interface ActivityHumanAction {
  action_id: string;
  item_id: string;
  severity: string;
  title: string;
  why_required: string;
  required_phrase: string | null;
  safe_to_ignore: boolean;
  copy_only: boolean;
  source_artifact_path: string;
  suggested_role: string;
  created_at: string;
}

export interface ActivityArtifactHealth {
  path: string;
  group: ActivityArtifactGroup;
  fresh: boolean;
  parse_ok: boolean;
  row_count: number;
  last_modified: string;
  module_version: string;
  has_summary: boolean;
  parse_error?: string;
  read_only_warning?: string;
}

export interface ActivityInvariantStatus {
  key: string;
  label: string;
  value: boolean | string;
  tone: ActivityInvariantTone;
  detail: string;
}

export interface ActivityFreshness {
  generated_at_utc?: string;
  oldest_artifact_age_seconds?: number;
  any_stale?: boolean;
  any_malformed?: boolean;
  background_refreshing?: boolean;
  ttl_seconds_by_path?: Record<string, number>;
}

export interface ActivityCounts {
  discovered?: number;
  queued?: number;
  delegated?: number;
  planned?: number;
  dry_run_ready?: number;
  pr_proposed?: number;
  pr_opened?: number;
  ci_feedback?: number;
  needs_human?: number;
  merge_candidate?: number;
  blocked?: number;
  total_open?: number;
}

interface _ActivityEnvelopeBase {
  kind: string;
  schema_version: number;
  module_version: string;
  status: string;
  reason?: string;
  generated_at_utc?: string;
  artifact_path?: string;
  step5_implementation_allowed?: boolean;
  step5_enabled_substage?: string;
  level6_enabled?: boolean;
}

export interface ActivityTodayEnvelope extends _ActivityEnvelopeBase {
  counts?: ActivityCounts;
  needs_human?: ActivityWorkItem[];
  merge_candidate?: ActivityWorkItem[];
  ci_feedback?: ActivityWorkItem[];
  blocked?: ActivityWorkItem[];
  recent_events?: ActivityAgentEvent[];
  freshness?: ActivityFreshness;
  invariant_status?: ActivityInvariantStatus[];
  section_totals?: {
    needs_human?: { total_matching: number; truncated: boolean };
    merge_candidate?: { total_matching: number; truncated: boolean };
    ci_feedback?: { total_matching: number; truncated: boolean };
    blocked?: { total_matching: number; truncated: boolean };
  };
}

export interface ActivityItemsListParams {
  stage?: ActivityStage;
  owner_role?: string;
  human_needed?: boolean;
  updated_since?: string;
}

export interface ActivityItemsListEnvelope extends _ActivityEnvelopeBase {
  work_items?: ActivityWorkItem[];
  total_matching?: number;
  truncated?: boolean;
  freshness?: ActivityFreshness;
}

export interface ActivityItemsDetailEnvelope extends _ActivityEnvelopeBase {
  work_item?: ActivityWorkItem;
  agent_events?: ActivityAgentEvent[];
  human_actions?: ActivityHumanAction[];
  artefacts_referenced?: string[];
  error?: string;
  param?: string;
  value?: string;
  detail?: string;
}

export interface ActivityAgentMatrixRow {
  role: string;
  new: number;
  planned: number;
  blocked: number;
  needs_human: number;
  pr_ready: number;
  last_action: ActivityAgentEvent | null;
  total: number;
}

export interface ActivityAgentsEnvelope extends _ActivityEnvelopeBase {
  rows?: ActivityAgentMatrixRow[];
}

export interface ActivityArtifactsEnvelope extends _ActivityEnvelopeBase {
  artifact_health?: ActivityArtifactHealth[];
}

export interface ActivityInvariantsEnvelope extends _ActivityEnvelopeBase {
  invariant_status?: ActivityInvariantStatus[];
}
