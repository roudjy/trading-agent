import { useEffect, useState } from "react";
import { api } from "../api/client";

type CampaignDigest = {
  date?: string;
  campaigns_scheduled?: number;
  campaigns_completed?: number;
  campaigns_failed?: number;
  campaigns_canceled?: number;
  campaigns_frozen?: number;
  meaningful_campaigns_total?: number;
  queue_depth?: number;
  queue_efficiency_pct?: number;
  worker_utilization_pct?: number;
  estimated_compute_seconds_used?: number;
  actual_compute_seconds_used?: number;
  compute_seconds_per_meaningful_campaign?: number;
  compute_seconds_per_candidate?: number;
  compute_seconds_per_paper_worthy_candidate?: number;
  top_failure_reasons?: Array<{ reason_code: string; count: number }>;
  newly_frozen_presets?: string[];
  thawed_presets?: string[];
  campaigns_by_type?: Record<string, number>;
  preset_states?: Record<string, string>;
};

type QueueEntry = {
  campaign_id?: string;
  priority_tier?: number;
  state?: string;
  spawned_at_utc?: string;
  estimated_runtime_seconds?: number;
};

type QueueEnvelope = {
  queue?: QueueEntry[];
};

function formatSeconds(seconds: number | undefined | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "-";
  }
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function percent(value: number | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(1)}%`;
}

export function CampaignOpsCard(): JSX.Element | null {
  const [digest, setDigest] = useState<CampaignDigest | null>(null);
  const [queue, setQueue] = useState<QueueEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [d, q] = await Promise.all([
          api.campaignDigest(),
          api.campaignQueue(),
        ]);
        setDigest(d as CampaignDigest);
        setQueue(q as QueueEnvelope);
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
        data-testid="campaign-ops-card-error"
      >
        campaign ops data niet beschikbaar ({error})
      </div>
    );
  }
  if (!digest) {
    return (
      <div
        className="card muted"
        role="status"
        data-testid="campaign-ops-card-loading"
      >
        campaign ops data laden...
      </div>
    );
  }

  const frozen = Object.entries(digest.preset_states ?? {}).filter(
    ([, state]) => state === "frozen"
  );
  const queueEntries = queue?.queue ?? [];
  const nextPending = queueEntries
    .filter((e) => e.state === "pending")
    .sort(
      (a, b) =>
        (a.priority_tier ?? 9) - (b.priority_tier ?? 9) ||
        (a.spawned_at_utc ?? "").localeCompare(b.spawned_at_utc ?? "")
    )[0];

  return (
    <div
      className="card"
      role="region"
      aria-label="Campaign Ops"
      data-testid="campaign-ops-card"
    >
      <div className="card-header">
        <strong>Campaign Ops</strong>
        <span className="muted">{digest.date ?? "-"}</span>
      </div>
      <div className="card-body">
        <div className="row">
          <span>scheduled</span>
          <strong>{digest.campaigns_scheduled ?? 0}</strong>
        </div>
        <div className="row">
          <span>completed</span>
          <strong>{digest.campaigns_completed ?? 0}</strong>
        </div>
        <div className="row">
          <span>meaningful</span>
          <strong>{digest.meaningful_campaigns_total ?? 0}</strong>
        </div>
        <div className="row">
          <span>failed</span>
          <strong>{digest.campaigns_failed ?? 0}</strong>
        </div>
        <div className="row">
          <span>canceled</span>
          <strong>{digest.campaigns_canceled ?? 0}</strong>
        </div>
        <div className="row">
          <span>queue depth</span>
          <strong>{digest.queue_depth ?? queueEntries.length}</strong>
        </div>
        <div className="row">
          <span>worker utilisation</span>
          <strong>{percent(digest.worker_utilization_pct)}</strong>
        </div>
        <div className="row">
          <span>queue efficiency</span>
          <strong>{percent(digest.queue_efficiency_pct)}</strong>
        </div>
        <div className="row">
          <span>compute used</span>
          <strong>
            {formatSeconds(digest.actual_compute_seconds_used ?? 0)}{" "}
            <span className="muted">
              / est {formatSeconds(digest.estimated_compute_seconds_used ?? 0)}
            </span>
          </strong>
        </div>
        {nextPending ? (
          <div className="row">
            <span>next</span>
            <strong title={nextPending.campaign_id}>
              tier {nextPending.priority_tier ?? "?"} —{" "}
              {nextPending.campaign_id?.split("-").pop() ?? "?"}
            </strong>
          </div>
        ) : null}
        {frozen.length > 0 ? (
          <div className="row warn">
            <span>frozen presets</span>
            <strong>{frozen.map(([name]) => name).join(", ")}</strong>
          </div>
        ) : null}
        {digest.top_failure_reasons && digest.top_failure_reasons.length > 0 ? (
          <div className="row">
            <span>top failures</span>
            <strong>
              {digest.top_failure_reasons
                .map((r) => `${r.reason_code} (${r.count})`)
                .join(", ")}
            </strong>
          </div>
        ) : null}
      </div>
    </div>
  );
}
