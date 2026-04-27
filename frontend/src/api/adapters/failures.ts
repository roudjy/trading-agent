import { api } from "../client";
import type { FailuresModel } from "./types";
import type { ResearchIntelligenceSummary } from "../client";

interface CountItem {
  name: string;
  count: number;
}

function fromLedgerSummary(
  intel: ResearchIntelligenceSummary | null
): CountItem[] {
  if (!intel) return [];
  const entries = Object.entries(intel.ledger_summary ?? {});
  return entries
    .filter(([k]) => k.startsWith("failure_") || k === "campaign_count")
    .map(([k, v]) => ({ name: k, count: typeof v === "number" ? v : 0 }))
    .filter((x) => x.count > 0);
}

function bucketise(events: Record<string, unknown>[], field: string): CountItem[] {
  const counts = new Map<string, number>();
  for (const ev of events) {
    const v = ev[field];
    if (typeof v === "string" && v.length > 0) {
      counts.set(v, (counts.get(v) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function buildFailuresModel(input: {
  evidence: Record<string, unknown> | null;
  intelligence: ResearchIntelligenceSummary | null;
}): FailuresModel {
  const { evidence, intelligence } = input;
  const eventsRaw = evidence?.events;
  const events: Record<string, unknown>[] = Array.isArray(eventsRaw)
    ? (eventsRaw.filter(
        (e) => e && typeof e === "object" && (e as Record<string, unknown>).outcome === "failed"
      ) as Record<string, unknown>[])
    : [];

  if (events.length === 0) {
    const fallback = fromLedgerSummary(intelligence);
    if (fallback.length === 0) {
      return {
        total24h: 0,
        byMode: [],
        byPreset: [],
        byFamily: [],
        byAsset: [],
        byTimeframe: [],
        byScreeningPhase: [],
        source: "empty",
      };
    }
    return {
      total24h: fallback.reduce((s, x) => s + x.count, 0),
      byMode: fallback,
      byPreset: [],
      byFamily: [],
      byAsset: [],
      byTimeframe: [],
      byScreeningPhase: [],
      source: "intelligence_summary",
    };
  }

  return {
    total24h: events.length,
    byMode: bucketise(events, "failure_reason"),
    byPreset: bucketise(events, "preset_name"),
    byFamily: bucketise(events, "family"),
    byAsset: bucketise(events, "asset"),
    byTimeframe: bucketise(events, "timeframe"),
    byScreeningPhase: bucketise(events, "screening_phase"),
    source: "evidence_ledger",
  };
}

export async function loadFailuresModel(): Promise<FailuresModel> {
  const [evidence, intelligence] = await Promise.all([
    api.campaignEvidence().catch(() => null),
    api.researchIntelligenceSummary().catch(() => null),
  ]);
  return buildFailuresModel({ evidence, intelligence });
}
