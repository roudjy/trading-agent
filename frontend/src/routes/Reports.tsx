import { useEffect, useState } from "react";
import { api, ReportPayload } from "../api/client";
import { StaleArtifactBanner } from "../components/StaleArtifactBanner";
import { Star, Warn } from "../components/pixel/Glyphs";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";

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
        setError(e instanceof Error ? e.message : "unknown error");
      }
    })();
  }, []);

  if (error) {
    return (
      <EmptyStatePanel
        title="Report unavailable"
        message={`Failed to load latest report: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }

  return (
    <div>
      <PixelSectionHeader title="Reports" icon={<Star size={20} />} />
      <StaleArtifactBanner />
      {payload && (
        <PixelCard style={{ marginBottom: 18 }}>
          <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
            SUMMARY
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="mono" style={{ fontSize: 14 }}>
              <span style={{ color: "var(--ink-muted)" }}>verdict ·</span>{" "}
              <PixelBadge kind="info">{payload.verdict}</PixelBadge>
            </div>
            <div className="mono" style={{ fontSize: 14 }}>
              <span style={{ color: "var(--ink-muted)" }}>preset ·</span>{" "}
              <code>{payload.preset ?? "—"}</code>
            </div>
            <div className="mono" style={{ fontSize: 14 }}>
              <span style={{ color: "var(--ink-muted)" }}>run id ·</span>{" "}
              <code>{payload.run_id ?? "—"}</code>
            </div>
            <div className="mono" style={{ fontSize: 14 }}>
              <span style={{ color: "var(--ink-muted)" }}>next experiment ·</span>{" "}
              {payload.next_experiment}
            </div>
            {payload.top_rejection_reasons?.length > 0 && (
              <div>
                <div className="pixel-stat-label" style={{ marginTop: 12, marginBottom: 6 }}>
                  TOP REJECTION REASONS
                </div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {payload.top_rejection_reasons.map((r) => (
                    <li key={r.reason} className="mono" style={{ fontSize: 13 }}>
                      {r.reason} ({r.count})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </PixelCard>
      )}
      <PixelCard>
        <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
          MARKDOWN
        </div>
        {markdown ? (
          <pre
            className="mono"
            style={{
              background: "var(--panel-2)",
              padding: 12,
              fontSize: 12,
              maxHeight: "60vh",
              overflow: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {markdown}
          </pre>
        ) : (
          <div className="mono" style={{ color: "var(--ink-muted)" }}>
            no report_latest.md available
          </div>
        )}
      </PixelCard>
    </div>
  );
}
