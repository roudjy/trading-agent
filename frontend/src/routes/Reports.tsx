import { useEffect, useState } from "react";
import { api, ReportPayload } from "../api/client";

export function Reports() {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [payload, setPayload] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.reportLatest();
        setMarkdown(res.markdown);
        setPayload(res.payload);
      } catch (e) {
        setError(e instanceof Error ? e.message : "onbekende fout");
      }
    })();
  }, []);

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Reports</h2>
      {error && <div className="card danger">Fout: {error}</div>}
      {payload && (
        <section className="card">
          <h2>Samenvatting</h2>
          <dl style={{ margin: 0 }}>
            <dt className="muted">Verdict</dt>
            <dd><strong>{payload.verdict}</strong></dd>
            <dt className="muted">Preset</dt>
            <dd><code>{payload.preset ?? "—"}</code></dd>
            <dt className="muted">Run ID</dt>
            <dd><code>{payload.run_id ?? "—"}</code></dd>
            <dt className="muted">Samenvatting</dt>
            <dd>
              <ul>
                {Object.entries(payload.summary ?? {}).map(([k, v]) => (
                  <li key={k}>
                    {k}: <strong>{v}</strong>
                  </li>
                ))}
              </ul>
            </dd>
            <dt className="muted">Volgende experiment</dt>
            <dd>{payload.next_experiment}</dd>
            {payload.top_rejection_reasons?.length ? (
              <>
                <dt className="muted">Top rejection reasons</dt>
                <dd>
                  <ul>
                    {payload.top_rejection_reasons.map((r) => (
                      <li key={r.reason}>
                        {r.reason} ({r.count})
                      </li>
                    ))}
                  </ul>
                </dd>
              </>
            ) : null}
          </dl>
        </section>
      )}
      <section className="card">
        <h2>Markdown</h2>
        {markdown ? (
          <pre className="markdown">{markdown}</pre>
        ) : (
          <div className="muted">Geen report_latest.md beschikbaar.</div>
        )}
      </section>
    </>
  );
}
