import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type {
  ObservabilityComponentEnvelope,
  ObservabilityIndexPayload,
  ObservabilitySummaryPayload,
} from "../api/client";
import { Block, Chip, Star, Warn } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { ComponentStatusPill } from "../components/pixel/ComponentStatusPill";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAge, fmtAgo } from "../lib/time";

function ageOf(modifiedAtUnix: number | null): string {
  if (modifiedAtUnix == null) return "—";
  const minutes = (Date.now() / 1000 - modifiedAtUnix) / 60;
  return fmtAge(minutes);
}

const OVERALL_TONE: Record<string, string> = {
  healthy: "var(--grass)",
  degraded: "var(--fire)",
  insufficient_evidence: "var(--stone-dark)",
  unknown: "var(--stone-dark)",
};

const OVERALL_BADGE: Record<
  string,
  "ok" | "warn" | "err" | "mute" | "info"
> = {
  healthy: "ok",
  degraded: "warn",
  insufficient_evidence: "mute",
  unknown: "mute",
};

export function Observability() {
  const [summaryEnvelope, setSummaryEnvelope] = useState<
    ObservabilityComponentEnvelope<ObservabilitySummaryPayload> | null
  >(null);
  const [index, setIndex] = useState<ObservabilityIndexPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [s, i] = await Promise.all([
          api.observabilitySummary(),
          api.observabilityIndex(),
        ]);
        if (!cancelled) {
          setSummaryEnvelope(s);
          setIndex(i);
        }
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
        title="Observability unavailable"
        message={`Failed to load observability surface: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }

  if (!summaryEnvelope || !index) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading observability artifacts..."
        icon={<Block size={36} />}
      />
    );
  }

  const summaryAvailable = summaryEnvelope.available && summaryEnvelope.payload;
  const summary = summaryEnvelope.payload;

  return (
    <div>
      <PixelSectionHeader
        title="Observability"
        icon={<Chip size={20} />}
        right={
          summaryAvailable && summary ? (
            <PixelBadge
              kind={OVERALL_BADGE[summary.overall_status] ?? "mute"}
            >
              {summary.overall_status.replace(/_/g, " ").toUpperCase()}
            </PixelBadge>
          ) : (
            <PixelBadge kind="mute">SUMMARY UNAVAILABLE</PixelBadge>
          )
        }
      />

      {/* Aggregator summary card */}
      {summaryAvailable && summary ? (
        <PixelCard variant="panel2" style={{ marginBottom: 18 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <div style={{ flex: 1, minWidth: 240 }}>
              <div className="pixel-stat-label">OVERALL STATUS</div>
              <div
                className="pxd"
                style={{
                  fontSize: 22,
                  marginTop: 4,
                  color:
                    OVERALL_TONE[summary.overall_status] ?? "var(--ink)",
                }}
              >
                {summary.overall_status.replace(/_/g, " ").toUpperCase()}
              </div>
              <div
                className="mono"
                style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 6 }}
              >
                generated {fmtAgo(summary.generated_at_utc)} · recommended next:{" "}
                <code>{summary.recommended_next_human_action}</code>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <PixelBadge kind="ok">
                {summary.component_status_counts?.available ?? 0} AVAILABLE
              </PixelBadge>
              <PixelBadge kind="err">
                {summary.component_status_counts?.corrupt ?? 0} CORRUPT
              </PixelBadge>
              <PixelBadge kind="warn">
                {summary.component_status_counts?.unavailable ?? 0} UNAVAILABLE
              </PixelBadge>
              <PixelBadge kind="info">
                {summary.deferred_component_count} DEFERRED
              </PixelBadge>
            </div>
          </div>

          {summary.critical_findings.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="pixel-stat-label" style={{ marginBottom: 6 }}>
                CRITICAL FINDINGS
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {summary.critical_findings.map((f) => (
                  <li
                    key={f}
                    className="mono"
                    style={{ fontSize: 13, color: "var(--brick)" }}
                  >
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {summary.warnings.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="pixel-stat-label" style={{ marginBottom: 6 }}>
                WARNINGS
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {summary.warnings.map((w) => (
                  <li key={w} className="mono" style={{ fontSize: 13 }}>
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {summary.informational_findings.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="pixel-stat-label" style={{ marginBottom: 6 }}>
                INFORMATIONAL
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {summary.informational_findings.map((m) => (
                  <li
                    key={m}
                    className="mono"
                    style={{ fontSize: 13, color: "var(--ink-muted)" }}
                  >
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </PixelCard>
      ) : (
        <PixelCard variant="panel2" style={{ marginBottom: 18 }}>
          <div className="pixel-stat-label" style={{ marginBottom: 8 }}>
            <Warn size={12} /> AGGREGATOR SUMMARY UNAVAILABLE
          </div>
          <div className="mono" style={{ fontSize: 13 }}>
            The observability_summary artifact has not yet been written. Run{" "}
            <code>python -m research.diagnostics build</code> in the dashboard
            container to produce one. The frontend remains read-only.
          </div>
        </PixelCard>
      )}

      {/* Component table */}
      <PixelCard padding={false}>
        <div
          style={{
            padding: "14px 18px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "4px solid var(--ink)",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <span className="pxd" style={{ fontSize: 11 }}>
            COMPONENTS · {index.active_count} active · {index.deferred_count}{" "}
            deferred
          </span>
          <span
            className="mono"
            style={{ fontSize: 12, color: "var(--ink-muted)" }}
          >
            artifact dir · <code>{index.observability_dir}</code>
          </span>
        </div>
        <table className="pixel-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Age</th>
              <th>Size</th>
              <th>Path</th>
            </tr>
          </thead>
          <tbody>
            {summaryAvailable && summary
              ? summary.components.map((c) => (
                  <tr key={c.name}>
                    <td className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                      {c.name}
                      {c.slug ? (
                        <span
                          className="mono"
                          style={{
                            fontSize: 11,
                            color: "var(--ink-muted)",
                            marginLeft: 8,
                          }}
                        >
                          /api/observability/{c.slug}
                        </span>
                      ) : null}
                    </td>
                    <td>
                      <ComponentStatusPill status={c.status} />
                    </td>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {ageOf(c.modified_at_unix)}
                    </td>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {c.size_bytes != null ? `${c.size_bytes}B` : "—"}
                    </td>
                    <td
                      className="mono"
                      style={{ fontSize: 12, color: "var(--ink-muted)" }}
                    >
                      {c.path ?? "—"}
                    </td>
                  </tr>
                ))
              : index.components.map((c) => (
                  <tr key={c.component}>
                    <td className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                      {c.component}
                      <span
                        className="mono"
                        style={{
                          fontSize: 11,
                          color: "var(--ink-muted)",
                          marginLeft: 8,
                        }}
                      >
                        /api/observability/{c.slug}
                      </span>
                    </td>
                    <td>
                      <ComponentStatusPill
                        status={
                          c.deferred
                            ? "deferred"
                            : c.exists
                            ? "available"
                            : "unavailable"
                        }
                      />
                    </td>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {ageOf(c.modified_at_unix)}
                    </td>
                    <td className="mono" style={{ fontSize: 13 }}>
                      {c.size_bytes != null ? `${c.size_bytes}B` : "—"}
                    </td>
                    <td
                      className="mono"
                      style={{ fontSize: 12, color: "var(--ink-muted)" }}
                    >
                      {c.artifact_path}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </PixelCard>

      <PixelCard variant="ink" style={{ marginTop: 18 }}>
        <div
          className="pxd"
          style={{ fontSize: 10, color: "var(--coin)", marginBottom: 8, letterSpacing: 1.2 }}
        >
          ▸ READ-ONLY SURFACE
        </div>
        <div className="mono" style={{ fontSize: 13, color: "var(--panel)" }}>
          Each row above is sourced from one read-only GET endpoint under{" "}
          <code>/api/observability/*</code>. Six components are deferred until
          v3.15.15.4. Inspecting the raw artifacts is best done via{" "}
          <Link to="/artifacts">Artifacts</Link>.
        </div>
        <div
          className="mono"
          style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 10 }}
        >
          <Star size={10} /> Aggregator: {summaryEnvelope.artifact_path} ·
          state <code>{summaryEnvelope.state}</code>
        </div>
      </PixelCard>
    </div>
  );
}
