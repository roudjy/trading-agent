import type { CSSProperties, ReactNode } from "react";

export type PixelCardVariant =
  | ""
  | "brick"
  | "coin"
  | "grass"
  | "fire"
  | "stone"
  | "info"
  | "ink"
  | "panel2";

interface PixelCardProps {
  children?: ReactNode;
  variant?: PixelCardVariant;
  className?: string;
  style?: CSSProperties;
  header?: ReactNode;
  headerIcon?: ReactNode;
  headerRight?: ReactNode;
  padding?: boolean;
}

export function PixelCard({
  children,
  variant = "",
  className = "",
  style,
  header,
  headerIcon,
  headerRight,
  padding = true,
}: PixelCardProps) {
  const cls = [
    "pixel-card",
    variant ? `pixel-card--${variant}` : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} style={{ padding: padding ? undefined : 0, ...style }}>
      {header && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 12,
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {headerIcon}
            <span
              className="pxd"
              style={{ fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase" }}
            >
              {header}
            </span>
          </div>
          {headerRight}
        </div>
      )}
      {children}
    </div>
  );
}
