import { api } from "../client";
import type { OverviewModel } from "./types";
import type {
  Health,
  PublicArtifactStatus,
  ReportPayload,
  ResearchIntelligenceSummary,
  RunStatus,
} from "../client";

function statusFromHealth(h: Health | null, stale: PublicArtifactStatus | null): OverviewModel["systemStatus"] {
  if (!h) return "IDLE";
  if (stale && stale.public_artifacts_stale === true) return "WARNING";
  if (h.status && h.status !== "ok") return "ERROR";
  return "HEALTHY";
}

export function buildOverviewModel(input: {
  health: Health | null;
  status: RunStatus | null;
  report: ReportPayload | null;
  publicArtifactStatus: PublicArtifactStatus | null;
  intelligence: ResearchIntelligenceSummary | null;
  campaignDigest: Record<string, unknown> | null;
}): OverviewModel {
  const { health, status, report, publicArtifactStatus, intelligence, campaignDigest } = input;
  const lastRunMin =
    health?.last_run_age_seconds != null
      ? health.last_run_age_seconds / 60
      : null;
  const digest = campaignDigest as Record<string, unknown> | null;
  const completed = numberOrNull(
    digest?.["campaigns_completed_last_24h"] ?? digest?.["completed_last_24h"]
  );
  const failed = numberOrNull(
    digest?.["campaigns_failed_last_24h"] ?? digest?.["failed_last_24h"]
  );
  const canceled = numberOrNull(
    digest?.["campaigns_canceled_last_24h"] ?? digest?.["canceled_last_24h"]
  );
  const queue = numberOrNull(digest?.["queue_depth"]);

  return {
    systemStatus: statusFromHealth(health, publicArtifactStatus),
    versionLabel: health?.version ?? null,
    lastRunAgeMin: lastRunMin,
    schedulerNextFireUtc: health?.scheduler_next_fire_utc ?? null,
    reportVerdict: report?.verdict ?? null,
    reportPreset: report?.preset ?? null,
    reportNextExperiment: report?.next_experiment ?? null,
    publicArtifactsStale: publicArtifactStatus?.public_artifacts_stale ?? null,
    staleReason: publicArtifactStatus?.stale_reason ?? null,
    intelligenceViability: intelligence?.viability?.status ?? null,
    intelligenceSummary: intelligence?.viability?.human_summary ?? null,
    campaignsCompleted24h: completed,
    campaignsFailed24h: failed,
    campaignsCanceled24h: canceled,
    queueDepth: queue,
    warnings: status?.warnings ?? [],
  };
}

function numberOrNull(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

export async function loadOverview(): Promise<OverviewModel> {
  const [health, status, reportRes, pas, intel, digest] = await Promise.all([
    api.health().catch(() => null),
    api.runStatus().catch(() => null),
    api.reportLatest().catch(() => ({ markdown: null, payload: null })),
    api.publicArtifactStatus().catch(() => null),
    api.researchIntelligenceSummary().catch(() => null),
    api.campaignDigest().catch(() => null),
  ]);
  return buildOverviewModel({
    health,
    status,
    report: reportRes?.payload ?? null,
    publicArtifactStatus: pas,
    intelligence: intel,
    campaignDigest: digest,
  });
}

export { numberOrNull };
