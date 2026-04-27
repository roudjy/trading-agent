import { useEffect, useState } from "react";
import { api, PresetCard } from "../api/client";
import { Coin, Pipe, Star, Warn } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";

export function Presets() {
  const [presets, setPresets] = useState<PresetCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const [launchMsg, setLaunchMsg] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.presets();
        setPresets(res.presets);
      } catch (e) {
        setError(e instanceof Error ? e.message : "unknown error");
      }
    })();
  }, []);

  async function handleRun(name: string) {
    setLaunching(name);
    setLaunchMsg(null);
    try {
      const result = await api.runPreset(name);
      setLaunchMsg(
        `Started: ${String((result as Record<string, unknown>).launch_state ?? "ok")}`
      );
    } catch (e) {
      setLaunchMsg(
        `Launch failed: ${e instanceof Error ? e.message : "unknown"}`
      );
    } finally {
      setLaunching(null);
    }
  }

  if (error) {
    return (
      <EmptyStatePanel
        title="Presets unavailable"
        message={`Failed to load presets: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }

  return (
    <div>
      <PixelSectionHeader title="Run Presets" icon={<Pipe size={20} />} />
      {launchMsg && (
        <PixelCard variant="panel2" style={{ marginBottom: 18 }}>
          <span className="mono">{launchMsg}</span>
        </PixelCard>
      )}
      {!presets ? (
        <EmptyStatePanel
          title="Loading"
          message="Fetching preset registry..."
          icon={<Pipe size={36} />}
        />
      ) : (
        <div className="grid-cards">
          {presets.map((p) => (
            <PresetCardView
              key={p.name}
              preset={p}
              onRun={() => void handleRun(p.name)}
              launching={launching === p.name}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PresetCardViewProps {
  preset: PresetCard;
  onRun: () => void;
  launching: boolean;
}

const STATUS_KIND: Record<string, "ok" | "warn" | "info" | "err"> = {
  stable: "ok",
  planned: "warn",
  diagnostic: "info",
  not_executable: "err",
};

function PresetCardView({ preset: p, onRun, launching }: PresetCardViewProps) {
  const decision = p.decision;
  const hasDecisionBlock = decision?.is_product_decision === true;
  const hasEnablementCriteria = hasDecisionBlock && p.enablement_criteria.length > 0;
  const hasHypothesisDetail = !!(
    p.rationale ||
    p.expected_behavior ||
    p.falsification.length
  );

  return (
    <PixelCard className={`preset-card-${p.name}`}>
      <div
        data-testid={`preset-card-${p.name}`}
        style={{ display: "flex", flexDirection: "column", gap: 10 }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="pxd" style={{ fontSize: 12, letterSpacing: 1 }}>
            {p.name}
          </span>
          <PixelBadge kind={STATUS_KIND[p.status] ?? "mute"}>{p.status}</PixelBadge>
          {p.preset_class && <PixelBadge kind="info">{p.preset_class}</PixelBadge>}
        </div>
        <div className="mono" style={{ fontSize: 14, color: "var(--ink-soft)" }}>
          {p.hypothesis}
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          timeframe <code>{p.timeframe}</code> · screening{" "}
          <code>{p.screening_mode}</code> · cost <code>{p.cost_mode}</code>
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          bundle:{" "}
          {p.bundle.map((b) => (
            <code key={b} style={{ marginRight: 4 }}>
              {b}
            </code>
          ))}
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          universe: {p.universe.join(", ")}
        </div>
        {p.regime_filter && (
          <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            regime filter: <code>{p.regime_filter}</code> ({p.regime_modes.join(", ")})
          </div>
        )}

        {hasHypothesisDetail && (
          <div
            style={{
              borderTop: "2px dashed var(--ink-muted)",
              paddingTop: 10,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            {p.rationale && (
              <div>
                <div className="pixel-stat-label">RATIONALE</div>
                <div className="mono" style={{ fontSize: 13 }}>
                  {p.rationale}
                </div>
              </div>
            )}
            {p.expected_behavior && (
              <div>
                <div className="pixel-stat-label">EXPECTED</div>
                <div className="mono" style={{ fontSize: 13 }}>
                  {p.expected_behavior}
                </div>
              </div>
            )}
            {p.falsification.length > 0 && (
              <div>
                <div className="pixel-stat-label">FALSIFICATION</div>
                <ul style={{ margin: "0.2rem 0 0 1.2rem", padding: 0, fontSize: 13 }}>
                  {p.falsification.map((f, i) => (
                    <li key={i} className="mono">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {hasDecisionBlock && (
          <div
            data-testid={`decision-block-${p.name}`}
            data-decision-kind={decision.kind ?? ""}
            style={{
              padding: 10,
              background: "var(--panel-2)",
              borderLeft: "4px solid var(--coin)",
            }}
          >
            <div className="pixel-stat-label" style={{ marginBottom: 4 }}>
              <Coin size={10} /> PRODUCT DECISION — {decision.kind}
            </div>
            <div className="mono" style={{ fontSize: 13 }}>
              {decision.summary}
            </div>
            {p.backlog_reason && (
              <div className="mono" style={{ fontSize: 13, marginTop: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Backlog reason:</span>{" "}
                {p.backlog_reason}
              </div>
            )}
            {hasEnablementCriteria && (
              <div style={{ marginTop: 6 }}>
                <div
                  className="mono"
                  style={{ fontSize: 13, color: "var(--ink-muted)" }}
                >
                  Required for enablement:
                </div>
                <ol style={{ margin: "0.2rem 0 0 1.2rem", padding: 0, fontSize: 13 }}>
                  {p.enablement_criteria.map((c, i) => (
                    <li key={i} className="mono">
                      {c}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}

        <div style={{ marginTop: "auto" }}>
          <button
            type="button"
            className="pixel-btn"
            disabled={!p.enabled || launching}
            onClick={onRun}
            title={
              !p.enabled
                ? `Preset is ${p.status}; not executable until enablement criteria are met`
                : "Run this preset"
            }
          >
            <Star size={10} />
            <span style={{ marginLeft: 6 }}>{launching ? "Launching…" : "Run preset"}</span>
          </button>
        </div>
      </div>
    </PixelCard>
  );
}
