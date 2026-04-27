export interface TickerItem {
  t: string;
  kind: string;
  msg: string;
}

interface TickerProps {
  items: TickerItem[];
}

const COLOR_MAP: Record<string, string> = {
  tick: "var(--grass)",
  campaign: "var(--coin)",
  spawn: "var(--info)",
  artifact: "var(--info)",
  sprint: "var(--coin)",
  warn: "var(--coin)",
  err: "var(--brick)",
  deploy: "var(--info)",
};

export function Ticker({ items }: TickerProps) {
  if (!items || items.length === 0) {
    return (
      <div className="ticker">
        <span className="ticker__item">
          <span className="ticker__sep">▸</span>
          <span style={{ color: "var(--ink-muted)" }}>no recent activity</span>
        </span>
      </div>
    );
  }
  return (
    <div className="ticker">
      {items.slice(0, 5).map((it, i) => (
        <span key={`${it.t}-${i}`} className="ticker__item">
          <span className="ticker__sep">▸</span>
          <span style={{ color: "var(--coin)" }}>{it.t}</span>
          <span style={{ color: COLOR_MAP[it.kind] ?? "var(--grass)" }}>
            [{it.kind}]
          </span>
          <span>{it.msg}</span>
        </span>
      ))}
    </div>
  );
}
