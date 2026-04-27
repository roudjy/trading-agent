import { useEffect, useState } from "react";
import type { ReactNode } from "react";

interface HBarProps {
  label: ReactNode;
  value: number;
  max: number;
  color?: "" | "coin" | "info" | "stone" | "grass";
  sub?: ReactNode;
}

export function HBar({ label, value, max, color = "", sub }: HBarProps) {
  const pct = max ? (value / max) * 100 : 0;
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(pct), 80);
    return () => clearTimeout(t);
  }, [pct]);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0" }}>
      <div style={{ width: 180, color: "var(--ink)" }}>
        <div className="mono" style={{ fontSize: 13, color: "var(--ink)" }}>
          {label}
        </div>
      </div>
      <div className="pixel-bar-track">
        <div
          className={`pixel-bar-fill ${color ? "pixel-bar-fill--" + color : ""}`}
          style={{ width: `${w}%` }}
        />
      </div>
      <div style={{ width: 80, textAlign: "right" }} className="pxd">
        <span style={{ fontSize: 11 }}>{value}</span>
        {sub && (
          <span style={{ fontSize: 9, color: "var(--ink-muted)", marginLeft: 6 }}>{sub}</span>
        )}
      </div>
    </div>
  );
}
