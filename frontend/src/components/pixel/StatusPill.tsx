import { Check, Dot, Warn, XMark } from "./Glyphs";

export type SystemStatus = "HEALTHY" | "WARNING" | "ERROR" | "IDLE";

interface StatusPillProps {
  status: SystemStatus | string;
}

const MAP: Record<string, { cls: string; icon: JSX.Element; label: string }> = {
  HEALTHY: { cls: "", icon: <Check size={12} />, label: "HEALTHY" },
  WARNING: { cls: "status-pill--warn", icon: <Warn size={12} />, label: "WARNING" },
  ERROR: { cls: "status-pill--err", icon: <XMark size={12} />, label: "ERROR" },
  IDLE: { cls: "status-pill--mute", icon: <Dot color="var(--stone-dark)" size={8} />, label: "IDLE" },
};

export function StatusPill({ status }: StatusPillProps) {
  const m = MAP[status] ?? MAP.IDLE;
  return (
    <span className={`status-pill ${m.cls}`}>
      <span className="pulse-dot">{m.icon}</span> {m.label}
    </span>
  );
}
