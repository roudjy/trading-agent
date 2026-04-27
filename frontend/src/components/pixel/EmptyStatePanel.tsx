import type { ReactNode } from "react";
import { Block } from "./Glyphs";

interface EmptyStatePanelProps {
  title: ReactNode;
  message: ReactNode;
  icon?: ReactNode;
  hint?: ReactNode;
}

export function EmptyStatePanel({ title, message, icon, hint }: EmptyStatePanelProps) {
  return (
    <div
      className="pixel-card"
      style={{ background: "var(--panel-2)", textAlign: "center", padding: "34px 20px" }}
    >
      <div style={{ fontSize: 32, marginBottom: 12 }}>{icon ?? <Block size={32} />}</div>
      <div
        className="pxd"
        style={{
          fontSize: 12,
          marginBottom: 8,
          letterSpacing: 1.5,
          textTransform: "uppercase",
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 18, color: "var(--ink-muted)" }}>{message}</div>
      {hint !== false && (
        <div className="pxd blink" style={{ marginTop: 16 }}>
          <span
            className="pxd"
            style={{ fontSize: 9, color: "var(--ink-muted)", letterSpacing: 2 }}
          >
            {hint ?? "...AWAITING NEXT REFRESH..."}
          </span>
        </div>
      )}
    </div>
  );
}
