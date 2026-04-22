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
            <article key={p.name} className="preset-card">
              <header>
                <h3>{p.name}</h3>
                <span className={`badge ${p.status}`}>{p.status}</span>
              </header>
              <p className="hypothesis">{p.hypothesis}</p>
              <div className="meta">
                <div>
                  Timeframe <code>{p.timeframe}</code> · screening{" "}
                  <code>{p.screening_mode}</code> · cost{" "}
                  <code>{p.cost_mode}</code>
                </div>
                <div>Bundle: {p.bundle.map((b) => <code key={b} style={{ marginRight: 4 }}>{b}</code>)}</div>
                <div>Universe: {p.universe.join(", ")}</div>
                {p.regime_filter && (
                  <div>
                    Regime filter: <code>{p.regime_filter}</code> (
                    {p.regime_modes.join(", ")})
                  </div>
                )}
                {p.diagnostic_only && (
                  <div className="warn">Diagnostic — not promoted</div>
                )}
                {p.excluded_from_daily_scheduler && (
                  <div className="muted">
                    Niet ingepland in de daily scheduler.
                  </div>
                )}
                {!p.enabled && p.backlog_reason && (
                  <div className="warn">Planned — {p.backlog_reason}</div>
                )}
              </div>
              <div className="run-row">
                <button
                  disabled={!p.enabled || launching === p.name}
                  onClick={() => void handleRun(p.name)}
                  title={
                    !p.enabled
                      ? `Preset is ${p.status}; niet uitvoerbaar in v3.10`
                      : "Start deze preset"
                  }
                >
                  {launching === p.name ? "Starten…" : "Run preset"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
