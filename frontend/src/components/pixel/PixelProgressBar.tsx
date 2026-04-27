import { useEffect, useState } from "react";

interface PixelProgressBarProps {
  value: number;
  max?: number;
  color?: "coin" | "grass" | "brick" | "info";
  label?: string;
  animate?: boolean;
}

export function PixelProgressBar({
  value,
  max = 100,
  color = "coin",
  label,
  animate = true,
}: PixelProgressBarProps) {
  const target = Math.min(100, Math.max(0, max ? (value / max) * 100 : 0));
  const [w, setW] = useState(animate ? 0 : target);
  useEffect(() => {
    if (!animate) {
      setW(target);
      return;
    }
    const t = setTimeout(() => setW(target), 60);
    return () => clearTimeout(t);
  }, [target, animate]);
  return (
    <div className="pixel-progress">
      <div
        className={`pixel-progress__fill pixel-progress__fill--${color}`}
        style={{ width: `${w}%` }}
      />
      {label && <span className="pixel-progress__label">{label}</span>}
    </div>
  );
}
