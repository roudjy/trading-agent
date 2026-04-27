import { useEffect, useState } from "react";
import { loadVersionModel } from "../api/adapters/version";
import type { VersionModel } from "../api/adapters/types";
import { Check, Star, Warn, XMark } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAgo } from "../lib/time";

export function Version() {
  const [model, setModel] = useState<VersionModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadVersionModel();
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
        title="Version metadata unavailable"
        message={`Failed to load version metadata: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading version metadata..."
        icon={<Star size={36} />}
      />
    );
  }

  const fileMatchesBackend =
    !!model.fileVersion && !!model.backendVersion && model.fileVersion === model.backendVersion;
  const versionMtimeIso =
    model.versionFileMtime != null
      ? new Date(model.versionFileMtime * 1000).toISOString()
      : null;

  return (
    <div>
      <PixelSectionHeader
        title="Version / Deploy Integrity"
        icon={<Star size={20} />}
        right={
          model.drift ? (
            <PixelBadge kind="err" icon={<Warn size={10} />}>
              VERSION DRIFT
            </PixelBadge>
          ) : (
            <PixelBadge kind="ok" icon={<Check size={10} />}>
              NO DRIFT
            </PixelBadge>
          )
        }
      />

      <div className="grid-3" style={{ marginBottom: 18 }}>
        <PixelCard variant={fileMatchesBackend ? "" : "brick"}>
          <div className="pixel-stat-label">VERSION FILE</div>
          <div className="pxd" style={{ fontSize: 22, marginTop: 8 }}>
            {model.fileVersion ?? "—"}
          </div>
          <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 6 }}>
            VERSION
          </div>
        </PixelCard>
        <PixelCard variant={fileMatchesBackend ? "" : "brick"}>
          <div className="pixel-stat-label">BACKEND</div>
          <div className="pxd" style={{ fontSize: 22, marginTop: 8 }}>
            {model.backendVersion ?? "—"}
          </div>
          <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 6 }}>
            reported by /api/health
          </div>
        </PixelCard>
        <PixelCard>
          <div className="pixel-stat-label">DASHBOARD</div>
          <div className="pxd" style={{ fontSize: 22, marginTop: 8 }}>
            {model.dashboardVersion}
          </div>
          <div className="mono" style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: 6 }}>
            this UI build
          </div>
        </PixelCard>
      </div>

      <div className="grid-2" style={{ marginBottom: 18 }}>
        <PixelCard>
          <div className="pixel-stat-label" style={{ marginBottom: 12 }}>
            BUILD ARTIFACTS
          </div>
          <table className="pixel-table">
            <tbody>
              <tr>
                <td>Git HEAD</td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {model.gitHead ?? "—"}
                </td>
              </tr>
              <tr>
                <td>Container image</td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {model.imageTag ?? "—"}
                </td>
              </tr>
              <tr>
                <td>Host</td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {model.host ?? "—"}
                </td>
              </tr>
              <tr>
                <td>Container</td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {model.container ?? "—"}
                </td>
              </tr>
              <tr>
                <td>VERSION mtime</td>
                <td className="mono" style={{ fontSize: 13 }}>
                  {fmtAgo(versionMtimeIso)}
                </td>
              </tr>
            </tbody>
          </table>
        </PixelCard>

        <PixelCard variant={model.drift ? "brick" : "panel2"}>
          <div className="pxd" style={{ fontSize: 11, marginBottom: 10, letterSpacing: 1.2 }}>
            {model.drift ? "▸ DRIFT DETECTED" : "▸ INTEGRITY OK"}
          </div>
          <div style={{ fontSize: 16, lineHeight: 1.5, marginBottom: 14 }}>
            {model.drift
              ? "One or more reported versions does not match VERSION file. Operator action required outside of this UI."
              : "All reported versions match the VERSION file. No host/container mismatch detected."}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 14 }}>
            {model.driftDetails.map((d) => (
              <div key={d.check} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {d.ok ? <Check size={14} /> : <XMark size={14} />}
                <span>{d.check}</span>
              </div>
            ))}
          </div>
        </PixelCard>
      </div>
    </div>
  );
}
