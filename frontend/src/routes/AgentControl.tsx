// Mobile-first read-only Agent Control PWA — v3.15.15.18.
//
// Hard guarantees enforced by structure:
//   - No execute / approve / reject / merge buttons. The only
//     interactive control is a single "Vernieuw" (refresh) button
//     that re-fetches the same five GET endpoints.
//   - Cards render an empty / not_available state when their backing
//     artifact is missing or malformed; nothing is silently OK.
//   - Notification center is a placeholder; v3.15.15.18 does not ship
//     browser push.
//
// The full feature roadmap (proposal queue → approval inbox →
// execute-safe controls → browser push → metrics) is documented in
// docs/governance/mobile_agent_control_pwa.md.

import { useCallback, useEffect, useState } from "react";
import {
  agentControlApi,
  type AgentControlActivity,
  type AgentControlNotifications,
  type AgentControlPRLifecycle,
  type AgentControlProposals,
  type AgentControlStatus,
  type AgentControlWorkloop,
} from "../api/agent_control";
import "../styles/agent_control.css";

interface CardLoaderProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

function Card({ title, subtitle, children }: CardLoaderProps) {
  return (
    <section className="agent-control-card" aria-labelledby={`title-${title}`}>
      <header className="agent-control-card__header">
        <div>
          <h2 className="agent-control-card__title" id={`title-${title}`}>
            {title}
          </h2>
          <p className="agent-control-card__subtitle">{subtitle}</p>
        </div>
      </header>
      <div className="agent-control-card__body">{children}</div>
    </section>
  );
}

function StatusPill({
  state,
}: {
  state: "ok" | "warn" | "danger" | "unknown";
}) {
  const label =
    state === "ok"
      ? "ok"
      : state === "warn"
        ? "warn"
        : state === "danger"
          ? "blocked"
          : "not_available";
  return (
    <span
      className={`agent-control-pill agent-control-pill--${state}`}
      data-testid={`pill-${state}`}
    >
      {label}
    </span>
  );
}

function pillFor(status: string | undefined): "ok" | "warn" | "danger" | "unknown" {
  if (status === "ok") return "ok";
  if (status === "blocked") return "danger";
  if (status === "warn") return "warn";
  return "unknown";
}

// --- Card: governance status + frozen hashes ---
function StatusCard({ payload }: { payload: AgentControlStatus | null }) {
  if (!payload) {
    return (
      <Card
        title="Status"
        subtitle="governance + frozen contracts"
      >
        <p className="agent-control-card__empty" data-testid="status-loading">
          Laden…
        </p>
      </Card>
    );
  }
  const govStatus = payload.governance_status?.status ?? "not_available";
  const fhStatus = payload.frozen_hashes?.status ?? "not_available";
  const fh = payload.frozen_hashes?.data ?? {};
  return (
    <Card title="Status" subtitle="governance + frozen contracts">
      <div className="agent-control-card__row">
        <dt>governance</dt>
        <dd>
          <StatusPill state={pillFor(govStatus)} />
        </dd>
      </div>
      <div className="agent-control-card__row">
        <dt>frozen hashes</dt>
        <dd>
          <StatusPill state={pillFor(fhStatus)} />
        </dd>
      </div>
      {Object.keys(fh).length === 0 ? (
        <p
          className="agent-control-card__empty"
          data-testid="status-frozen-empty"
        >
          Geen contract-hashes beschikbaar
        </p>
      ) : (
        Object.entries(fh).map(([path, sha]) => (
          <div className="agent-control-card__row" key={path}>
            <dt>{path}</dt>
            <dd
              title={sha}
              data-testid={`hash-${path}`}
            >
              {sha === "missing" ? "missing" : `${sha.slice(0, 12)}…`}
            </dd>
          </div>
        ))
      )}
    </Card>
  );
}

// --- Card: agent activity ---
function ActivityCard({
  payload,
}: {
  payload: AgentControlActivity | null;
}) {
  if (!payload) {
    return (
      <Card title="Activity" subtitle="agent audit timeline">
        <p className="agent-control-card__empty">Laden…</p>
      </Card>
    );
  }
  if (payload.status !== "ok" || !payload.data) {
    return (
      <Card title="Activity" subtitle="agent audit timeline">
        <div className="agent-control-card__row">
          <dt>status</dt>
          <dd>
            <StatusPill state="unknown" />
          </dd>
        </div>
        <p
          className="agent-control-card__empty"
          data-testid="activity-not-available"
        >
          {payload.reason ?? "not_available"}
        </p>
      </Card>
    );
  }
  const data = payload.data;
  const recent = (data.rows ?? []).slice(-5).reverse();
  return (
    <Card title="Activity" subtitle="agent audit timeline (last 5)">
      <div className="agent-control-card__row">
        <dt>chain</dt>
        <dd>
          <StatusPill
            state={
              data.chain_status === "intact"
                ? "ok"
                : data.chain_status === "broken"
                  ? "danger"
                  : "unknown"
            }
          />
        </dd>
      </div>
      <div className="agent-control-card__row">
        <dt>events</dt>
        <dd>{data.ledger_event_count}</dd>
      </div>
      {recent.length === 0 ? (
        <p
          className="agent-control-card__empty"
          data-testid="activity-empty"
        >
          Geen events vandaag
        </p>
      ) : (
        recent.map((row, idx) => (
          <div
            className="agent-control-card__row"
            key={String(row.sequence_id ?? idx)}
          >
            <dt>
              #{String(row.sequence_id ?? "?")}{" "}
              {String(row.actor ?? "unknown")}
            </dt>
            <dd>{String(row.outcome ?? "unknown")}</dd>
          </div>
        ))
      )}
    </Card>
  );
}

