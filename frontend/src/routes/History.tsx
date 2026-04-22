import { useEffect, useState } from "react";
import { api, RunStatus } from "../api/client";

export function History() {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [reports, setReports] = useState<
    { path: string; run_id: string; modified_at_utc: string }[]
  >([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [s, r] = await Promise.all([
          api.runStatus(),
          api.reportHistory(),
        ]);
        setStatus(s);
        setReports(r.reports);
      } catch (e) {
        setError(e instanceof Error ? e.message : "onbekende fout");
      }
    })();
  }, []);

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Run History</h2>
      {error && <div className="card danger">Fout: {error}</div>}
      <section className="card">
        <h2>Huidige/laatste run</h2>
        {status ? (
          <pre className="markdown">{JSON.stringify(status, null, 2)}</pre>
        ) : (
          <div className="muted">Geen run-status beschikbaar.</div>
        )}
      </section>
      <section className="card">
        <h2>Gearchiveerde reports</h2>
        {reports.length === 0 ? (
          <div className="muted">Geen archief reports gevonden.</div>
        ) : (
          <table className="candidate-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Pad</th>
                <th>Laatst gewijzigd (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.path}>
                  <td><code>{r.run_id}</code></td>
                  <td><code>{r.path}</code></td>
                  <td>{r.modified_at_utc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
