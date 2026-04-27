import { useEffect, useState } from "react";
import { loadSprintModel } from "../api/adapters/sprint";
import type { SprintModel } from "../api/adapters/types";
import {
  Chip,
  Coin,
  Flag,
  Pipe,
  Star,
  Warn,
} from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelProgressBar } from "../components/pixel/PixelProgressBar";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { StatTile } from "../components/pixel/PixelStat";
import { HBar } from "../components/pixel/HBar";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAgo } from "../lib/time";

export function Sprint() {
  const [model, setModel] = useState<SprintModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadSprintModel();
        if (!cancelled) setModel(m);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <EmptyStatePanel
        title="Sprint status unavailable"
        message={`Failed to load sprint artifact: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading discovery sprint artifact..."
        icon={<Flag size={36} />}
      />
    );
  }
  if (!model.available) {
    return (
      <div>
        <PixelSectionHeader title="Discovery Sprint" icon={<Flag size={20} />} />
        <EmptyStatePanel
          title="No Active Sprint"
          message="The discovery engine is not currently running a sprint. Sprint definition is read-only here; check the operator console to start one."
          icon={<Flag size={36} />}
        />
      </div>
    );
  }

  const observed = model.observedCampaigns ?? 0;
  const target = model.targetCampaigns ?? 0;
  const pct = target ? Math.round((observed / target) * 100) : 0;
  const maxPreset = Math.max(...model.byPreset.map((x) => x.count), 1);
  const maxHypo = Math.max(...model.byHypothesis.map((x) => x.count), 1);
  const maxOut = Math.max(...model.byOutcome.map((x) => x.count), 1);

  return (
    <div>
      <PixelSectionHeader
        title="Discovery Sprint"
        icon={<Flag size={20} />}
        right={
          <PixelBadge
            kind={
              model.state === "ACTIVE" || model.state === "active"
                ? "ok"
                : model.state === "CANCELED" || model.state === "canceled"
                ? "err"
                : "mute"
            }
          >
            {model.state ?? "—"}
          </PixelBadge>
        }
      />

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        <StatTile
          label="Sprint ID"
          value={
            <span className="mono" style={{ fontSize: 14 }}>
              {model.sprintId ? model.sprintId.replace("sp_", "") : "—"}
            </span>
          }
          sub={model.profile ?? "—"}
          icon={<Chip size={20} />}
        />
        <StatTile
          label="Observed"
          value={`${observed}`}
          sub={`of ${target} target`}
          icon={<Pipe size={20} />}
          tone="var(--grass-dark)"
        />
        <StatTile
          label="Progress"
          value={`${pct}%`}
          sub="completion"
          icon={<Coin size={20} />}
          tone="var(--coin-dark)"
        />
        <StatTile
          label="Days remaining"
          value={model.daysRemaining ?? "—"}
          sub={`expected ${fmtAgo(model.expectedCompletionUtc)}`}
          icon={<Star size={20} />}
        />
      </div>

      <PixelCard variant="panel2" style={{ marginBottom: 18 }}>
        <div className="pixel-stat-label" style={{ marginBottom: 8 }}>
          Sprint Progress
        </div>
        <PixelProgressBar
          value={observed}
          max={target || 1}
          color="grass"
          label={`${pct}% · ${observed}/${target}`}
        />
        <div
          style={{
            display: "flex",
            gap: 18,
            marginTop: 12,
            fontSize: 14,
            color: "var(--ink-muted)",
            flexWrap: "wrap",
          }}
        >
          <span className="mono">started · {fmtAgo(model.startedAtUtc)}</span>
          <span className="mono">
            expected · {fmtAgo(model.expectedCompletionUtc)}
          </span>
        </div>
      </PixelCard>

      <div className="grid-3">
        <PixelCard>
          <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
            BY PRESET
          </div>
          {model.byPreset.length === 0 ? (
            <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
              no breakdown reported
            </div>
          ) : (
            model.byPreset.map((p) => (
              <HBar key={p.name} label={p.name} value={p.count} max={maxPreset} color="info" />
            ))
          )}
        </PixelCard>
        <PixelCard>
          <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
            BY HYPOTHESIS
          </div>
          {model.byHypothesis.length === 0 ? (
            <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
              no breakdown reported
            </div>
          ) : (
            model.byHypothesis.map((p) => (
              <HBar key={p.name} label={p.name} value={p.count} max={maxHypo} color="coin" />
            ))
          )}
        </PixelCard>
        <PixelCard>
          <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
            BY OUTCOME
          </div>
          {model.byOutcome.length === 0 ? (
            <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
              no breakdown reported
            </div>
          ) : (
            model.byOutcome.map((p) => {
              const colorMap: Record<
                string,
                "" | "coin" | "info" | "stone" | "grass"
              > = {
                no_signal: "info",
                near_pass: "grass",
                failed: "",
                canceled: "stone",
              };
              return (
                <HBar
                  key={p.name}
                  label={p.name}
                  value={p.count}
                  max={maxOut}
                  color={colorMap[p.name] ?? ""}
                />
              );
            })
          )}
        </PixelCard>
      </div>
    </div>
  );
}