// --- Card: autonomous workloop ---
function WorkloopCard({ payload }: { payload: AgentControlWorkloop | null }) {
  if (!payload) {
    return (
      <Card title="Workloop" subtitle="autonomous workloop digest">
        <p className="agent-control-card__empty">Laden…</p>
      </Card>
    );
  }
  if (payload.status !== "ok" || !payload.data) {
    return (
      <Card title="Workloop" subtitle="autonomous workloop digest">
        <p
          className="agent-control-card__empty"
          data-testid="workloop-not-available"
        >
          {payload.reason ?? "not_available"} —{" "}
          <code>{payload.artifact_path}</code>
        </p>
      </Card>
    );
  }
  const data = payload.data as Record<string, unknown>;
  const next = String(data.next_recommended_item ?? "unknown");
  const merges = String(data.merges_performed ?? "unknown");
  const mode = String(data.mode ?? "unknown");
  return (
    <Card title="Workloop" subtitle="autonomous workloop digest">
      <div className="agent-control-card__row">
        <dt>mode</dt>
        <dd>{mode}</dd>
      </div>
      <div className="agent-control-card__row">
        <dt>next</dt>
        <dd>{next}</dd>
      </div>
      <div className="agent-control-card__row">
        <dt>merges performed</dt>
        <dd>{merges}</dd>
      </div>
    </Card>
  );
}

// --- Card: GitHub PR lifecycle ---
function PRLifecycleCard({
  payload,
}: {
  payload: AgentControlPRLifecycle | null;
}) {
  if (!payload) {
    return (
      <Card title="PR Lifecycle" subtitle="Dependabot queue">
        <p className="agent-control-card__empty">Laden…</p>
      </Card>
    );
  }
  if (payload.status !== "ok" || !payload.data) {
    return (
      <Card title="PR Lifecycle" subtitle="Dependabot queue">
        <p
          className="agent-control-card__empty"
          data-testid="pr-not-available"
        >
          {payload.reason ?? "not_available"} —{" "}
          <code>{payload.artifact_path}</code>
        </p>
      </Card>
    );
  }
  const data = payload.data;
  const prs = data.prs ?? [];
  const recommendation = String(
    data.final_recommendation ?? "unknown",
  );
  return (
    <Card title="PR Lifecycle" subtitle="Dependabot queue">
      <div className="agent-control-card__row">
        <dt>recommendation</dt>
        <dd data-testid="pr-recommendation">{recommendation}</dd>
      </div>
      {prs.length === 0 ? (
        <p
          className="agent-control-card__empty"
          data-testid="pr-empty"
        >
          Geen open Dependabot PRs
        </p>
      ) : (
        prs.slice(0, 5).map((pr, idx) => {
          const number = String(pr.number ?? "?");
          const decision = String(pr.decision ?? "unknown");
          const risk = String(pr.risk_class ?? "UNKNOWN");
          const pillState =
            decision === "merge_allowed"
              ? "ok"
              : decision === "blocked_high_risk"
                ? "warn"
                : decision.startsWith("blocked_")
                  ? "danger"
                  : "unknown";
          return (
            <div className="agent-control-card__row" key={`${number}-${idx}`}>
              <dt>
                #{number}{" "}
                <span style={{ color: "var(--fg-muted)" }}>{risk}</span>
              </dt>
              <dd>
                <StatusPill state={pillState} />
              </dd>
            </div>
          );
        })
      )}
    </Card>
  );
}

