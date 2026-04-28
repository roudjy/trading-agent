import { useEffect, useState } from "react";
import { api } from "../api/client";
import { loadHealthModel } from "../api/adapters/health";
import type { HealthModel } from "../api/adapters/types";
import type {
  ObservabilityComponentEnvelope,
  SystemIntegrityPayload,
} from "../api/client";
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
  const [integrityEnvelope, setIntegrityEnvelope] = useState<
    ObservabilityComponentEnvelope<SystemIntegrityPayload> | null
  >(null);

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
    void (async () => {
      try {
        const i = await api.observabilitySystemIntegrity();
        if (!cancelled) setIntegrityEnvelope(i);
      } catch {
        if (!cancelled) setIntegrityEnvelope(null);
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

      <SystemIntegrityCard envelope={integrityEnvelope} />
    </div>
  );
}

function SystemIntegrityCard({
  envelope,
}: {
  envelope: ObservabilityComponentEnvelope<SystemIntegrityPayload> | null;
}) {
  if (!envelope) return null;
  if (!envelope.available || !envelope.payload) {
    return (
      <PixelCard variant="panel2" style={{ marginTop: 18 }}>
        <div
          className="pixel-stat-label"
          style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}
        >
          <Chip size={12} /> OBSERVABILITY · system_integrity artifact
        </div>
        <div className="mono" style={{ fontSize: 13 }}>
          The observability ``system_integrity`` artifact is{" "}
          <code>{envelope.state}</code>. Build it with{" "}
          <code>python -m research.diagnostics build</code> to enrich this page.
        </div>
      </PixelCard>
    );
  }
  const p = envelope.payload;
  return (
    <PixelCard variant="panel2" style={{ marginTop: 18 }}>
      <div
        className="pixel-stat-label"
        style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}
      >
        <Chip size={12} /> OBSERVABILITY · system integrity
      </div>
      <table className="pixel-table">
        <tbody>
          <tr>
            <td>VERSION file</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.version_file ?? "—"}
            </td>
          </tr>
          <tr>
            <td>git head / branch</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.git.head ?? "—"} / {p.git.branch ?? "—"}{" "}
              {p.git.dirty === true ? (
                <PixelBadge kind="warn">DIRTY</PixelBadge>
              ) : null}
            </td>
          </tr>
          <tr>
            <td>process / container uptime</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.uptime_seconds.process != null
                ? `${Math.round(p.uptime_seconds.process / 60)}m`
                : "—"}{" "}
              /{" "}
              {p.uptime_seconds.container != null
                ? `${Math.round(p.uptime_seconds.container / 60)}m`
                : "—"}
            </td>
          </tr>
          <tr>
            <td>disk free</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.disk_free_bytes != null
                ? `${(p.disk_free_bytes / 1024 / 1024 / 1024).toFixed(2)} GiB`
                : "—"}
            </td>
          </tr>
          <tr>
            <td>artifact dir writable</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.artifact_directory_writable ? (
                <PixelBadge kind="ok">YES</PixelBadge>
              ) : (
                <PixelBadge kind="err">NO</PixelBadge>
              )}
            </td>
          </tr>
        </tbody>
      </table>
    </PixelCard>
  );
}
