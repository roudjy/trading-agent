/**
 * AgentActivity — v3.15.16.A15.B2.0d
 *
 * Mobile-first read-only Agent Activity Center PWA surface, mounted by
 * App.tsx and consuming the six existing GET endpoints via the AAC
 * client methods on agentControlApi in
 * frontend/src/api/agent_control.ts.
 *
 * Hard guarantees enforced by the companion test files:
 *   - Read-only. Bottom-nav uses Link, not button. No rendered button
 *     has an accessible name matching a decision verb.
 *   - URL-synced active tab via useLocation pathname.
 *   - All network calls go through the API client; no direct browser
 *     network-API literal appears in this file.
 *   - No push-subscription, no notification-permission, no
 *     service-worker registration in this file.
 *   - CopyOperatorPhraseButton writes to the clipboard only.
 *   - Empty / not-available / malformed / offline envelopes render
 *     visibly without breaking the page.
 *   - Level 6 banner always renders permanently_disabled on the Safety
 *     section.
 *   - "No promotable candidates" copy renders for the empty
 *     done_blocked stage on the Pipeline section.
 *   - More section lists "Design Spec - documented in repo (deferred)"
 *     as plain info text - no broken navigation link.
 */

import {
  Routes,
  Route,
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useCallback, useEffect, useState } from "react";

import {
  agentControlApi,
  type ActivityAgentEvent,
  type ActivityAgentMatrixRow,
  type ActivityAgentsEnvelope,
  type ActivityArtifactHealth,
  type ActivityArtifactsEnvelope,
  type ActivityHumanAction,
  type ActivityInvariantStatus,
  type ActivityInvariantsEnvelope,
  type ActivityItemsDetailEnvelope,
  type ActivityItemsListEnvelope,
  type ActivityStage,
  type ActivityTodayEnvelope,
  type ActivityWorkItem,
} from "../../api/agent_control";

import "../../styles/agent_activity.css";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGE_ORDER: readonly ActivityStage[] = [
  "discovered",
  "queued",
  "delegated",
  "planned",
  "dry_run_ready",
  "pr_proposed",
  "pr_opened",
  "ci_feedback",
  "needs_human",
  "merge_candidate",
  "done_blocked",
];

const STAGE_LABEL: Record<ActivityStage, string> = {
  discovered: "Discovered",
  queued: "Queued",
  delegated: "Delegated",
  planned: "Planned",
  dry_run_ready: "Dry-run Ready",
  pr_proposed: "PR Proposed",
  pr_opened: "PR Opened",
  ci_feedback: "CI Feedback",
  needs_human: "Needs Human",
  merge_candidate: "Merge Candidate",
  done_blocked: "Done / Blocked",
};

const READ_ONLY_FOOTER_NOTE =
  "Read-only console. No approve, execute, merge, or deploy actions are available here.";

// ---------------------------------------------------------------------------
// Polling helper
// ---------------------------------------------------------------------------

