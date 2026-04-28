import { useEffect, useState } from "react";
import { api } from "../api/client";
import { loadVersionModel } from "../api/adapters/version";
import type { VersionModel } from "../api/adapters/types";
import type {
  ObservabilityComponentEnvelope,
  SystemIntegrityPayload,
} from "../api/client";
import { Check, Chip, Star, Warn, XMark } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAgo } from "../lib/time";

export function Version() {
  const [model, setModel] = useState<VersionModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [integrityEnvelope, setIntegrityEnvelope] = useState<
    ObservabilityComponentEnvelope<SystemIntegrityPayload> | null
  >(null);

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

      <SystemIntegrityIntegrityCard envelope={integrityEnvelope} />
    </div>
  );
}

function SystemIntegrityIntegrityCard({
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
          <code>python -m research.diagnostics build</code> to see the
          observability-side integrity card here.
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
        <Chip size={12} /> OBSERVABILITY · system integrity (sidecar)
      </div>
      <table className="pixel-table">
        <tbody>
          <tr>
            <td>VERSION (observed)</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.version_file ?? "—"}
            </td>
          </tr>
          <tr>
            <td>git head</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.git.head ?? "—"}
            </td>
          </tr>
          <tr>
            <td>git branch</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.git.branch ?? "—"}
            </td>
          </tr>
          <tr>
            <td>git dirty</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.git.dirty == null ? (
                "—"
              ) : p.git.dirty ? (
                <PixelBadge kind="warn">DIRTY</PixelBadge>
              ) : (
                <PixelBadge kind="ok">CLEAN</PixelBadge>
              )}
            </td>
          </tr>
          <tr>
            <td>timezone</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.timezone ?? "—"}
            </td>
          </tr>
          <tr>
            <td>last observability artifact write</td>
            <td className="mono" style={{ fontSize: 13 }}>
              {p.last_observability_artifact_update_unix
                ? fmtAgo(
                    new Date(
                      p.last_observability_artifact_update_unix * 1000
                    ).toISOString()
                  )
                : "—"}
            </td>
          </tr>
        </tbody>
      </table>
    </PixelCard>
  );
}
