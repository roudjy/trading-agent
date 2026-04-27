import { api } from "../client";
import { numberOrNull } from "./index";
import type { CampaignsModel, CampaignRow } from "./types";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function rowFromRegistry(entry: Record<string, unknown>): CampaignRow | null {
  const id = asString(entry.campaign_id) ?? asString(entry.id);
  if (!id) return null;
  const preset = asString(entry.preset) ?? asString(entry.preset_name) ?? "";
  const state = asString(entry.state) ?? "running";
  const outcome = asString(entry.outcome) ?? "running";
  return {
    campaignId: id,
    preset,
    hypothesisId: asString(entry.hypothesis_id) ?? null,
    asset: asString(entry.asset) ?? null,
    timeframe: asString(entry.timeframe) ?? null,
    family: asString(entry.family) ?? null,
    campaignType: asString(entry.campaign_type) ?? null,
    state,
    outcome,
    failureReason: asString(entry.failure_reason) ?? null,
    startedAtUtc: asString(entry.started_at_utc) ?? asString(entry.started_at) ?? null,
    finishedAtUtc:
      asString(entry.finished_at_utc) ?? asString(entry.finished_at) ?? null,
    runtimeMin: numberOrNull(entry.runtime_min),
  };
}

export function buildCampaignsModel(input: {
  registry: Record<string, unknown> | null;
  digest: Record<string, unknown> | null;
  queue: Record<string, unknown> | null;
}): CampaignsModel {
  const { registry, digest, queue } = input;
  const rows: CampaignRow[] = [];
  if (registry) {
    const campaigns = registry.campaigns;
    if (Array.isArray(campaigns)) {
      for (const entry of campaigns) {
        if (entry && typeof entry === "object") {
          const row = rowFromRegistry(entry as Record<string, unknown>);
          if (row) rows.push(row);
        }
      }
    } else if (campaigns && typeof campaigns === "object") {
      for (const value of Object.values(campaigns)) {
        if (value && typeof value === "object") {
          const row = rowFromRegistry(value as Record<string, unknown>);
          if (row) rows.push(row);
        }
      }
    }
  }
  rows.sort((a, b) => {
    const aTime = a.finishedAtUtc ? Date.parse(a.finishedAtUtc) : 0;
    const bTime = b.finishedAtUtc ? Date.parse(b.finishedAtUtc) : 0;
    return bTime - aTime;
  });
  const queueCount = (() => {
    if (!queue) return null;
    const q = queue.queue;
    if (Array.isArray(q)) return q.length;
    return numberOrNull((queue as Record<string, unknown>).queue_depth);
  })();
  return {
    rows: rows.slice(0, 10),
    completed24h: numberOrNull(digest?.["campaigns_completed_last_24h"]),
    failed24h: numberOrNull(digest?.["campaigns_failed_last_24h"]),
    canceled24h: numberOrNull(digest?.["campaigns_canceled_last_24h"]),
    queueDepth: queueCount,
    workersBusy: numberOrNull(digest?.["workers_busy"]),
    workersTotal: numberOrNull(digest?.["workers_total"]),
    runtimePerPreset: extractRuntimePerPreset(digest),
  };
}

function extractRuntimePerPreset(
  digest: Record<string, unknown> | null
): { name: string; avg_min: number }[] {
  if (!digest) return [];
  const raw = digest["runtime_per_preset"] ?? digest["per_preset_runtime_min"];
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => {
        if (entry && typeof entry === "object") {
          const rec = entry as Record<string, unknown>;
          const name = asString(rec.name) ?? asString(rec.preset);
          const avg = numberOrNull(rec.avg_min) ?? numberOrNull(rec.avg);
          if (name && avg != null) return { name, avg_min: avg };
        }
        return null;
      })
      .filter((x): x is { name: string; avg_min: number } => x !== null);
  }
  return [];
}

export async function loadCampaignsModel(): Promise<CampaignsModel> {
  const [registry, digest, queue] = await Promise.all([
    api.campaignRegistry().catch(() => null),
    api.campaignDigest().catch(() => null),
    api.campaignQueue().catch(() => null),
  ]);
  return buildCampaignsModel({ registry, digest, queue });
}
