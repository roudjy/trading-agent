import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadArtifactsModel } from "../api/adapters/artifacts";
import type { ArtifactsModel } from "../api/adapters/types";
import { Check, Chip, Star, Warn, XMark } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { FreshnessBadge } from "../components/pixel/Badges";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAge } from "../lib/time";

export function Artifacts() {
  const [model, setModel] = useState<ArtifactsModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadArtifactsModel();
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
        title="Artifact index unavailable"
        message={`Failed to read artifact directory: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Indexing research artifacts..."
        icon={<Chip size={36} />}
      />
    );
  }
  if (model.rows.length === 0) {
    return (
      <div>
        <PixelSectionHeader title="Artifacts" icon={<Chip size={20} />} />
        <EmptyStatePanel
          title="No Artifacts Found"
          message="The research/ directory is empty or unreadable."
          icon={<Chip size={36} />}
        />
      </div>
    );
  }

  return (
    <div>
      <PixelSectionHeader
        title="Artifacts"
        icon={<Chip size={20} />}
        right={
          <>
            <PixelBadge kind="ok">{model.totalFresh} fresh</PixelBadge>
            <PixelBadge kind="warn">{model.totalStale} stale</PixelBadge>
            <PixelBadge kind="err">{model.totalMissing} missing</PixelBadge>
          </>
        }
      />

      <PixelCard padding={false} style={{ marginBottom: 18 }}>
        <table className="pixel-table">
          <thead>
            <tr>
              <th>Artifact</th>
              <th>Exists</th>
              <th>Age</th>
              <th>Size</th>
              <th>State</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {model.rows.map((a) => (
              <tr key={a.name}>
                <td className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                  {a.name}
                </td>
                <td>
                  {a.exists ? (
                    <PixelBadge kind="ok" icon={<Check size={10} />}>
                      YES
                    </PixelBadge>
                  ) : (
                    <PixelBadge kind="err" icon={<XMark size={10} />}>
                      NO
                    </PixelBadge>
                  )}
                </td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {fmtAge(a.ageMin)}
                </td>
                <td className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                  {a.sizeBytes != null ? `${formatBytes(a.sizeBytes)}` : "—"}
                </td>
                <td>
                  <FreshnessBadge state={a.state} />
                </td>
                <td className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                  {a.note ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PixelCard>

      <div className="grid-2">
        <PixelCard variant="panel2">
          <div className="pixel-stat-label" style={{ marginBottom: 8 }}>
            FROZEN CONTRACTS
          </div>
          <div style={{ fontSize: 16, lineHeight: 1.5 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <Star size={14} /> <span className="mono">research/research_latest.json</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Star size={14} /> <span className="mono">research/strategy_matrix.csv</span>
            </div>
            <div
              className="mono"
              style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 12 }}
            >
              These contracts are read-only and not modified by the dashboard.
            </div>
          </div>
        </PixelCard>

        <PixelCard>
          <div className="pixel-stat-label" style={{ marginBottom: 8 }}>
            FRESHNESS POLICY
          </div>
          <div style={{ fontSize: 16, lineHeight: 1.6 }}>
            <div>
              <PixelBadge kind="ok">FRESH</PixelBadge>
              &nbsp;&lt; 4h since write
            </div>
            <div style={{ marginTop: 6 }}>
              <PixelBadge kind="warn">STALE</PixelBadge>
              &nbsp;≥ 4h since write
            </div>
            <div style={{ marginTop: 6 }}>
              <PixelBadge kind="err">MISSING</PixelBadge>
              &nbsp;artifact file not found
            </div>
            <div
              className="mono"
              style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 12 }}
            >
              For deep inspection of the latest research outputs see{" "}
              <Link to="/reports">Reports</Link> and{" "}
              <Link to="/candidates">Candidates</Link>.
            </div>
          </div>
        </PixelCard>
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}K`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)}M`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)}G`;
}