// --- Card: proposal queue (v3.15.15.19) ---
function ProposalsCard({
  payload,
}: {
  payload: AgentControlProposals | null;
}) {
  if (!payload) {
    return (
      <Card title="Proposals" subtitle="roadmap intake queue">
        <p className="agent-control-card__empty">Laden…</p>
      </Card>
    );
  }
  if (payload.status !== "ok" || !payload.data) {
    return (
      <Card title="Proposals" subtitle="roadmap intake queue">
        <p
          className="agent-control-card__empty"
          data-testid="proposals-not-available"
        >
          {payload.reason ?? "not_available"} —{" "}
          <code>{payload.artifact_path}</code>
        </p>
      </Card>
    );
  }
  const data = payload.data;
  const proposals = data.proposals ?? [];
  const recommendation = String(data.final_recommendation ?? "unknown");
  return (
    <Card title="Proposals" subtitle="roadmap intake queue">
      <div className="agent-control-card__row">
        <dt>recommendation</dt>
        <dd data-testid="proposals-recommendation">{recommendation}</dd>
      </div>
      {proposals.length === 0 ? (
        <p
          className="agent-control-card__empty"
          data-testid="proposals-empty"
        >
          Geen proposals — geen roadmap intake op dit moment.
        </p>
      ) : (
        proposals.slice(0, 5).map((p, idx) => {
          const id = String(p.proposal_id ?? "?");
          const risk = String(p.risk_class ?? "UNKNOWN");
          const status = String(p.status ?? "unknown");
          const ptype = String(p.proposal_type ?? "unknown");
          const pillState =
            risk === "HIGH"
              ? status === "blocked"
                ? "danger"
                : "warn"
              : risk === "LOW"
                ? "ok"
                : "unknown";
          return (
            <div className="agent-control-card__row" key={`${id}-${idx}`}>
              <dt>
                {id}{" "}
                <span style={{ color: "var(--fg-muted)" }}>{ptype}</span>
              </dt>
              <dd>
                <StatusPill state={pillState} />
              </dd>
            </div>
          );
        })
      )}
    </Card>
  );
}

// --- Card: notification center placeholder ---
function NotificationsCard({
  payload,
}: {
  payload: AgentControlNotifications | null;
}) {
  if (!payload) {
    return (
      <Card title="Notifications" subtitle="placeholder (v3.15.15.18)">
        <p className="agent-control-card__empty">Laden…</p>
      </Card>
    );
  }
  const next = payload.next_release_with_push ?? "later";
  return (
    <Card
      title="Notifications"
      subtitle={`placeholder — browser push lands ${next}`}
    >
      {(payload.data ?? []).length === 0 ? (
        <p
          className="agent-control-card__empty"
          data-testid="notifications-empty"
        >
          Geen meldingen — browser push komt later.
        </p>
      ) : null}
    </Card>
  );
}

// --- Route ---
export function AgentControl() {
  const [status, setStatus] = useState<AgentControlStatus | null>(null);
  const [activity, setActivity] = useState<AgentControlActivity | null>(null);
  const [workloop, setWorkloop] = useState<AgentControlWorkloop | null>(null);
  const [prLifecycle, setPrLifecycle] =
    useState<AgentControlPRLifecycle | null>(null);
  const [notifications, setNotifications] =
    useState<AgentControlNotifications | null>(null);
  const [proposals, setProposals] = useState<AgentControlProposals | null>(
    null,
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshedAt, setRefreshedAt] = useState<string>("");

  const loadAll = useCallback(async () => {
    setLoading(true);
    const [s, a, w, p, n, q] = await Promise.all([
      agentControlApi.status(),
      agentControlApi.activity(),
      agentControlApi.workloop(),
      agentControlApi.prLifecycle(),
      agentControlApi.notifications(),
      agentControlApi.proposals(),
    ]);
    setStatus(s);
    setActivity(a);
    setWorkloop(w);
    setPrLifecycle(p);
    setNotifications(n);
    setProposals(q);
    setRefreshedAt(new Date().toISOString().replace("T", " ").slice(0, 19));
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <main
      className="agent-control"
      data-testid="agent-control-root"
      role="main"
    >
      <div className="agent-control__header">
        <h1>Agent Control</h1>
        <p>Read-only observability surface — v3.15.15.18.</p>
        <button
          type="button"
          className="agent-control__refresh"
          onClick={() => void loadAll()}
          disabled={loading}
          data-testid="agent-control-refresh"
          aria-label="Vernieuw alle kaarten"
        >
          {loading ? "Laden…" : "Vernieuw"}
        </button>
        {refreshedAt ? (
          <p
            className="agent-control-card__subtitle"
            data-testid="agent-control-refreshed-at"
          >
            laatste update: {refreshedAt} UTC
          </p>
        ) : null}
      </div>

      <div className="agent-control__grid">
        <StatusCard payload={status} />
        <ActivityCard payload={activity} />
        <WorkloopCard payload={workloop} />
        <PRLifecycleCard payload={prLifecycle} />
        <ProposalsCard payload={proposals} />
        <NotificationsCard payload={notifications} />
      </div>

      <footer className="agent-control__footer">
        <p>
          v3.15.15.18 — read-only. Geen execute / approve / merge knoppen.
          Schema:{" "}
          <code>docs/governance/github_pr_lifecycle/schema.v1.md</code>
        </p>
      </footer>
    </main>
  );
}
