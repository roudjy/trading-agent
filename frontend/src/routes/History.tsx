import { useEffect, useState } from "react";
import { api, RunStatus } from "../api/client";
import { Chip, Star, Warn } from "../components/pixel/Glyphs";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";

interface ReportRow {
  path: string;
  run_id: string;
  modified_at_utc: string;
}

export function History() {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [s, r] = await Promise.all([api.runStatus(), api.reportHistory()]);
        setStatus(s);
        setReports(r.reports);
      } catch (e) {
        setError(e instanceof Error ? e.message : "unknown error");
      }
    })();
  }, []);

  if (error) {
    return (
      <EmptyStatePanel
        title="History unavailable"
        message={`Failed to load run history: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }

  return (
    <div>
      <PixelSectionHeader title="Run History" icon={<Star size={20} />} />

      <PixelCard style={{ marginBottom: 18 }}>
        <div className="pixel-stat-label" style={{ marginBottom: 8 }}>
          <Chip size={12} /> CURRENT / LATEST RUN
        </div>
        {status ? (
          <pre
            className="mono"
            style={{
              background: "var(--panel-2)",
              padding: 12,
              fontSize: 12,
              maxHeight: "50vh",
              overflow: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {JSON.stringify(status, null, 2)}
          </pre>
        ) : (
          <div className="mono" style={{ color: "var(--ink-muted)" }}>
            no run-status available
          </div>
        )}
      </PixelCard>

      <PixelCard padding={false}>
        <div style={{ padding: "14px 18px", borderBottom: "4px solid var(--ink)" }}>
          <span className="pxd" style={{ fontSize: 11 }}>
            ARCHIVED REPORTS
          </span>
        </div>
        {reports.length === 0 ? (
          <div className="mono" style={{ padding: 18, color: "var(--ink-muted)" }}>
            no archived reports found
          </div>
        ) : (
          <table className="pixel-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Path</th>
                <th>Modified (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.path}>
                  <td className="mono" style={{ fontSize: 13 }}>
                    <code>{r.run_id}</code>
                  </td>
                  <td className="mono" style={{ fontSize: 13 }}>
                    <code>{r.path}</code>
                  </td>
                  <td className="mono" style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                    {r.modified_at_utc}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PixelCard>
    </div>
  );
}
