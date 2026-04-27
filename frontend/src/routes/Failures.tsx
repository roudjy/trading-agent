import { useEffect, useMemo, useState } from "react";
import { loadFailuresModel } from "../api/adapters/failures";
import type { FailuresModel } from "../api/adapters/types";
import { Check, Chip, Pipe, Skull, Warn } from "../components/pixel/Glyphs";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { StatTile } from "../components/pixel/PixelStat";
import { HBar } from "../components/pixel/HBar";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";

interface SectionProps {
  title: string;
  items: { name: string; count: number }[];
  color?: "" | "coin" | "info" | "stone" | "grass";
  sortBy: "count" | "name";
}

function Section({ title, items, color = "", sortBy }: SectionProps) {
  if (items.length === 0) return null;
  const max = Math.max(...items.map((x) => x.count), 1);
  const sorted = [...items].sort((a, b) =>
    sortBy === "count" ? b.count - a.count : a.name.localeCompare(b.name)
  );
  return (
    <PixelCard>
      <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
        {title}
      </div>
      {sorted.map((p) => (
        <HBar key={p.name} label={p.name} value={p.count} max={max} color={color} />
      ))}
    </PixelCard>
  );
}

export function Failures() {
  const [model, setModel] = useState<FailuresModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"count" | "name">("count");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadFailuresModel();
        if (!cancelled) setModel(m);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const dominant = useMemo(() => {
    if (!model || model.byMode.length === 0) return null;
    return [...model.byMode].sort((a, b) => b.count - a.count)[0];
  }, [model]);

  const worstPreset = useMemo(() => {
    if (!model || model.byPreset.length === 0) return null;
    return [...model.byPreset].sort((a, b) => b.count - a.count)[0];
  }, [model]);

  if (error) {
    return (
      <EmptyStatePanel
        title="Failure data unavailable"
        message={`Failed to load evidence ledger: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading failure observations..."
        icon={<Skull size={36} />}
      />
    );
  }
  if (model.total24h === 0) {
    return (
      <div>
        <PixelSectionHeader title="Failure Modes" icon={<Skull size={20} />} />
        <EmptyStatePanel
          title="No Failures Recorded"
          message="No failure data available in the current observation window."
          icon={<Check size={36} />}
        />
      </div>
    );
  }

  return (
    <div>
      <PixelSectionHeader
        title="Failure Modes"
        icon={<Skull size={20} />}
        right={
          <>
            <button
              type="button"
              className={`pixel-btn ${sortBy === "count" ? "pixel-btn--active" : ""}`}
              onClick={() => setSortBy("count")}
            >
              by count
            </button>
            <button
              type="button"
              className={`pixel-btn ${sortBy === "name" ? "pixel-btn--active" : ""}`}
              onClick={() => setSortBy("name")}
            >
              by name
            </button>
          </>
        }
      />

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        <StatTile
          label="Total · 24H"
          value={model.total24h}
          sub="campaigns failed"
          icon={<Skull size={20} />}
          tone="var(--brick)"
        />
        {dominant && (
          <StatTile
            label="Dominant Mode"
            value={
              <span className="pxd" style={{ fontSize: 14 }}>
                {dominant.name}
              </span>
            }
            sub={`${dominant.count} observed`}
            icon={<Warn size={20} />}
            tone="var(--ink)"
          />
        )}
        <StatTile
          label="Distinct Modes"
          value={model.byMode.filter((x) => x.count > 0).length}
          sub={`of ${model.byMode.length} tracked`}
          icon={<Chip size={20} />}
        />
        {worstPreset && (
          <StatTile
            label="Worst Preset"
            value={
              <span className="pxd" style={{ fontSize: 14 }}>
                {worstPreset.name}
              </span>
            }
            sub={`${worstPreset.count} failures`}
            icon={<Pipe size={20} />}
          />
        )}
      </div>

      <PixelCard variant="ink" style={{ marginBottom: 18 }}>
        <div
          className="pxd"
          style={{ fontSize: 10, color: "var(--coin)", marginBottom: 8, letterSpacing: 1.2 }}
        >
          ▸ INTERPRETATION ONLY
        </div>
        <div className="mono" style={{ fontSize: 13, color: "var(--panel)" }}>
          This page displays observed failure counts. It does not recommend
          actions, classify strategies as good or bad, or suggest what should
          run next. Source · {model.source.replace("_", " ")}.
        </div>
      </PixelCard>

      <div className="grid-2" style={{ marginBottom: 18 }}>
        <Section title="BY FAILURE MODE" items={model.byMode} color="" sortBy={sortBy} />
        <Section title="BY PRESET" items={model.byPreset} color="info" sortBy={sortBy} />
      </div>
      <div className="grid-2" style={{ marginBottom: 18 }}>
        <Section title="BY STRATEGY FAMILY" items={model.byFamily} color="coin" sortBy={sortBy} />
        <Section title="BY ASSET" items={model.byAsset} color="stone" sortBy={sortBy} />
      </div>
      <div className="grid-2">
        <Section title="BY TIMEFRAME" items={model.byTimeframe} color="info" sortBy={sortBy} />
        <Section title="BY SCREENING PHASE" items={model.byScreeningPhase} color="" sortBy={sortBy} />
      </div>
    </div>
  );
}
