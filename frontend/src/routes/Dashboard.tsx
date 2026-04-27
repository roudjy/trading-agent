import { useEffect, useState } from "react";
import { loadOverview } from "../api/adapters";
import type { OverviewModel } from "../api/adapters/types";
import {
  Block,
  Check,
  Chip,
  Coin,
  Flag,
  Heart,
  Pipe,
  Star,
  Warn,
} from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { StatTile } from "../components/pixel/PixelStat";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAge } from "../lib/time";

const TONE: Record<string, string> = {
  HEALTHY: "var(--grass)",
  WARNING: "var(--fire)",
  ERROR: "var(--brick)",
  IDLE: "var(--stone-dark)",
};

export function Dashboard() {
  const [model, setModel] = useState<OverviewModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadOverview();
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
        title="Overview unavailable"
        message={`Failed to load overview data: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Fetching service status..."
        icon={<Block size={36} />}
      />
    );
  }

  const tone = TONE[model.systemStatus] ?? "var(--stone-dark)";

  return (
    <div>
      <PixelSectionHeader
        title="Mission Status"
        icon={<Block size={20} />}
        right={
          <>
            <PixelBadge kind="ink" icon={<Coin size={10} />}>
              VERDICT · {model.reportVerdict ?? "—"}
            </PixelBadge>
            {model.systemStatus === "HEALTHY" ? (
              <PixelBadge kind="ok" icon={<Check size={10} />}>
                API OK
              </PixelBadge>
            ) : (
              <PixelBadge kind="warn" icon={<Warn size={10} />}>
                CHECK API
              </PixelBadge>
            )}
          </>
        }
      />

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        <StatTile
          label="System"
          value={model.systemStatus}
          sub={
            model.versionLabel
              ? `service v${model.versionLabel}`
              : "service version unknown"
          }
          icon={<Heart size={20} />}
          tone={tone}
          footer={
            <div style={{ fontSize: 14 }}>
              last run ·{" "}
              <span className="mono">{fmtAge(model.lastRunAgeMin)} ago</span>
            </div>
          }
        />
        <StatTile
          label="Latest Verdict"
          value={model.reportVerdict ?? "—"}
          sub={
            model.reportPreset
              ? `preset · ${model.reportPreset}`
              : "no preset reported"
          }
          icon={<Star size={20} />}
        />
        <StatTile
          label="Campaigns · 24H"
          value={model.campaignsCompleted24h ?? "—"}
          sub={`${model.campaignsFailed24h ?? 0} failed · ${
            model.campaignsCanceled24h ?? 0
          } canceled`}
          icon={<Pipe size={20} />}
          footer={
            <div style={{ display: "flex", gap: 6 }}>
              {model.queueDepth != null && (
                <PixelBadge kind="info">QUEUE {model.queueDepth}</PixelBadge>
              )}
            </div>
          }
        />
        <StatTile
          label="Public Artifacts"
          value={
            model.publicArtifactsStale === true
              ? "STALE"
              : model.publicArtifactsStale === false
              ? "FRESH"
              : "UNKNOWN"
          }
          sub={model.staleReason ?? "research_latest.json + strategy_matrix.csv"}
          icon={<Chip size={20} />}
          tone={
            model.publicArtifactsStale === true
              ? "var(--fire)"
              : model.publicArtifactsStale === false
              ? "var(--grass)"
              : "var(--stone-dark)"
          }
        />
      </div>

      <div className="grid-2" style={{ marginBottom: 18 }}>
        <PixelCard>
          <div
            className="pixel-stat-label"
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Flag size={14} /> Discovery Sprint Snapshot
          </div>
          <div style={{ marginTop: 8 }}>
            <div className="mono" style={{ fontSize: 14 }}>
              Open the <strong>Discovery Sprint</strong> page to inspect
              the active sprint and its breakdowns. The orchestrator
              writes the sprint registry artifact; this UI is read-only.
            </div>
          </div>
        </PixelCard>
        <PixelCard>
          <div
            className="pixel-stat-label"
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Star size={14} /> Latest Research Verdict
          </div>
          {model.reportVerdict ? (
            <div style={{ marginTop: 8 }}>
              <div className="pxd" style={{ fontSize: 14, marginBottom: 6 }}>
                {model.reportVerdict.toUpperCase()}
              </div>
              <div
                className="mono"
                style={{ fontSize: 13, color: "var(--ink-muted)", wordBreak: "break-word" }}
              >
                next experiment · {model.reportNextExperiment ?? "—"}
              </div>
            </div>
          ) : (
            <div style={{ color: "var(--ink-muted)", marginTop: 10 }}>
              No report generated yet.
            </div>
          )}
        </PixelCard>
      </div>

      {model.warnings.length > 0 && (
        <PixelCard variant="panel2">
          <div
            className="pixel-stat-label"
            style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}
          >
            <Warn size={14} /> Warnings
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {model.warnings.map((w) => (
              <li key={w} className="mono" style={{ fontSize: 13 }}>
                {w}
              </li>
            ))}
          </ul>
        </PixelCard>
      )}

      {model.intelligenceSummary && (
        <PixelCard variant="ink" style={{ marginTop: 18 }}>
          <div
            className="pxd"
            style={{ fontSize: 10, color: "var(--coin)", marginBottom: 8, letterSpacing: 1.2 }}
          >
            ▸ INTELLIGENCE SUMMARY · advisory only
          </div>
          <div className="mono" style={{ fontSize: 13, color: "var(--panel)" }}>
            {model.intelligenceSummary}
          </div>
        </PixelCard>
      )}
    </div>
  );
}
