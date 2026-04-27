import { Check, Warn, XMark } from "./Glyphs";
import { PixelBadge } from "./PixelBadge";

export type FreshnessState = "fresh" | "stale" | "missing" | string;

interface FreshnessBadgeProps {
  state: FreshnessState;
}

export function FreshnessBadge({ state }: FreshnessBadgeProps) {
  if (state === "fresh") {
    return (
      <PixelBadge kind="ok" icon={<Check size={10} />}>
        FRESH
      </PixelBadge>
    );
  }
  if (state === "stale") {
    return (
      <PixelBadge kind="warn" icon={<Warn size={10} />}>
        STALE
      </PixelBadge>
    );
  }
  if (state === "missing") {
    return (
      <PixelBadge kind="err" icon={<XMark size={10} />}>
        MISSING
      </PixelBadge>
    );
  }
  return <PixelBadge kind="mute">{state}</PixelBadge>;
}

export type CampaignOutcome =
  | "no_signal"
  | "near_pass"
  | "failed"
  | "canceled"
  | "running"
  | string;

interface OutcomeBadgeProps {
  outcome: CampaignOutcome;
}

const OUTCOME_MAP: Record<string, { kind: "ok" | "info" | "err" | "warn" | "mute"; label: string }> =
  {
    no_signal: { kind: "info", label: "NO SIGNAL" },
    near_pass: { kind: "ok", label: "NEAR PASS" },
    failed: { kind: "err", label: "FAILED" },
    canceled: { kind: "mute", label: "CANCELED" },
    running: { kind: "warn", label: "RUNNING" },
  };

export function OutcomeBadge({ outcome }: OutcomeBadgeProps) {
  const m = OUTCOME_MAP[outcome] ?? { kind: "mute" as const, label: String(outcome).toUpperCase() };
  return <PixelBadge kind={m.kind}>{m.label}</PixelBadge>;
}

export type CampaignState = "completed" | "failed" | "canceled" | "running" | string;

interface StateBadgeProps {
  state: CampaignState;
}

const STATE_MAP: Record<string, { kind: "ok" | "err" | "mute" | "warn"; label: string }> = {
  completed: { kind: "ok", label: "COMPLETE" },
  failed: { kind: "err", label: "FAILED" },
  canceled: { kind: "mute", label: "CANCELED" },
  running: { kind: "warn", label: "RUNNING" },
};

export function StateBadge({ state }: StateBadgeProps) {
  const m = STATE_MAP[state] ?? { kind: "mute" as const, label: String(state).toUpperCase() };
  return <PixelBadge kind={m.kind}>{m.label}</PixelBadge>;
}
