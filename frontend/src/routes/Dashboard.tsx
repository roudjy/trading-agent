import { useEffect, useState } from "react";
import { api, Health, ReportPayload, RunStatus } from "../api/client";

export function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [h, s, r] = await Promise.all([
          api.health(),
          api.runStatus(),
          api.reportLatest().catch(() => ({ markdown: null, payload: null })),
        ]);
        setHealth(h);
        setStatus(s);
        setReport(r.payload ?? null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "onbekende fout");
      }
    })();
  }, []);

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Home</h2>

      {error && <div className="card danger">Fout: {error}</div>}

      <section className="card">
        <h2>Service</h2>
        <div className="stat-grid">
          <div className="stat">
            <div className="label">Version</div>
            <div className="value">{health?.version ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Last run age</div>
            <div className="value">
              {health?.last_run_age_seconds == null
                ? "—"
                : formatAge(health.last_run_age_seconds)}
            </div>
          </div>
          <div className="stat">
            <div className="label">Next scheduled</div>
            <div className="value">
              {health?.scheduler_next_fire_utc
                ? new Date(health.scheduler_next_fire_utc).toLocaleString()
                : "—"}
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Run status</h2>
        {status ? (
          <dl style={{ margin: 0 }}>
            <dt className="muted">Status</dt>
            <dd>
              <code>
                {String(
                  (status.run_state as Record<string, unknown> | null)?.artifact
                    ? ((status.run_state as { artifact: Record<string, unknown> }).artifact.status ?? "unknown")
                    : "unknown"
                )}
              </code>
            </dd>
            {status.warnings?.length ? (
              <>
                <dt className="muted">Waarschuwingen</dt>
                <dd>
                  <ul>
                    {status.warnings.map((w) => (
                      <li key={w} className="warn">{w}</li>
                    ))}
                  </ul>
                </dd>
              </>
            ) : null}
          </dl>
        ) : (
          <div className="muted">Geen status beschikbaar.</div>
        )}
      </section>

      <section className="card">
        <h2>Laatste report</h2>
        {report ? (
          <dl style={{ margin: 0 }}>
            <dt className="muted">Preset</dt>
            <dd>
              <code>{report.preset ?? "—"}</code>
            </dd>
            <dt className="muted">Verdict</dt>
            <dd>
              <strong>{report.verdict}</strong>
            </dd>
            <dt className="muted">Volgende experiment</dt>
            <dd>{report.next_experiment}</dd>
          </dl>
        ) : (
          <div className="muted">Nog geen report gegenereerd.</div>
        )}
      </section>
    </>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
  return `${(seconds / 86400).toFixed(1)} d`;
}
