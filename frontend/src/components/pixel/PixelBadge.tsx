import type { ReactNode } from "react";

export type PixelBadgeKind = "ok" | "warn" | "err" | "info" | "mute" | "ink" | "fire" | "coin";

interface PixelBadgeProps {
  children?: ReactNode;
  kind?: PixelBadgeKind;
  icon?: ReactNode;
}

export function PixelBadge({ children, kind = "mute", icon }: PixelBadgeProps) {
  return (
    <span className={`pixel-badge pixel-badge--${kind}`}>
      {icon}
      {children}
    </span>
  );
}
