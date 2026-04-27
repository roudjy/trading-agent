import { useEffect, useState } from "react";
import { api, type ResearchIntelligenceSummary } from "../api/client";

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return String(value);
}

function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function verdictTone(status: string | undefined): string {
  if (status === "promising") return "ok";
  if (status === "weak") return "info";
  if (status === "commercially_questionable" || status === "stop_or_pivot") {
    return "warn";
  }
  return "muted";
}

export function ResearchIntelligenceCard(): JSX.Element | null {
  const [summary, setSummary] = useState<ResearchIntelligenceSummary | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.researchIntelligenceSummary();
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "unknown error");
      }
    })();
  }, []);

  if (error) {
    return (
      <div
        className="card muted"
        role="status"
        data-testid="research-intelligence-card-error"
      >
        research intelligence niet beschikbaar ({error})
      </div>
    );
  }
  if (!summary) {
    return (
      <div
        className="card muted"
        role="status"
        data-testid="research-intelligence-card-loading"
      >
        research intelligence laden...
      </div>
    );
  }

  const verdictStatus = summary.viability?.status ?? "insufficient_data";
  const verdictClass = verdictTone(verdictStatus);
  const meaningfulRate = summary.metrics?.meaningful_campaign_rate;
  const ig = summary.information_gain ?? {};

  return (
    <div
      className="card"
      role="region"
      aria-label="Research Intelligence"
      data-testid="research-intelligence-card"
    >
      <div className="card-header">
        <strong>Research Intelligence</strong>
        <span className="muted">advisory · {summary.enforcement_state}</span>
      </div>
      <div className="card-body">
        <div className={`row ${verdictClass}`}>
          <span>viability</span>
          <strong>{verdictStatus}</strong>
        </div>
        {summary.viability?.human_summary ? (
          <div className="row muted">
            <span>summary</span>
            <strong>{summary.viability.human_summary}</strong>
          </div>
        ) : null}
        <div className="row">
          <span>campaigns</span>
          <strong>{formatNumber(summary.metrics?.campaign_count)}</strong>
        </div>
        <div className="row">
          <span>meaningful rate</span>
          <strong>{formatRate(meaningfulRate)}</strong>
        </div>
        <div className="row">
          <span>candidates</span>
          <strong>{formatNumber(summary.metrics?.candidate_count)}</strong>
        </div>
        <div className="row">
          <span>paper ready</span>
          <strong>{formatNumber(summary.metrics?.paper_ready_count)}</strong>
        </div>
        <div className="row">
          <span>last IG</span>
          <strong>
            {ig.bucket ?? "-"}{" "}
            <span className="muted">
              ({typeof ig.score === "number" ? ig.score.toFixed(2) : "-"})
            </span>
          </strong>
        </div>
        <div className="row">
          <span>advisory decisions</span>
          <strong>{summary.advisory_decision_count}</strong>
        </div>
        <div className="row">
          <span>dead zones</span>
          <strong>{summary.dead_zone_count}</strong>
        </div>
        {summary.spawn_proposals ? (
          <>
            <div
              className={`row ${
                summary.spawn_proposals.proposal_mode === "diagnostic_only"
                  ? "warn"
                  : ""
              }`}
            >
              <span>proposal mode</span>
              <strong>{summary.spawn_proposals.proposal_mode ?? "-"}</strong>
            </div>
            <div className="row">
              <span>spawn proposals</span>
              <strong>{summary.spawn_proposals.proposed_count ?? 0}</strong>
            </div>
            <div className="row">
              <span>suppressed zones</span>
              <strong>
                {summary.spawn_proposals.suppressed_zone_count ?? 0}
              </strong>
            </div>
            {summary.spawn_proposals.human_review_required ? (
              <div className="row warn">
                <span>review required</span>
                <strong>yes — viability stop_or_pivot</strong>
              </div>
            ) : null}
            {(summary.spawn_proposals.top_proposals ?? []).slice(0, 3).map(
              (p, idx) => (
                <div
                  className="row muted"
                  key={`${p.preset_name ?? "unknown"}-${idx}`}
                >
                  <span>{p.priority_tier ?? "?"}</span>
                  <strong>
                    {p.proposal_type ?? "?"}{" "}
                    <span className="muted">{p.preset_name ?? ""}</span>
                  </strong>
                </div>
              )
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
