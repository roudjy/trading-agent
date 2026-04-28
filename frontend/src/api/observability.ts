// Typed shapes for the v3.15.15.3 observability endpoints.
// All endpoints share a single response envelope; payloads vary
// per component but every consumer can rely on the envelope being
// present and stable.

export type ObservabilityReadState =
  | "valid"
  | "absent"
  | "empty"
  | "invalid_json"
  | "unreadable";

export interface ObservabilityComponentEnvelope<P = unknown> {
  available: boolean;
  component: string;
  artifact_name: string;
  artifact_path: string;
  state: ObservabilityReadState;
  modified_at_unix: number | null;
  size_bytes: number | null;
  payload: P | null;
  error: string | null;
  // Present on deferred-component responses.
  deferred?: boolean;
  slug?: string;
}

// ---- artifact_health payload ----

export interface ArtifactHealthRow {
  artifact_name: string;
  path: string;
  exists: boolean;
  parse_ok: boolean;
  schema_version: string | null;
  generated_at_utc: string | null;
  modified_at_unix: number | null;
  age_seconds: number | null;
  stale: boolean;
  stale_reason: string | null;
  size_bytes: number | null;
  empty: boolean;
  linked_ids: Record<string, string | null>;
  parse_error_type: string | null;
  parse_error_message: string;
  contract_class: string;
}

export interface ArtifactHealthSummary {
  total: number;
  missing: number;
  corrupt: number;
  stale: number;
  fresh: number;
  empty: number;
  by_contract_class: Record<string, number>;
}

export interface ArtifactHealthPayload {
  schema_version: string;
  generated_at_utc: string;
  summary: ArtifactHealthSummary;
  artifacts: ArtifactHealthRow[];
}

// ---- failure_modes payload ----

export interface FailureCount {
  name: string;
  count: number;
}

export interface FailureModesPayload {
  schema_version: string;
  generated_at_utc: string;
  source: {
    registry_state: ObservabilityReadState | null;
    ledger_state: ObservabilityReadState | null;
    ledger_lines_consumed: number | null;
    ledger_truncated: boolean | null;
    ledger_partial_trailing_dropped: boolean | null;
    ledger_parse_errors: number | null;
    max_ledger_lines: number;
  };
  total_campaigns_observed: number;
  total_failure_events_observed: number;
  campaigns_by_outcome: FailureCount[];
  campaigns_by_outcome_class: Record<string, number>;
  top_failure_reasons: FailureCount[];
  by_preset: FailureCount[];
  by_hypothesis_id: FailureCount[];
  by_strategy_family: FailureCount[];
  by_asset: FailureCount[];
  by_timeframe: FailureCount[];
  by_campaign_type: FailureCount[];
  by_worker_id: FailureCount[];
  repeated_failure_clusters: {
    preset: string;
    failure_reason: string;
    count: number;
  }[];
  technical_vs_research_failure_counts: Record<string, number>;
  unknown_or_unclassified_count: number;
}

// ---- throughput payload ----

export interface ThroughputPayload {
  schema_version: string;
  generated_at_utc: string;
  window: { days: number; start_utc: string; end_utc: string };
  source: {
    registry_state: ObservabilityReadState | null;
    queue_state: ObservabilityReadState | null;
    digest_state: ObservabilityReadState | null;
    campaigns_observed_in_registry: number;
    campaigns_in_window: number;
  };
  campaigns_per_day: number;
  completed_campaigns_per_day: number;
  meaningful_campaigns_per_day: number;
  outcomes: Record<string, number>;
  success_rate: number | null;
  degenerate_rate: number | null;
  research_rejection_rate: number | null;
  technical_failure_rate: number | null;
  runtime_minutes: { count: number; p50: number; p95: number; avg: number | null };
  queue_wait_seconds: { count: number; p50: number; p95: number };
  workers: {
    busy: number | null;
    total: number | null;
    busy_rate: number | null;
    idle_rate: number | null;
  };
  queue: {
    depth: number | null;
    stale_lease_count: number | null;
    backpressure_flag: boolean | null;
  };
  running_count: number;
  canceled_count: number;
}

// ---- system_integrity payload ----

export interface SystemIntegrityPayload {
  schema_version: string;
  generated_at_utc: string;
  version_file: string | null;
  git: { head: string | null; branch: string | null; dirty: boolean | null };
  uptime_seconds: { process: number | null; container: number | null };
  disk_free_bytes: number | null;
  artifact_directory_writable: boolean;
  observability_dir: string;
  last_observability_artifact_update_unix: number | null;
  timezone: string | null;
  base_dir: string;
}

// ---- aggregator summary payload ----

export type ObservabilityComponentStatus =
  | "available"
  | "unavailable"
  | "corrupt"
  | "empty"
  | "deferred";

export type ObservabilityOverallStatus =
  | "healthy"
  | "degraded"
  | "insufficient_evidence"
  | "unknown";

export interface ObservabilitySummaryComponentRow {
  name: string;
  slug: string;
  status: ObservabilityComponentStatus;
  path: string | null;
  schema_version: string | null;
  generated_at_utc: string | null;
  modified_at_unix: number | null;
  size_bytes: number | null;
  error_message: string | null;
}

export interface ObservabilitySummaryPayload {
  schema_version: string;
  generated_at_utc: string;
  observation_window: {
    earliest_component_generated_at_utc: string | null;
    latest_component_generated_at_utc: string | null;
    inferred_from: string;
  };
  overall_status: ObservabilityOverallStatus;
  component_status_counts: Partial<Record<ObservabilityComponentStatus, number>>;
  components: ObservabilitySummaryComponentRow[];
  critical_findings: string[];
  warnings: string[];
  informational_findings: string[];
  recommended_next_human_action:
    | "none"
    | "inspect_artifacts"
    | "investigation_required"
    | "roadmap_decision_required";
  active_component_count: number;
  deferred_component_count: number;
}

// ---- index payload ----

export interface ObservabilityIndexComponent {
  component: string;
  slug: string;
  artifact_name: string;
  artifact_path: string;
  exists: boolean;
  size_bytes: number | null;
  modified_at_unix: number | null;
  deferred: boolean;
}

export interface ObservabilityIndexPayload {
  observability_dir: string;
  components: ObservabilityIndexComponent[];
  active_count: number;
  deferred_count: number;
}
