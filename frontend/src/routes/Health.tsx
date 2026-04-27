import { useEffect, useState } from "react";
import { loadHealthModel } from "../api/adapters/health";
import type { HealthModel } from "../api/adapters/types";
import { Chip, Coin, Heart, Star, Warn } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { StatTile } from "../components/pixel/PixelStat";
import { StatusPill } from "../components/pixel/StatusPill";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAge } from "../lib/time";

export function Health() {
  const [model, setModel] = useState<HealthModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadHealthModel();
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
        title="Health unavailable"
        message={`Failed to load health surface: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading service health..."
        icon={<Heart size={36} />}
      />
    );
  }

  const ledgerEntries = Object.entries(model.ledgerSummary);

  return (
    <div>
      <PixelSectionHeader
        title="System Health"
        icon={<Heart size={20} />}
        right={<StatusPill status={model.status} />}
      />

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        <StatTile
          label="Service"
          value={model.status}
          sub={model.version ? `v${model.version}` : "—"}
          icon={<Heart size={20} />}
          tone={
            model.status === "HEALTHY"
              ? "var(--grass-dark)"
              : model.status === "ERROR"
              ? "var(--brick)"
              : "var(--stone-dark)"
          }
        />
        <StatTile
          label="Last Run"
          value={fmtAge(model.lastRunAgeMin)}
          sub="since most recent run"
          icon={<Star size={20} />}
        />
        <StatTile
          label="Next Scheduled"
          value={
            model.schedulerNextFireUtc
              ? new Date(model.schedulerNextFireUtc).toLocaleString()
              : "—"
          }
          sub="UTC scheduler fire"
          icon={<Coin size={20} />}
        />
        <StatTile
          label="Ledger Events"
          value={ledgerEntries.length}
          sub="distinct ledger keys"
          icon={<Chip size={20} />}
        />
      </div>

      <div className="grid-2" style={{ marginBottom: 18 }}>
        <PixelCard padding={false}>
          <div style={{ padding: "14px 18px", borderBottom: "4px solid var(--ink)" }}>
            <span className="pxd" style={{ fontSize: 11 }}>
              READ-ONLY API SURFACE
            </span>
          </div>
          <table className="pixel-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Method</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              {model.apiEndpoints.map((e) => (
                <tr key={e.path}>
                  <td className="mono" style={{ fontSize: 13 }}>
                    {e.path}
                  </td>
                  <td>
                    <PixelBadge kind="info">GET</PixelBadge>
                  </td>
                  <td className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                    read-only passthrough
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PixelCard>

        <PixelCard padding={false}>
          <div style={{ padding: "14px 18px", borderBottom: "4px solid var(--ink)" }}>
            <span className="pxd" style={{ fontSize: 11 }}>
              EVIDENCE LEDGER SUMMARY
            </span>
          </div>
          <table className="pixel-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {ledgerEntries.length === 0 ? (
                <tr>
                  <td colSpan={2} className="mono" style={{ color: "var(--ink-muted)" }}>
                    no ledger entries reported
                  </td>
                </tr>
              ) : (
                ledgerEntries.map(([k, v]) => (
                  <tr key={k}>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {k}
                    </td>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {v}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </PixelCard>
      </div>

      {model.warnings.length > 0 && (
        <PixelCard variant="ink">
          <div
            className="pxd"
            style={{ fontSize: 10, color: "var(--coin)", marginBottom: 10, letterSpacing: 1.2 }}
          >
            ▸ WARNINGS
          </div>
          <div style={{ fontSize: 14, color: "var(--panel)", lineHeight: 1.7 }}>
            {model.warnings.map((w) => (
              <div key={w} className="mono">
                {w}
              </div>
            ))}
          </div>
        </PixelCard>
      )}
    </div>
  );
}
