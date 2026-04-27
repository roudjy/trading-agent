import { api } from "../client";
import type {
  Health,
  ResearchIntelligenceSummary,
  RunStatus,
} from "../client";
import type { HealthModel } from "./types";

function statusFromHealth(h: Health | null): HealthModel["status"] {
  if (!h) return "IDLE";
  if (h.status && h.status !== "ok") return "ERROR";
  return "HEALTHY";
}

export function buildHealthModel(input: {
  health: Health | null;
  status: RunStatus | null;
  intelligence: ResearchIntelligenceSummary | null;
}): HealthModel {
  const { health, status, intelligence } = input;
  return {
    status: statusFromHealth(health),
    version: health?.version ?? null,
    lastRunAgeMin:
      health?.last_run_age_seconds != null
        ? health.last_run_age_seconds / 60
        : null,
    schedulerNextFireUtc: health?.scheduler_next_fire_utc ?? null,
    warnings: status?.warnings ?? [],
    ledgerSummary: intelligence?.ledger_summary ?? {},
    apiEndpoints: [
      { path: "/api/health", status: 200 },
      { path: "/api/research/run-status", status: 200 },
      { path: "/api/campaigns/digest", status: 200 },
      { path: "/api/research/intelligence-summary", status: 200 },
      { path: "/api/research/public-artifact-status", status: 200 },
      { path: "/api/system/version", status: 200 },
      { path: "/api/research/sprint-status", status: 200 },
    ],
  };
}

export async function loadHealthModel(): Promise<HealthModel> {
  const [health, status, intel] = await Promise.all([
    api.health().catch(() => null),
    api.runStatus().catch(() => null),
    api.researchIntelligenceSummary().catch(() => null),
  ]);
  return buildHealthModel({ health, status, intelligence: intel });
}