function useAaCFetch<T>(
  loader: () => Promise<T>,
  intervalMs = 60_000,
): { state: T | null; loading: boolean; refresh: () => void } {
  const [state, setState] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => {
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loader()
      .then((value) => {
        if (!cancelled) {
          setState(value);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    const interval = setInterval(() => {
      if (
        typeof document !== "undefined" &&
        document.visibilityState !== "visible"
      ) {
        return;
      }
      setTick((t) => t + 1);
    }, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  return { state, loading, refresh };
}

// ---------------------------------------------------------------------------
// Atoms (scoped to .aac via className)
// ---------------------------------------------------------------------------

function StaleDataBanner({
  freshness,
  status,
}: {
  freshness?: { any_stale?: boolean; oldest_artifact_age_seconds?: number };
  status?: string;
}) {
  if (status && status !== "ok") {
    return (
      <div
        className="aac__banner aac__banner--offline"
        data-testid="aac-banner-offline"
        role="status"
        aria-live="polite"
      >
        Aggregator not available - showing last cached snapshot when possible.
      </div>
    );
  }
  if (freshness?.any_stale) {
    const age = Math.max(0, freshness.oldest_artifact_age_seconds ?? 0);
    const mins = Math.round(age / 60);
    return (
      <div
        className="aac__banner aac__banner--stale"
        data-testid="aac-banner-stale"
        role="status"
        aria-live="polite"
      >
        Stale snapshot - oldest upstream is {mins}m old.
      </div>
    );
  }
  return null;
}

function Badge({
  tone,
  children,
  testid,
}: {
  tone: string;
  children: React.ReactNode;
  testid?: string;
}) {
  return (
    <span
      className={`aac__badge aac__badge--${tone}`}
      data-testid={testid}
    >
      {children}
    </span>
  );
}

function StageBadge({ stage }: { stage: ActivityStage }) {
  const tone =
    stage === "needs_human"
      ? "human"
      : stage === "done_blocked"
        ? "blocked"
        : stage === "merge_candidate"
          ? "merge"
          : stage === "ci_feedback"
            ? "blocked"
            : stage === "planned"
              ? "planned"
              : "info";
  return <Badge tone={tone} testid={`aac-stage-${stage}`}>{STAGE_LABEL[stage]}</Badge>;
}

function RiskBadge({ risk }: { risk: string }) {
  const tone =
    risk === "high" || risk === "critical"
      ? "blocked"
      : risk === "medium"
        ? "human"
        : "off";
  return <Badge tone={tone}>{risk}</Badge>;
}

function FreshnessBadge({
  fresh,
  parse_ok,
}: {
  fresh: boolean;
  parse_ok: boolean;
}) {
  if (!parse_ok) {
    return <Badge tone="blocked" testid="aac-freshness-malformed">malformed</Badge>;
  }
  if (!fresh) {
    return <Badge tone="stale" testid="aac-freshness-stale">stale</Badge>;
  }
  return <Badge tone="merge" testid="aac-freshness-fresh">fresh</Badge>;
}

function EmptyState({
  title,
  body,
  testid,
}: {
  title: string;
  body?: string;
  testid?: string;
}) {
  return (
    <div className="aac__empty" data-testid={testid}>
      <div className="aac__empty-title">{title}</div>
      {body && <div className="aac__empty-body">{body}</div>}
    </div>
  );
}

function CopyOperatorPhraseButton({ phrase }: { phrase: string }) {
  const [copied, setCopied] = useState(false);
  const onClick = useCallback(() => {
    if (typeof navigator === "undefined") return;
    if (!navigator.clipboard || !navigator.clipboard.writeText) return;
    navigator.clipboard
      .writeText(phrase)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => {
        // Silent — clipboard permissions denied. No fallback network call.
      });
  }, [phrase]);
  return (
    <button
      type="button"
      className="aac__copy-phrase"
      data-testid="aac-copy-phrase"
      onClick={onClick}
      aria-label="Copy operator phrase to clipboard"
    >
      <code className="aac__copy-phrase-code">{phrase}</code>
      <span className="aac__copy-phrase-label">
        {copied ? "Copied" : "Copy phrase"}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Top bar + bottom nav
// ---------------------------------------------------------------------------

function AacTopBar({
  title,
  sub,
  showBack,
}: {
  title: string;
  sub?: string;
  showBack?: boolean;
}) {
  const navigate = useNavigate();
  return (
    <div className="aac__top-bar">
      <div className="aac__top-bar-row">
        {showBack && (
          <button
            type="button"
            className="aac__back"
            onClick={() => navigate(-1)}
            aria-label="Back"
            data-testid="aac-back"
          >
            ←
          </button>
        )}
        <h1 className="aac__top-title">{title}</h1>
      </div>
      {sub && <div className="aac__top-sub">{sub}</div>}
    </div>
  );
}

function AacBottomNav() {
  const { pathname } = useLocation();
  const todayActive =
    pathname === "/agent-control/activity" ||
    pathname === "/agent-control/activity/" ||
    pathname.startsWith("/agent-control/activity/today");
  const inboxActive = pathname.startsWith("/agent-control/activity/inbox");
  const pipelineActive = pathname.startsWith("/agent-control/activity/pipeline");
  const agentsActive = pathname.startsWith("/agent-control/activity/agents");
  const moreActive =
    pathname.startsWith("/agent-control/activity/more") ||
    pathname.startsWith("/agent-control/activity/artefacts") ||
    pathname.startsWith("/agent-control/activity/safety");
  return (
    <nav
      className="aac__bottom-nav"
      aria-label="Primary"
      data-testid="aac-bottom-nav"
    >
      <Link
        to="today"
        className="aac__nav-tab"
        aria-current={todayActive ? "page" : undefined}
        data-testid="aac-tab-today"
      >
        Today
      </Link>
      <Link
        to="inbox"
        className="aac__nav-tab"
        aria-current={inboxActive ? "page" : undefined}
        data-testid="aac-tab-inbox"
      >
        Inbox
      </Link>
      <Link
        to="pipeline"
        className="aac__nav-tab"
        aria-current={pipelineActive ? "page" : undefined}
        data-testid="aac-tab-pipeline"
      >
        Pipeline
      </Link>
      <Link
        to="agents"
        className="aac__nav-tab"
        aria-current={agentsActive ? "page" : undefined}
        data-testid="aac-tab-agents"
      >
        Agents
      </Link>
      <Link
        to="more"
        className="aac__nav-tab"
        aria-current={moreActive ? "page" : undefined}
        data-testid="aac-tab-more"
      >
        More
      </Link>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Today section
// ---------------------------------------------------------------------------

function MetricTile({
  label,
  value,
  sub,
  tone,
  to,
}: {
  label: string;
  value: number;
  sub: string;
  tone: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className={`aac__metric aac__metric--${tone}`}
      data-testid={`aac-metric-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="aac__metric-label">{label}</div>
      <div className="aac__metric-value">{value}</div>
      <div className="aac__metric-sub">{sub}</div>
    </Link>
  );
}

function CompactItemCard({ item }: { item: ActivityWorkItem }) {
  return (
    <Link
      to={`items/${encodeURIComponent(item.item_id)}`}
      className="aac__item-card"
      data-testid={`aac-item-${item.item_id}`}
    >
      <div className="aac__item-row">
        <StageBadge stage={item.current_stage} />
        <RiskBadge risk={item.risk} />
      </div>
      <div className="aac__item-title">{item.title}</div>
      <div className="aac__item-meta">
        <span className="aac__mono">{item.owner_role}</span>
        <span className="aac__muted"> · </span>
        <span className="aac__mono aac__muted">{item.latest_verdict}</span>
      </div>
    </Link>
  );
}

function SectionToday() {
  const { state, loading } = useAaCFetch<ActivityTodayEnvelope>(() =>
    agentControlApi.activityToday(),
  );
  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-today">
        <AacTopBar title="Today" sub="Loading snapshot..." />
        <div className="aac__skeleton" />
      </section>
    );
  }
  const env = state;
  const status = env?.status ?? "not_available";
  const counts = env?.counts ?? {};
  return (
    <section className="aac__section" data-testid="aac-section-today">
      <AacTopBar title="Today" sub="Read-only cockpit" />
      <StaleDataBanner freshness={env?.freshness} status={status} />
      <div className="aac__metrics" data-testid="aac-metric-grid">
        <MetricTile
          label="Needs human"
          value={counts.needs_human ?? 0}
          sub="review required"
          tone="human"
          to="../inbox"
        />
        <MetricTile
          label="Blocked"
          value={counts.blocked ?? 0}
          sub="by invariants / CI"
          tone="blocked"
          to="../pipeline"
        />
        <MetricTile
          label="Merge candidate"
          value={counts.merge_candidate ?? 0}
          sub="operator-gated"
          tone="merge"
          to="../pipeline"
        />
        <MetricTile
          label="CI feedback"
          value={counts.ci_feedback ?? 0}
          sub="re-runs / flake triage"
          tone="blocked"
          to="../pipeline"
        />
        <MetricTile
          label="Planned"
          value={counts.planned ?? 0}
          sub="plans drafted"
          tone="planned"
          to="../pipeline"
        />
        <MetricTile
          label="Dry-run ready"
          value={counts.dry_run_ready ?? 0}
          sub="candidates only"
          tone="info"
          to="../pipeline"
        />
      </div>
      <h2 className="aac__section-title">Needs human</h2>
      {(env?.needs_human?.length ?? 0) === 0 ? (
        <EmptyState
          title="Nothing needs you right now"
          body="No items require an operator-go phrase or review."
          testid="aac-today-needs-human-empty"
        />
      ) : (
        <div className="aac__list">
          {(env?.needs_human ?? []).slice(0, 3).map((w) => (
            <CompactItemCard key={w.item_id} item={w} />
          ))}
        </div>
      )}
      {(env?.merge_candidate?.length ?? 0) > 0 && (
        <>
          <h2 className="aac__section-title">Merge candidates</h2>
          <div className="aac__list">
            {(env?.merge_candidate ?? []).map((w) => (
              <CompactItemCard key={w.item_id} item={w} />
            ))}
          </div>
          <div
            className="aac__notice"
            data-testid="aac-live-merge-disabled-notice"
          >
            Live merge is permanently disabled. Surfaced for operator
            visibility only.
          </div>
        </>
      )}
      {(env?.ci_feedback?.length ?? 0) > 0 && (
        <>
          <h2 className="aac__section-title">CI feedback</h2>
          <div className="aac__list">
            {(env?.ci_feedback ?? []).map((w) => (
              <CompactItemCard key={w.item_id} item={w} />
            ))}
          </div>
        </>
      )}
      {(env?.blocked?.length ?? 0) > 0 && (
        <>
          <h2 className="aac__section-title">Blocked</h2>
          <div className="aac__list">
            {(env?.blocked ?? []).map((w) => (
              <CompactItemCard key={w.item_id} item={w} />
            ))}
          </div>
        </>
      )}
      <div className="aac__footer-note">{READ_ONLY_FOOTER_NOTE}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Inbox section
// ---------------------------------------------------------------------------

type InboxFilter = "all" | "required" | "optional";

function AttentionCard({
  action,
  reviewed,
  onToggle,
}: {
  action: ActivityHumanAction;
  reviewed: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="aac__attention-card"
      data-testid={`aac-attention-${action.action_id}`}
      data-reviewed={reviewed ? "true" : "false"}
    >
      <div className="aac__attention-row">
        <Badge tone="human">severity {action.severity}</Badge>
        <Badge tone="off">{action.suggested_role}</Badge>
        {action.safe_to_ignore && <Badge tone="off">safe to ignore</Badge>}
      </div>
      <div className="aac__attention-title">{action.title}</div>
      <div className="aac__attention-why">{action.why_required}</div>
      {action.required_phrase && (
        <CopyOperatorPhraseButton phrase={action.required_phrase} />
      )}
      <div className="aac__attention-meta">
        <Link
          to={`../items/${encodeURIComponent(action.item_id)}`}
          className="aac__link"
          data-testid={`aac-attention-trace-${action.action_id}`}
        >
          View trace
        </Link>
        <button
          type="button"
          className="aac__chip aac__chip--ghost"
          onClick={onToggle}
          aria-label={
            reviewed
              ? "Unmark reviewed (local-only)"
              : "Mark reviewed (local-only)"
          }
          data-testid={`aac-mark-reviewed-${action.action_id}`}
        >
          {reviewed ? "Unmark reviewed" : "Mark reviewed"}
        </button>
      </div>
      <div className="aac__mono aac__muted aac__attention-source">
        {action.source_artifact_path}
      </div>
    </div>
  );
}

function SectionInbox() {
  const { state, loading } = useAaCFetch<ActivityItemsListEnvelope>(() =>
    agentControlApi.activityItemsList({ human_needed: true }),
  );
  const [filter, setFilter] = useState<InboxFilter>("all");
  const [reviewed, setReviewed] = useState<Record<string, boolean>>({});

  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-inbox">
        <AacTopBar title="Approval Inbox" sub="Loading..." />
        <div className="aac__skeleton" />
      </section>
    );
  }

  const items = state?.work_items ?? [];
  // Synthesize HumanAction-like records from work items where human_needed=true.
  const actions: ActivityHumanAction[] = items
    .filter((w) => w.human_needed)
    .map((w) => ({
      action_id: `ha_${w.item_id}`,
      item_id: w.item_id,
      severity: w.risk,
      title: w.title,
      why_required: w.summary,
      // Required phrase is sourced from upstream only via Trace detail;
      // the list endpoint does not include human_actions[]. This inbox
      // surfaces the work-item list filtered by human_needed; the
      // operator opens the Trace view to see the phrase if any.
      required_phrase: null,
      safe_to_ignore: false,
      copy_only: true,
      source_artifact_path: w.source_path,
      suggested_role: w.owner_role,
      created_at: w.updated_at,
    }));
  const filtered = actions.filter((a) => {
    if (filter === "all") return true;
    if (filter === "required") return !a.safe_to_ignore;
    return a.safe_to_ignore;
  });

  return (
    <section className="aac__section" data-testid="aac-section-inbox">
      <AacTopBar
        title="Approval Inbox"
        sub="Operator attention items - copy-only"
      />
      <StaleDataBanner
        freshness={state?.freshness}
        status={state?.status}
      />
      <div className="aac__filter-pills" role="tablist" aria-label="Filter">
        {(
          [
            { id: "all" as const, label: "All", n: actions.length },
            {
              id: "required" as const,
              label: "Required",
              n: actions.filter((a) => !a.safe_to_ignore).length,
            },
            {
              id: "optional" as const,
              label: "Informational",
              n: actions.filter((a) => a.safe_to_ignore).length,
            },
          ]
        ).map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className="aac__chip"
            onClick={() => setFilter(f.id)}
            data-testid={`aac-inbox-filter-${f.id}`}
          >
            {f.label} <span className="aac__mono aac__muted">({f.n})</span>
          </button>
        ))}
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          title="Inbox zero"
          body="No operator attention items right now."
          testid="aac-inbox-empty"
        />
      ) : (
        <div className="aac__list">
          {filtered.map((a) => (
            <AttentionCard
              key={a.action_id}
              action={a}
              reviewed={!!reviewed[a.action_id]}
              onToggle={() =>
                setReviewed((r) => ({
                  ...r,
                  [a.action_id]: !r[a.action_id],
                }))
              }
            />
          ))}
        </div>
      )}
      <div className="aac__footer-note">
        <strong>Mark reviewed</strong> is local-only - it dims the card in
        this session. It does not approve or unblock any backend action.
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Pipeline section
// ---------------------------------------------------------------------------

function SectionPipeline() {
  const { state, loading } = useAaCFetch<ActivityItemsListEnvelope>(() =>
    agentControlApi.activityItemsList(),
  );
  const [activeStage, setActiveStage] = useState<ActivityStage>("needs_human");

  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-pipeline">
        <AacTopBar title="Pipeline" sub="Loading..." />
        <div className="aac__skeleton" />
      </section>
    );
  }

  const items = state?.work_items ?? [];
  const itemsAt = (s: ActivityStage) =>
    items.filter((w) => w.current_stage === s);
  const activeItems = itemsAt(activeStage);

  return (
    <section className="aac__section" data-testid="aac-section-pipeline">
      <AacTopBar
        title="Pipeline"
        sub="Roadmap to queue to delegation to merge"
      />
      <StaleDataBanner
        freshness={state?.freshness}
        status={state?.status}
      />
      <div
        className="aac__chip-row"
        role="tablist"
        aria-label="Stages"
        data-testid="aac-pipeline-chips"
      >
        {STAGE_ORDER.map((s) => {
          const n = itemsAt(s).length;
          return (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={activeStage === s}
              className="aac__chip"
              onClick={() => setActiveStage(s)}
              data-testid={`aac-pipeline-chip-${s}`}
            >
              {STAGE_LABEL[s]}{" "}
              <span className="aac__mono aac__muted">({n})</span>
            </button>
          );
        })}
      </div>
      {activeItems.length === 0 ? (
        <EmptyState
          title={
            activeStage === "done_blocked"
              ? "No promotable candidates"
              : "—"
          }
          testid={`aac-pipeline-empty-${activeStage}`}
        />
      ) : (
        <div className="aac__list">
          {activeItems.map((w) => (
            <CompactItemCard key={w.item_id} item={w} />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Agents section
// ---------------------------------------------------------------------------

function AgentRoleRow({ row }: { row: ActivityAgentMatrixRow }) {
  return (
    <div
      className="aac__agent-row"
      data-testid={`aac-agent-${row.role}`}
    >
      <div className="aac__agent-role">
        <span className="aac__mono">{row.role}</span>
      </div>
      <div className="aac__agent-stats">
        <span className="aac__agent-stat">
          <span className="aac__agent-stat-label">new</span>
          <span className="aac__mono">{row.new}</span>
        </span>
        <span className="aac__agent-stat">
          <span className="aac__agent-stat-label">planned</span>
          <span className="aac__mono">{row.planned}</span>
        </span>
        <span className="aac__agent-stat">
          <span className="aac__agent-stat-label">blocked</span>
          <span className="aac__mono">{row.blocked}</span>
        </span>
        <span className="aac__agent-stat">
          <span className="aac__agent-stat-label">human</span>
          <span className="aac__mono">{row.needs_human}</span>
        </span>
        <span className="aac__agent-stat">
          <span className="aac__agent-stat-label">PR-ready</span>
          <span className="aac__mono">{row.pr_ready}</span>
        </span>
      </div>
      {row.last_action && (
        <div className="aac__agent-last">
          <span className="aac__mono aac__muted">
            {row.last_action.module}
          </span>{" "}
          <span className="aac__muted">- {row.last_action.event_type}</span>
        </div>
      )}
    </div>
  );
}

function SectionAgents() {
  const { state, loading } = useAaCFetch<ActivityAgentsEnvelope>(() =>
    agentControlApi.activityAgents(),
  );
  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-agents">
        <AacTopBar title="Agents" sub="Loading..." />
        <div className="aac__skeleton" />
      </section>
    );
  }
  const rows = state?.rows ?? [];
  return (
    <section className="aac__section" data-testid="aac-section-agents">
      <AacTopBar title="Agents" sub="Role activity matrix" />
      <StaleDataBanner status={state?.status} />
      {rows.length === 0 ? (
        <EmptyState
          title="No agent activity"
          testid="aac-agents-empty"
        />
      ) : (
        <div className="aac__list">
          {rows.map((r) => (
            <AgentRoleRow key={r.role} row={r} />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Artefacts section
// ---------------------------------------------------------------------------

function ArtefactRow({ row }: { row: ActivityArtifactHealth }) {
  return (
    <div
      className="aac__artefact-row"
      data-testid={`aac-artefact-${row.path}`}
    >
      <div className="aac__artefact-path">
        <span className="aac__mono">{row.path}</span>
      </div>
      <div className="aac__artefact-meta">
        <span className="aac__mono aac__muted">
          {row.parse_ok ? `${row.row_count} rows` : (row.parse_error ?? "parse error")}
        </span>
        {row.module_version && (
          <span className="aac__mono aac__muted">
            {" · "}
            {row.module_version}
          </span>
        )}
        {row.read_only_warning && (
          <span
            className="aac__read-only-chip"
            data-testid={`aac-read-only-${row.path}`}
          >
            {row.read_only_warning}
          </span>
        )}
      </div>
      <FreshnessBadge fresh={row.fresh} parse_ok={row.parse_ok} />
    </div>
  );
}

function SectionArtefacts() {
  const { state, loading } = useAaCFetch<ActivityArtifactsEnvelope>(() =>
    agentControlApi.activityArtifacts(),
  );
  if (loading && !state) {
    return (
      <section
        className="aac__section"
        data-testid="aac-section-artefacts"
      >
        <AacTopBar title="Artefact Explorer" sub="Loading..." />
        <div className="aac__skeleton" />
      </section>
    );
  }
  const rows = state?.artifact_health ?? [];
  return (
    <section className="aac__section" data-testid="aac-section-artefacts">
      <AacTopBar
        title="Artefact Explorer"
        sub="Read-only audit"
        showBack
      />
      <StaleDataBanner status={state?.status} />
      {rows.length === 0 ? (
        <EmptyState
          title="No artefacts"
          body="The aggregator has not catalogued any upstreams."
          testid="aac-artefacts-empty"
        />
      ) : (
        <div className="aac__list">
          {rows.map((r) => (
            <ArtefactRow key={r.path} row={r} />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Safety section
// ---------------------------------------------------------------------------

function InvariantCard({ row }: { row: ActivityInvariantStatus }) {
  return (
    <div
      className={`aac__invariant aac__invariant--${row.tone}`}
      data-testid={`aac-invariant-${row.key}`}
    >
      <div className="aac__invariant-label">{row.label}</div>
      <div className="aac__invariant-value aac__mono">{String(row.value)}</div>
      <div className="aac__invariant-detail">{row.detail}</div>
    </div>
  );
}

function SectionSafety() {
  const { state, loading } = useAaCFetch<ActivityInvariantsEnvelope>(() =>
    agentControlApi.activityInvariants(),
  );
  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-safety">
        <AacTopBar title="System Safety" sub="Loading..." />
        <div className="aac__skeleton" />
      </section>
    );
  }
  const rows = state?.invariant_status ?? [];
  const level6 = rows.find((r) => r.key === "level_6");
  return (
    <section className="aac__section" data-testid="aac-section-safety">
      <AacTopBar
        title="System Safety"
        sub="Invariant posture - always-on"
        showBack
      />
      <StaleDataBanner status={state?.status} />
      <div
        className="aac__l6-banner"
        data-testid="aac-l6-banner"
        role="alert"
      >
        <div className="aac__l6-title">Level 6 - permanently disabled</div>
        <div className="aac__l6-body">
          Level 6 capabilities cannot be re-enabled by this UI or any
          agent. Build-time invariant per ADR-015 Doctrine 1. Surfaced
          here so the operator can confirm posture.
        </div>
      </div>
      <div className="aac__invariant-grid">
        {rows
          .filter((r) => r.key !== "level_6")
          .map((r) => (
            <InvariantCard key={r.key} row={r} />
          ))}
        {level6 && <InvariantCard row={level6} />}
      </div>
      <h2 className="aac__section-title">What this UI cannot do</h2>
      <ul className="aac__cant-do-list">
        <li>Approve or execute any gated operation</li>
        <li>Admit any work to the queue or generated lane</li>
        <li>Open, merge, or close a pull request</li>
        <li>Trigger or roll back a deploy</li>
        <li>Flip step5_implementation_allowed</li>
        <li>Mint or verify tokens</li>
        <li>Write to seed JSONL files</li>
        <li>Re-enable Level 6</li>
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// More section
// ---------------------------------------------------------------------------

function SectionMore() {
  return (
    <section className="aac__section" data-testid="aac-section-more">
      <AacTopBar title="More" sub="Drilldown views" />
      <div className="aac__list">
        <Link
          to="../artefacts"
          className="aac__more-row"
          data-testid="aac-more-artefacts"
        >
          <div className="aac__more-row-title">Artefact Explorer</div>
          <div className="aac__more-row-body">
            Grouped path list with freshness, row counts, raw JSON.
          </div>
        </Link>
        <Link
          to="../safety"
          className="aac__more-row"
          data-testid="aac-more-safety"
        >
          <div className="aac__more-row-title">System Safety</div>
          <div className="aac__more-row-body">
            Invariant posture, Level 6 banner, what this UI cannot do.
          </div>
        </Link>
        <div
          className="aac__more-row aac__more-row--deferred"
          data-testid="aac-more-spec-deferred"
          aria-disabled="true"
        >
          <div className="aac__more-row-title">Design Spec</div>
          <div className="aac__more-row-body">
            Design Spec - documented in repo (deferred)
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Trace detail section
// ---------------------------------------------------------------------------

function TimelineNode({ event }: { event: ActivityAgentEvent }) {
  return (
    <li
      className={`aac__timeline-node aac__timeline-node--${event.severity}`}
      data-testid={`aac-event-${event.event_id}`}
    >
      <div className="aac__timeline-head">
        <span className="aac__mono aac__muted">{event.timestamp}</span>
        <span className="aac__mono">{event.module}</span>
      </div>
      <div className="aac__timeline-summary">{event.summary}</div>
      <div className="aac__timeline-reason aac__muted">{event.reason}</div>
      <div className="aac__mono aac__muted aac__timeline-art">
        {event.artifact_path}
      </div>
    </li>
  );
}

function SectionTrace() {
  const { itemId: raw } = useParams<{ itemId: string }>();
  const safe = (raw ?? "").replace(/[^A-Za-z0-9_.\-]/g, "").slice(0, 128);
  const { state, loading } = useAaCFetch<ActivityItemsDetailEnvelope>(
    () => agentControlApi.activityItemsDetail(safe),
  );

  if (!safe) {
    return (
      <section className="aac__section" data-testid="aac-section-trace">
        <AacTopBar title="Trace" showBack />
        <EmptyState
          title="Invalid item id"
          body="The trace path could not be parsed."
          testid="aac-trace-invalid"
        />
      </section>
    );
  }

  if (loading && !state) {
    return (
      <section className="aac__section" data-testid="aac-section-trace">
        <AacTopBar title="Trace" sub="Loading..." showBack />
        <div className="aac__skeleton" />
      </section>
    );
  }

  if (state?.status !== "ok" || !state.work_item) {
    return (
      <section className="aac__section" data-testid="aac-section-trace">
        <AacTopBar title="Trace" showBack />
        <EmptyState
          title="Not in last snapshot"
          body="This item is not present in the latest aggregator snapshot."
          testid="aac-trace-not-found"
        />
      </section>
    );
  }

  const wi = state.work_item;
  const events = state.agent_events ?? [];
  const actions = state.human_actions ?? [];
  return (
    <section className="aac__section" data-testid="aac-section-trace">
      <AacTopBar
        title={wi.title}
        sub={`${wi.source_kind} - ${wi.updated_at}`}
        showBack
      />
      <div
        className="aac__trace-header"
        data-testid="aac-trace-header"
      >
        <div className="aac__attention-row">
          <StageBadge stage={wi.current_stage} />
          <RiskBadge risk={wi.risk} />
          {wi.human_needed && <Badge tone="human">needs human</Badge>}
        </div>
        <div className="aac__trace-summary">{wi.summary}</div>
        <dl className="aac__trace-meta">
          <div>
            <dt>item_id</dt>
            <dd className="aac__mono">{wi.item_id}</dd>
          </div>
          <div>
            <dt>owner_role</dt>
            <dd className="aac__mono">{wi.owner_role}</dd>
          </div>
          <div>
            <dt>source_path</dt>
            <dd className="aac__mono">{wi.source_path}</dd>
          </div>
          <div>
            <dt>latest_verdict</dt>
            <dd className="aac__mono">{wi.latest_verdict}</dd>
          </div>
          <div>
            <dt>next_action</dt>
            <dd>{wi.next_action}</dd>
          </div>
        </dl>
        {actions.map(
          (a) =>
            a.required_phrase && (
              <CopyOperatorPhraseButton
                key={a.action_id}
                phrase={a.required_phrase}
              />
            ),
        )}
      </div>
      <h2 className="aac__section-title">Event timeline</h2>
      {events.length === 0 ? (
        <EmptyState
          title="No timeline events yet"
          body="This item has been discovered but no agent has acted on it."
          testid="aac-trace-events-empty"
        />
      ) : (
        <ol className="aac__timeline">
          {events.map((e) => (
            <TimelineNode key={e.event_id} event={e} />
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export function AgentActivity() {
  return (
    <div
      className="aac"
      data-theme="dark"
      data-testid="aac-root"
    >
      <main className="aac__body">
        <Routes>
          <Route index element={<SectionToday />} />
          <Route path="today" element={<SectionToday />} />
          <Route path="inbox" element={<SectionInbox />} />
          <Route path="pipeline" element={<SectionPipeline />} />
          <Route path="agents" element={<SectionAgents />} />
          <Route path="more" element={<SectionMore />} />
          <Route path="artefacts" element={<SectionArtefacts />} />
          <Route path="safety" element={<SectionSafety />} />
          <Route path="items/:itemId" element={<SectionTrace />} />
          <Route path="*" element={<Navigate to="today" replace />} />
        </Routes>
      </main>
      <AacBottomNav />
    </div>
  );
}
