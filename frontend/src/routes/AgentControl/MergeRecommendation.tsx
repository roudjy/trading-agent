/**
 * AgentControlMergeRecommendation
 * --------------------------------
 *
 * N5c — read-only PWA surface for the existing N5a merge-recommendation
 * API. Renders the closed-schema A23 / N5a payload as a bounded list
 * and per-row detail. **No** approve / reject / merge / deploy action
 * is exposed; merge execution remains N5b territory and is not
 * implemented in this stage.
 *
 * Two views share this component:
 *
 *   ``/agent-control/merge-recommendation``
 *       Renders the read-only N5a list envelope.
 *
 *   ``/agent-control/merge-recommendation/:recommendationId``
 *       Renders the read-only N5a detail envelope for the bounded
 *       ``recommendationId`` route parameter.
 *
 * Hard guarantees enforced by the unit tests:
 *
 *   - Read-only banner is always rendered.
 *   - Only the N5a endpoints under
 *     ``/api/agent-control/merge-recommendation/...`` are fetched.
 *   - No call to any N4b ``approval-token`` endpoint.
 *   - No call to the N3b mobile-inbox endpoints.
 *   - No mutating verbs: every fetch is a ``GET`` with
 *     ``credentials: same-origin``. No ``XMLHttpRequest``, no
 *     ``navigator.sendBeacon``, no POST / PUT / PATCH / DELETE.
 *   - Zero ``<button>`` elements in the rendered DOM. Tabs are
 *     ``<Link>`` components only; refresh is a ``<Link>`` to the
 *     same path with a refresh-triggered remount key.
 *   - ``recommendationId`` is bounded to charset ``[A-Za-z0-9_-]``
 *     and ≤ 128 characters before any fetch.
 *   - Empty / not_available / not_found / invalid_recommendation_id /
 *     malformed / network failure all collapse to safe states.
 *   - A ``<Link>`` back to ``/agent-control`` is always present.
 *
 * Note on the word "merge": this surface is *about* merge
 * recommendations and the read-only banner mentions that "merge
 * execution is not implemented in this stage". The unit tests therefore
 * assert *no decision-action button* and *no fetch to action endpoints*
 * rather than asserting the literal string "merge" never appears.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  agentControlApi,
  type AgentControlMergeRecommendationDetail,
  type AgentControlMergeRecommendationList,
  type AgentControlMergeRecommendationRow,
} from "../../api/agent_control";

const MAX_RECOMMENDATION_ID_LEN = 128;
const READ_ONLY_BANNER =
  "Read-only merge recommendation. Merge execution is not implemented in this stage.";

function boundedRecommendationId(raw: string | undefined | null): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const safe = trimmed.replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_RECOMMENDATION_ID_LEN);
}

function shortHead(sha: string | undefined | null): string {
  if (typeof sha !== "string" || !sha) return "";
  return sha.length > 12 ? `${sha.slice(0, 12)}…` : sha;
}

type ListState =
  | { phase: "loading" }
  | { phase: "ok"; envelope: AgentControlMergeRecommendationList }
  | { phase: "empty"; envelope: AgentControlMergeRecommendationList }
  | { phase: "not_available"; reason: string };

type DetailState =
  | { phase: "loading" }
  | { phase: "ok"; envelope: AgentControlMergeRecommendationDetail }
  | { phase: "not_found"; reason: string }
  | { phase: "invalid"; reason: string }
  | { phase: "not_available"; reason: string };

function Banner() {
  return (
    <div
      data-testid="agent-control-merge-recommendation-banner"
      style={{
        margin: "0 0 0.85rem 0",
        padding: "0.55rem 0.7rem",
        borderRadius: "0.4rem",
        background: "rgba(0,0,0,0.05)",
        fontSize: "0.85rem",
        lineHeight: 1.4,
      }}
    >
      {READ_ONLY_BANNER}
    </div>
  );
}

function BackLink() {
  return (
    <p style={{ margin: "1rem 0 0 0" }}>
      <Link
        to="/agent-control"
        data-testid="agent-control-merge-recommendation-back-link"
        style={{ color: "var(--ink, #1a73e8)" }}
      >
        Back to agent control
      </Link>
    </p>
  );
}

function PageShell({
  heading,
  children,
}: {
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <main
      data-testid="agent-control-merge-recommendation-root"
      style={{
        padding: "1.25rem",
        maxWidth: "640px",
        margin: "0 auto",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.4rem", margin: "0 0 0.75rem 0" }}>{heading}</h1>
      <Banner />
      {children}
      <BackLink />
    </main>
  );
}

function RowFields({
  row,
  testIdPrefix,
}: {
  row: AgentControlMergeRecommendationRow;
  testIdPrefix: string;
}) {
  return (
    <dl
      data-testid={`${testIdPrefix}-fields`}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        columnGap: "0.6rem",
        rowGap: "0.25rem",
        fontSize: "0.85rem",
        margin: 0,
      }}
    >
      <dt>recommendation_id</dt>
      <dd data-testid={`${testIdPrefix}-recommendation-id`}>
        <code>{row.recommendation_id}</code>
      </dd>
      <dt>pr_number</dt>
      <dd data-testid={`${testIdPrefix}-pr-number`}>{row.pr_number}</dd>
      <dt>head_ref</dt>
      <dd data-testid={`${testIdPrefix}-head-ref`}>
        <code>{row.head_ref || "—"}</code>
      </dd>
      <dt>base_ref</dt>
      <dd data-testid={`${testIdPrefix}-base-ref`}>
        <code>{row.base_ref || "—"}</code>
      </dd>
      <dt>head_sha</dt>
      <dd
        data-testid={`${testIdPrefix}-head-sha`}
        title={row.head_sha || ""}
      >
        <code>{shortHead(row.head_sha) || "—"}</code>
      </dd>
      <dt>observer_classification</dt>
      <dd data-testid={`${testIdPrefix}-observer-classification`}>
        {row.observer_classification || "—"}
      </dd>
      <dt>recommendation_action</dt>
      <dd data-testid={`${testIdPrefix}-recommendation-action`}>
        {row.recommendation_action || "—"}
      </dd>
      <dt>recommendation_reason</dt>
      <dd data-testid={`${testIdPrefix}-recommendation-reason`}>
        {row.recommendation_reason || "—"}
      </dd>
      <dt>inbox_blocked_count</dt>
      <dd data-testid={`${testIdPrefix}-inbox-blocked-count`}>
        {row.inbox_blocked_count}
      </dd>
      <dt>inbox_critical_count</dt>
      <dd data-testid={`${testIdPrefix}-inbox-critical-count`}>
        {row.inbox_critical_count}
      </dd>
      <dt>inbox_needs_review_count</dt>
      <dd data-testid={`${testIdPrefix}-inbox-needs-review-count`}>
        {row.inbox_needs_review_count}
      </dd>
      <dt>evaluated_at</dt>
      <dd data-testid={`${testIdPrefix}-evaluated-at`}>
        {row.evaluated_at || "—"}
      </dd>
    </dl>
  );
}

// ---------------------------------------------------------------------------
// List view
// ---------------------------------------------------------------------------

function ListView() {
  const [state, setState] = useState<ListState>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ phase: "loading" });
    agentControlApi
      .mergeRecommendationList()
      .then((envelope) => {
        if (cancelled) return;
        if (envelope.status !== "ok") {
          setState({
            phase: "not_available",
            reason: envelope.reason || "not_available",
          });
          return;
        }
        const rows = Array.isArray(envelope.rows) ? envelope.rows : [];
        if (rows.length === 0) {
          setState({ phase: "empty", envelope });
          return;
        }
        setState({ phase: "ok", envelope });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ phase: "not_available", reason: "network" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageShell heading="Merge recommendations">
      {state.phase === "loading" && (
        <p data-testid="agent-control-merge-recommendation-loading">
          Loading merge recommendations…
        </p>
      )}

      {state.phase === "not_available" && (
        <p
          data-testid="agent-control-merge-recommendation-not-available"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The merge recommendation artefact is not available
          ({state.reason}). The full N5a report is generated by{" "}
          <code>reporting.development_merge_recommendation</code>; this
          view will render rows once the artefact is present.
        </p>
      )}

      {state.phase === "empty" && (
        <p
          data-testid="agent-control-merge-recommendation-empty"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          No open recommendations at this time. The N5a projector has
          produced an empty row set ({state.envelope.counts?.rows ?? 0}{" "}
          row(s)).
        </p>
      )}

      {state.phase === "ok" && (
        <section
          data-testid="agent-control-merge-recommendation-list"
          style={{ marginTop: "0.5rem" }}
        >
          <p
            data-testid="agent-control-merge-recommendation-list-count"
            style={{
              fontSize: "0.85rem",
              color: "rgba(0,0,0,0.6)",
              margin: "0 0 0.6rem 0",
            }}
          >
            {state.envelope.rows.length} recommendation(s) —{" "}
            generated_at_utc:{" "}
            <code>{state.envelope.generated_at_utc || "—"}</code>
          </p>
          <ul
            data-testid="agent-control-merge-recommendation-list-items"
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {state.envelope.rows.map((row) => {
              const safeId = boundedRecommendationId(row.recommendation_id);
              return (
                <li
                  key={row.recommendation_id}
                  data-testid={`agent-control-merge-recommendation-row-${row.recommendation_id}`}
                  style={{
                    padding: "0.6rem 0.7rem",
                    border: "1px solid rgba(0,0,0,0.08)",
                    borderRadius: "0.45rem",
                    background: "rgba(0,0,0,0.02)",
                  }}
                >
                  <Link
                    to={`/agent-control/merge-recommendation/${safeId}`}
                    data-testid={`agent-control-merge-recommendation-link-${row.recommendation_id}`}
                    style={{
                      color: "var(--ink, #1a73e8)",
                      textDecoration: "none",
                      display: "block",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "0.5rem",
                        fontFamily:
                          "ui-monospace, SFMono-Regular, Menlo, monospace",
                        fontSize: "0.85rem",
                        marginBottom: "0.25rem",
                      }}
                    >
                      <span>{row.recommendation_id}</span>
                      <span>PR #{row.pr_number}</span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.8rem",
                        color: "rgba(0,0,0,0.7)",
                      }}
                    >
                      {row.recommendation_action} ·{" "}
                      {row.observer_classification || "—"}
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
          {state.envelope.step5_enabled_substage ? (
            <p
              data-testid="agent-control-merge-recommendation-step5-invariant"
              style={{
                marginTop: "0.85rem",
                fontSize: "0.75rem",
                color: "rgba(0,0,0,0.55)",
              }}
            >
              step5_implementation_allowed:{" "}
              {String(
                state.envelope.step5_implementation_allowed ?? false,
              )}{" "}
              · step5_enabled_substage:{" "}
              {state.envelope.step5_enabled_substage}
            </p>
          ) : null}
        </section>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

function DetailView({ recommendationId }: { recommendationId: string }) {
  const [state, setState] = useState<DetailState>({ phase: "loading" });

  useEffect(() => {
    if (!recommendationId) {
      setState({ phase: "invalid", reason: "empty" });
      return;
    }
    let cancelled = false;
    setState({ phase: "loading" });
    agentControlApi
      .mergeRecommendationDetail(recommendationId)
      .then((envelope) => {
        if (cancelled) return;
        switch (envelope.status) {
          case "ok":
            setState({ phase: "ok", envelope });
            return;
          case "not_found":
            setState({
              phase: "not_found",
              reason: envelope.reason || "not_found",
            });
            return;
          case "invalid_recommendation_id":
            setState({
              phase: "invalid",
              reason: envelope.reason || "invalid_recommendation_id",
            });
            return;
          default:
            setState({
              phase: "not_available",
              reason: envelope.reason || "not_available",
            });
            return;
        }
      })
      .catch(() => {
        if (cancelled) return;
        setState({ phase: "not_available", reason: "network" });
      });
    return () => {
      cancelled = true;
    };
  }, [recommendationId]);

  return (
    <PageShell heading="Merge recommendation detail">
      <p
        data-testid="agent-control-merge-recommendation-detail-id"
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.85rem",
          background: "rgba(0,0,0,0.04)",
          padding: "0.5rem 0.65rem",
          borderRadius: "0.4rem",
          wordBreak: "break-all",
          margin: "0 0 0.75rem 0",
        }}
      >
        recommendation_id: {recommendationId || "—"}
      </p>

      <p style={{ margin: "0 0 0.75rem 0" }}>
        <Link
          to="/agent-control/merge-recommendation"
          data-testid="agent-control-merge-recommendation-detail-list-link"
          style={{ color: "var(--ink, #1a73e8)" }}
        >
          ← Back to list
        </Link>
      </p>

      {state.phase === "loading" && (
        <p data-testid="agent-control-merge-recommendation-detail-loading">
          Loading merge recommendation detail…
        </p>
      )}

      {state.phase === "ok" && state.envelope.row && (
        <section
          data-testid="agent-control-merge-recommendation-detail"
          style={{ marginTop: "0.5rem" }}
        >
          <RowFields
            row={state.envelope.row}
            testIdPrefix="agent-control-merge-recommendation-detail"
          />
          {state.envelope.generated_at_utc ? (
            <p
              data-testid="agent-control-merge-recommendation-detail-generated-at"
              style={{
                marginTop: "0.65rem",
                fontSize: "0.75rem",
                color: "rgba(0,0,0,0.55)",
              }}
            >
              generated_at_utc:{" "}
              <code>{state.envelope.generated_at_utc}</code>
            </p>
          ) : null}
          {state.envelope.step5_enabled_substage ? (
            <p
              data-testid="agent-control-merge-recommendation-detail-step5-invariant"
              style={{
                marginTop: "0.25rem",
                fontSize: "0.75rem",
                color: "rgba(0,0,0,0.55)",
              }}
            >
              step5_implementation_allowed:{" "}
              {String(
                state.envelope.step5_implementation_allowed ?? false,
              )}{" "}
              · step5_enabled_substage:{" "}
              {state.envelope.step5_enabled_substage}
            </p>
          ) : null}
        </section>
      )}

      {state.phase === "not_found" && (
        <p
          data-testid="agent-control-merge-recommendation-detail-not-found"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          No recommendation row matches this id ({state.reason}). The
          N5a artefact may have advanced past this head SHA, or the
          recommendation was already resolved upstream.
        </p>
      )}

      {state.phase === "invalid" && (
        <p
          data-testid="agent-control-merge-recommendation-detail-invalid"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The recommendation_id in this URL is not valid
          ({state.reason}). Go back to the list to pick a current row.
        </p>
      )}

      {state.phase === "not_available" && (
        <p
          data-testid="agent-control-merge-recommendation-detail-not-available"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The merge recommendation artefact is not available
          ({state.reason}).
        </p>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Entry point — picks list or detail based on the route parameter
// ---------------------------------------------------------------------------

export function AgentControlMergeRecommendation() {
  const params = useParams<{ recommendationId?: string }>();
  const safeId = boundedRecommendationId(params.recommendationId);
  if (typeof params.recommendationId === "string") {
    return <DetailView recommendationId={safeId} />;
  }
  return <ListView />;
}
