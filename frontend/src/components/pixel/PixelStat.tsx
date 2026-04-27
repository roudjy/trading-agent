import type { ReactNode } from "react";

interface PixelStatProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  accent?: string;
}

export function PixelStat({ label, value, sub, icon, accent }: PixelStatProps) {
  return (
    <div>
      <div className="pixel-stat-label">{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {icon}
        <div className="pixel-stat-value" style={accent ? { color: accent } : undefined}>
          {value}
        </div>
      </div>
      {sub && <div className="pixel-stat-sub">{sub}</div>}
    </div>
  );
}

interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  variant?: "" | "brick" | "coin" | "grass" | "fire" | "stone" | "info" | "ink" | "panel2";
  tone?: string;
  footer?: ReactNode;
}

export function StatTile({
  label,
  value,
  sub,
  icon,
  variant = "",
  tone,
  footer,
}: StatTileProps) {
  const cls = ["pixel-card", variant ? `pixel-card--${variant}` : ""].filter(Boolean).join(" ");
  return (
    <div className={cls} style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 10,
        }}
      >
        <div className="pixel-stat-label">{label}</div>
        {icon}
      </div>
      <div className="pixel-stat-value" style={{ marginTop: 8, color: tone ?? "inherit" }}>
        {value}
      </div>
      {sub && <div className="pixel-stat-sub">{sub}</div>}
      {footer && (
        <div
          style={{
            marginTop: 10,
            paddingTop: 8,
            borderTop: "2px dashed currentColor",
            opacity: 0.85,
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
