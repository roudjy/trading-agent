import { useEffect, useState } from "react";
import { api, PresetCard } from "../api/client";

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
        setError(e instanceof Error ? e.message : "onbekende fout");
      }
    })();
  }, []);

  async function handleRun(name: string) {
    setLaunching(name);
    setLaunchMsg(null);
    try {
      const result = await api.runPreset(name);
      setLaunchMsg(`Gestart: ${String((result as Record<string, unknown>).launch_state ?? "ok")}`);
    } catch (e) {
      setLaunchMsg(
        `Starten mislukt: ${e instanceof Error ? e.message : "onbekend"}`
      );
    } finally {
      setLaunching(null);
    }
  }

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Run Presets</h2>
      {launchMsg && <div className="card">{launchMsg}</div>}
      {error && <div className="card danger">Fout: {error}</div>}
      {!presets && !error && <div className="muted">Presets laden…</div>}
      {presets && (
        <div className="preset-cards">
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
    </>
  );
}

interface PresetCardViewProps {
  preset: PresetCard;
  onRun: () => void;
  launching: boolean;
}

function PresetCardView({ preset: p, onRun, launching }: PresetCardViewProps) {
  const decision = p.decision;
  const hasDecisionBlock = decision?.is_product_decision === true;
  const hasEnablementCriteria =
    hasDecisionBlock && p.enablement_criteria.length > 0;
  const hasHypothesisDetail =
    !!(p.rationale || p.expected_behavior || p.falsification.length);

  return (
    <article className="preset-card" data-testid={`preset-card-${p.name}`}>
      <header>
        <h3>{p.name}</h3>
        <span className={`badge ${p.status}`}>{p.status}</span>
        {p.preset_class ? (
          <span className={`preset-class-badge ${p.preset_class}`}>
            {p.preset_class}
          </span>
        ) : null}
      </header>
      <p className="hypothesis">{p.hypothesis}</p>
      <div className="meta">
        <div>
          Timeframe <code>{p.timeframe}</code> · screening{" "}
          <code>{p.screening_mode}</code> · cost <code>{p.cost_mode}</code>
        </div>
        <div>
          Bundle:{" "}
          {p.bundle.map((b) => (
            <code key={b} style={{ marginRight: 4 }}>
              {b}
            </code>
          ))}
        </div>
        <div>Universe: {p.universe.join(", ")}</div>
        {p.regime_filter && (
          <div>
            Regime filter: <code>{p.regime_filter}</code> (
            {p.regime_modes.join(", ")})
          </div>
        )}
      </div>

      {hasHypothesisDetail ? (
        <div className="preset-hypothesis-section">
          {p.rationale ? (
            <div>
              <h4>Rationale</h4>
              <div>{p.rationale}</div>
            </div>
          ) : null}
          {p.expected_behavior ? (
            <div>
              <h4>Verwacht gedrag</h4>
              <div>{p.expected_behavior}</div>
            </div>
          ) : null}
          {p.falsification.length ? (
            <div>
              <h4>Falsificatie</h4>
              <ul style={{ margin: "0.2rem 0 0 1.2rem", padding: 0 }}>
                {p.falsification.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasDecisionBlock ? (
        <div
          className="decision-block"
          data-testid={`decision-block-${p.name}`}
          data-decision-kind={decision.kind ?? ""}
        >
          <h4>Product decision — {decision.kind}</h4>
          <div>{decision.summary}</div>
          {p.backlog_reason ? (
            <div>
              <span className="muted">Backlog reden:</span> {p.backlog_reason}
            </div>
          ) : null}
          {hasEnablementCriteria ? (
            <div>
              <div className="muted">
                Minimaal vereist voor enablement:
              </div>
              <ol>
                {p.enablement_criteria.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="run-row">
        <button
          disabled={!p.enabled || launching}
          onClick={onRun}
          title={
            !p.enabled
              ? `Preset is ${p.status}; niet uitvoerbaar tot enablement-criteria voldaan zijn`
              : "Start deze preset"
          }
        >
          {launching ? "Starten…" : "Run preset"}
        </button>
      </div>
    </article>
  );
}
