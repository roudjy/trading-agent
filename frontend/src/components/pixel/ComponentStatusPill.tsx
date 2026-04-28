import type { ObservabilityComponentStatus } from "../../api/client";
import { PixelBadge } from "./PixelBadge";

const MAP: Record<
  ObservabilityComponentStatus,
  { kind: "ok" | "warn" | "err" | "info" | "mute"; label: string }
> = {
  available: { kind: "ok", label: "AVAILABLE" },
  unavailable: { kind: "warn", label: "UNAVAILABLE" },
  corrupt: { kind: "err", label: "CORRUPT" },
  empty: { kind: "warn", label: "EMPTY" },
  deferred: { kind: "info", label: "DEFERRED" },
};

export function ComponentStatusPill({
  status,
}: {
  status: ObservabilityComponentStatus;
}) {
  const m = MAP[status] ?? { kind: "mute" as const, label: String(status).toUpperCase() };
  return <PixelBadge kind={m.kind}>{m.label}</PixelBadge>;
}
