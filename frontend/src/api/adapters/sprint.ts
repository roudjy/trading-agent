import { api, type SystemSprintStatus } from "../client";
import type { SprintModel, SprintBreakdownItem } from "./types";

function asBreakdown(raw: unknown): SprintBreakdownItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (item && typeof item === "object") {
        const rec = item as Record<string, unknown>;
        const name =
          (typeof rec.name === "string" && rec.name) ||
          (typeof rec.preset === "string" && rec.preset) ||
          (typeof rec.preset_name === "string" && rec.preset_name) ||
          (typeof rec.hypothesis_id === "string" && rec.hypothesis_id) ||
          (typeof rec.outcome === "string" && rec.outcome) ||
          null;
        const count =
          typeof rec.count === "number"
            ? rec.count
            : typeof rec.observed === "number"
            ? rec.observed
            : null;
        if (name && count != null) return { name, count };
      }
      return null;
    })
    .filter((x): x is SprintBreakdownItem => x !== null);
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function daysBetween(startIso: string | null, endIso: string | null): number | null {
  if (!startIso || !endIso) return null;
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, Math.round((end - Date.now()) / (1000 * 60 * 60 * 24)));
}

export function buildSprintModel(status: SystemSprintStatus | null): SprintModel {
  if (!status || !status.available) {
    return {
      available: false,
      sprintId: null,
      profile: null,
      state: null,
      startedAtUtc: null,
      expectedCompletionUtc: null,
      daysRemaining: null,
      observedCampaigns: null,
      targetCampaigns: null,
      byPreset: [],
      byHypothesis: [],
      byOutcome: [],
    };
  }
  const reg = (status.registry ?? {}) as Record<string, unknown>;
  const prog = (status.progress ?? {}) as Record<string, unknown>;
  const sprintId = asString(reg.sprint_id);
  const profile = asString(reg.profile);
  const state = asString(reg.state) ?? asString(prog.state);
  const startedAt =
    asString(reg.started_at_utc) ??
    asString(reg.started_at) ??
    null;
  const expected =
    asString(reg.expected_completion_utc) ??
    asString(reg.expected_completion) ??
    null;
  return {
    available: true,
    sprintId,
    profile,
    state,
    startedAtUtc: startedAt,
    expectedCompletionUtc: expected,
    daysRemaining: daysBetween(startedAt, expected),
    observedCampaigns:
      asNumber(prog.observed_campaigns) ?? asNumber(prog.observed) ?? null,
    targetCampaigns:
      asNumber(reg.target_campaigns) ?? asNumber(prog.target_campaigns) ?? null,
    byPreset: asBreakdown(prog.by_preset),
    byHypothesis: asBreakdown(prog.by_hypothesis),
    byOutcome: asBreakdown(prog.by_outcome),
  };
}

export async function loadSprintModel(): Promise<SprintModel> {
  const status = await api.sprintStatus().catch(() => null);
  return buildSprintModel(status);
}
