// Common shapes shared across adapters. These mirror the data the
// design pages consume; adapters are responsible for filling them
// from real APIs and falling back to nulls / empty arrays so pages
// can render an EmptyStatePanel rather than crash.

export interface OverviewModel {
  systemStatus: "HEALTHY" | "WARNING" | "ERROR" | "IDLE";
  versionLabel: string | null;
  lastRunAgeMin: number | null;
  schedulerNextFireUtc: string | null;
  reportVerdict: string | null;
  reportPreset: string | null;
  reportNextExperiment: string | null;
  publicArtifactsStale: boolean | null;
  staleReason: string | null;
  intelligenceViability: string | null;
  intelligenceSummary: string | null;
  campaignsCompleted24h: number | null;
  campaignsFailed24h: number | null;
  campaignsCanceled24h: number | null;
  queueDepth: number | null;
  warnings: string[];
}

export interface SprintBreakdownItem {
  name: string;
  count: number;
}

export interface SprintModel {
  available: boolean;
  sprintId: string | null;
  profile: string | null;
  state: string | null;
  startedAtUtc: string | null;
  expectedCompletionUtc: string | null;
  daysRemaining: number | null;
  observedCampaigns: number | null;
  targetCampaigns: number | null;
  byPreset: SprintBreakdownItem[];
  byHypothesis: SprintBreakdownItem[];
  byOutcome: SprintBreakdownItem[];
}

export interface CampaignRow {
  campaignId: string;
  preset: string;
  hypothesisId: string | null;
  asset: string | null;
  timeframe: string | null;
  family: string | null;
  campaignType: string | null;
  state: string;
  outcome: string;
  failureReason: string | null;
  startedAtUtc: string | null;
  finishedAtUtc: string | null;
  runtimeMin: number | null;
}

export interface CampaignsModel {
  rows: CampaignRow[];
  completed24h: number | null;
  failed24h: number | null;
  canceled24h: number | null;
  queueDepth: number | null;
  workersBusy: number | null;
  workersTotal: number | null;
  runtimePerPreset: { name: string; avg_min: number }[];
}

export interface FailuresModel {
  total24h: number;
  byMode: { name: string; count: number }[];
  byPreset: { name: string; count: number }[];
  byFamily: { name: string; count: number }[];
  byAsset: { name: string; count: number }[];
  byTimeframe: { name: string; count: number }[];
  byScreeningPhase: { name: string; count: number }[];
  source: "evidence_ledger" | "intelligence_summary" | "empty";
}

export interface ArtifactRow {
  name: string;
  exists: boolean;
  ageMin: number | null;
  schema: string | null;
  state: "fresh" | "stale" | "missing";
  note: string | null;
  sizeBytes: number | null;
}

export interface ArtifactsModel {
  rows: ArtifactRow[];
  publicArtifactsStale: boolean | null;
  staleReason: string | null;
  totalFresh: number;
  totalStale: number;
  totalMissing: number;
}

export interface HealthModel {
  status: "HEALTHY" | "WARNING" | "ERROR" | "IDLE";
  version: string | null;
  lastRunAgeMin: number | null;
  schedulerNextFireUtc: string | null;
  warnings: string[];
  ledgerSummary: Record<string, number>;
  apiEndpoints: { path: string; status: number }[];
}

export interface VersionModel {
  fileVersion: string | null;
  backendVersion: string | null;
  dashboardVersion: string;
  gitHead: string | null;
  imageTag: string | null;
  host: string | null;
  container: string | null;
  versionFileMtime: number | null;
  drift: boolean;
  driftDetails: { check: string; ok: boolean }[];
}
