// Thin fetch wrapper for the Flask control-surface API.
// The frontend contains ZERO business logic — all data comes from /api/*.
// Session cookie is set by the Flask /api/session/login endpoint; this
// client always sends credentials so the cookie rides along.

export interface Health {
  status: string;
  version: string;
  last_run_age_seconds: number | null;
  scheduler_next_fire_utc: string | null;
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
  login: (username: string, password: string) =>
    request<{ ok: boolean; actor?: string; error?: string }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    request<{ ok: boolean }>("/api/session/logout", { method: "POST" }),
};

export { ApiError };
