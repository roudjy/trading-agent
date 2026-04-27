import type { ReactNode } from "react";

interface PixelSectionHeaderProps {
  title: ReactNode;
  icon?: ReactNode;
  right?: ReactNode;
}

export function PixelSectionHeader({ title, icon, right }: PixelSectionHeaderProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        margin: "8px 0 14px",
        paddingBottom: 6,
        borderBottom: "4px dashed var(--ink)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {icon}
        <h2
          className="pxd"
          style={{
            fontSize: 14,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            margin: 0,
          }}
        >
          {title}
        </h2>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {right}
      </div>
    </div>
  );
}
