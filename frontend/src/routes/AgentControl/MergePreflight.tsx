/**
 * AgentControlMergePreflight
 * --------------------------
 *
 * v3.15.16.N5b.phase1 — read-only PWA surface for the existing N5b
 * Phase 1 dry-run merge-preflight API
 * (``/api/agent-control/merge-preflight/{list,detail}``). Renders the
 * closed-schema candidate rows projected by
 * ``reporting.development_merge_preflight`` and surfaced via
 * ``dashboard.api_merge_preflight``.
 *
 * Two views share this component:
 *
 *   ``/agent-control/merge-preflight``
 *       Renders the read-only N5b list envelope.
 *
 *   ``/agent-control/merge-preflight/:preflightId``
 *       Renders the read-only N5b detail envelope for the bounded
 *       ``preflightId`` route parameter.
 *
 * The banner literal is fixed verbatim:
 *
 *   "Dry-run only. Live merge execution is not implemented."
 *
 * Hard guarantees enforced by the unit tests:
 *
 *   - Read-only banner is always rendered (list + detail).
 *   - Only the N5b endpoints under
 *     ``/api/agent-control/merge-preflight/...`` are fetched.
 *   - No call to any N4b ``approval-token`` endpoint.
 *   - No call to the N3b mobile-inbox endpoints.
 *   - No call to any hypothetical merge-execution / live merge
 *     endpoint.
 *   - No mutating verbs: every fetch is a ``GET`` with
 *     ``credentials: include``. No ``XMLHttpRequest``, no
 *     ``navigator.sendBeacon``, no POST / PUT / PATCH / DELETE.
 *   - Zero ``<button>`` elements in the rendered DOM. Navigation is
 *     via ``<Link>`` components only.
 *   - ``preflightId`` is bounded to charset ``[A-Za-z0-9_-]`` and
 *     ≤ 128 characters before any fetch.
 *   - Empty / not_available / not_found / invalid_preflight_id /
 *     malformed / network failure all collapse to safe states.
 *   - Discipline invariants from the envelope are surfaced verbatim
 *     (``dry_run_only``, ``live_merge_implemented``,
 *     ``deploy_coupled``, ``level6_enabled``,
 *     ``step5_implementation_allowed``, ``step5_enabled_substage``).
 *   - A ``<Link>`` back to ``/agent-control`` is always present.
 *
 * The closed ``dry_run_verdict`` vocabulary
 * (``would_block`` / ``would_require_operator`` /
 * ``would_be_live_candidate_if_authorized``) uses ``would_*`` prefixes
 * that are explicitly NOT executable decision verbs. The component
 * renders these strings verbatim from the envelope.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  agentControlApi,
  type AgentControlMergePreflightDetail,
  type AgentControlMergePreflightList,
  type AgentControlMergePreflightRow,
} from "../../api/agent_control";

const MAX_PREFLIGHT_ID_LEN = 128;
const READ_ONLY_BANNER =
  "Dry-run only. Live merge execution is not implemented.";

function boundedPreflightId(raw: string | undefined | null): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const safe = trimmed.replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_PREFLIGHT_ID_LEN);
}

function shortHead(sha: string | undefined | null): string {
  if (typeof sha !== "string" || !sha) return "";
  return sha.length > 12 ? `${sha.slice(0, 12)}…` : sha;
}

type ListState =
  | { phase: "loading" }
  | { phase: "ok"; envelope: AgentControlMergePreflightList }
  | { phase: "empty"; envelope: AgentControlMergePreflightList }
  | { phase: "not_available"; reason: string };

type DetailState =
  | { phase: "loading" }
  | { phase: "ok"; envelope: AgentControlMergePreflightDetail }
  | { phase: "not_found"; reason: string }
  | { phase: "invalid"; reason: string }
  | { phase: "not_available"; reason: string };

function Banner() {
  return (
    <div
      data-testid="agent-control-merge-preflight-banner"
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
        data-testid="agent-control-merge-preflight-back-link"
        style={{ color: "var(--ink, #1a73e8)" }}
      >
        Back to agent control
      </Link>
    </p>
  );
}

function DisciplineInvariants({
  envelope,
}: {
  envelope:
    | AgentControlMergePreflightList
    | AgentControlMergePreflightDetail;
}) {
  return (
    <p
      data-testid="agent-control-merge-preflight-invariants"
      style={{
        marginTop: "0.85rem",
        fontSize: "0.75rem",
        color: "rgba(0,0,0,0.55)",
        lineHeight: 1.5,
      }}
    >
      dry_run_only: {String(envelope.dry_run_only ?? true)} ·{" "}
      live_merge_implemented:{" "}
      {String(envelope.live_merge_implemented ?? false)} ·{" "}
      deploy_coupled: {String(envelope.deploy_coupled ?? false)} ·{" "}
      level6_enabled: {String(envelope.level6_enabled ?? false)} ·{" "}
      step5_implementation_allowed:{" "}
      {String(envelope.step5_implementation_allowed ?? false)} ·{" "}
      step5_enabled_substage:{" "}
      {envelope.step5_enabled_substage || "none"}
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
      data-testid="agent-control-merge-preflight-root"
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

function StopConditions({
  conditions,
  testIdPrefix,
}: {
  conditions: string[];
  testIdPrefix: string;
}) {
  if (!Array.isArray(conditions) || conditions.length === 0) {
    return (
      <span data-testid={`${testIdPrefix}-stop-conditions-empty`}>—</span>
    );
  }
  return (
    <ul
      data-testid={`${testIdPrefix}-stop-conditions`}
      style={{
        listStyle: "disc",
        margin: 0,
        paddingLeft: "1.1rem",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: "0.8rem",
      }}
    >
      {conditions.map((sc) => (
        <li
          key={sc}
          data-testid={`${testIdPrefix}-stop-condition-${sc}`}
        >
          {sc}
        </li>
      ))}
    </ul>
  );
}

function RowFields({
  row,
  testIdPrefix,
}: {
  row: AgentControlMergePreflightRow;
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
      <dt>preflight_id</dt>
      <dd data-testid={`${testIdPrefix}-preflight-id`}>
        <code>{row.preflight_id}</code>
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
      <dt>expected_head_sha</dt>
      <dd
        data-testid={`${testIdPrefix}-expected-head-sha`}
        title={row.expected_head_sha || ""}
      >
        <code>{shortHead(row.expected_head_sha) || "—"}</code>
      </dd>
      <dt>observed_head_sha</dt>
      <dd
        data-testid={`${testIdPrefix}-observed-head-sha`}
        title={row.observed_head_sha || ""}
      >
        <code>{shortHead(row.observed_head_sha) || "—"}</code>
      </dd>
      <dt>merge_state</dt>
      <dd data-testid={`${testIdPrefix}-merge-state`}>
        {row.merge_state || "—"}
      </dd>
      <dt>checks_state</dt>
      <dd data-testid={`${testIdPrefix}-checks-state`}>
        {row.checks_state || "—"}
      </dd>
      <dt>dry_run_verdict</dt>
      <dd data-testid={`${testIdPrefix}-dry-run-verdict`}>
        {row.dry_run_verdict || "—"}
      </dd>
      <dt>token_required_for_live</dt>
      <dd data-testid={`${testIdPrefix}-token-required-for-live`}>
        {String(row.token_required_for_live ?? true)}
      </dd>
      <dt>stop_conditions</dt>
      <dd>
        <StopConditions
          conditions={row.stop_conditions || []}
          testIdPrefix={testIdPrefix}
        />
      </dd>
      <dt>recommendation_action</dt>
      <dd data-testid={`${testIdPrefix}-recommendation-action`}>
        {row.recommendation_action || "—"}
      </dd>
      <dt>recommendation_reason</dt>
      <dd data-testid={`${testIdPrefix}-recommendation-reason`}>
        {row.recommendation_reason || "—"}
      </dd>
      <dt>evidence_freshness_seconds</dt>
      <dd data-testid={`${testIdPrefix}-evidence-freshness-seconds`}>
        {row.evidence_freshness_seconds}
      </dd>
      <dt>generated_at_utc</dt>
      <dd data-testid={`${testIdPrefix}-generated-at-utc`}>
        {row.generated_at_utc || "—"}
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
      .mergePreflightList()
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
    <PageShell heading="Merge preflight (N5b dry-run)">
      {state.phase === "loading" && (
        <p data-testid="agent-control-merge-preflight-loading">
          Loading merge preflight…
        </p>
      )}

      {state.phase === "not_available" && (
        <p
          data-testid="agent-control-merge-preflight-not-available"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The merge preflight artefact is not available
          ({state.reason}). The full N5b Phase 1 report is generated
          by <code>reporting.development_merge_preflight</code>; this
          view will render rows once the artefact is present.
        </p>
      )}

      {state.phase === "empty" && (
        <>
          <p
            data-testid="agent-control-merge-preflight-empty"
            style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
          >
            No open preflight candidates at this time. The N5b
            projector has produced an empty row set (
            {state.envelope.counts?.rows ?? 0} row(s)).
          </p>
          <DisciplineInvariants envelope={state.envelope} />
        </>
      )}

      {state.phase === "ok" && (
        <section
          data-testid="agent-control-merge-preflight-list"
          style={{ marginTop: "0.5rem" }}
        >
          <p
            data-testid="agent-control-merge-preflight-list-count"
            style={{
              fontSize: "0.85rem",
              color: "rgba(0,0,0,0.6)",
              margin: "0 0 0.6rem 0",
            }}
          >
            {state.envelope.rows.length} candidate(s) — generated_at_utc:{" "}
            <code>{state.envelope.generated_at_utc || "—"}</code>
          </p>
          <ul
            data-testid="agent-control-merge-preflight-list-items"
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
              const safeId = boundedPreflightId(row.preflight_id);
              return (
                <li
                  key={row.preflight_id}
                  data-testid={`agent-control-merge-preflight-row-${row.preflight_id}`}
                  style={{
                    padding: "0.6rem 0.7rem",
                    border: "1px solid rgba(0,0,0,0.08)",
                    borderRadius: "0.45rem",
                    background: "rgba(0,0,0,0.02)",
                  }}
                >
                  <Link
                    to={`/agent-control/merge-preflight/${safeId}`}
                    data-testid={`agent-control-merge-preflight-link-${row.preflight_id}`}
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
                      <span>{row.preflight_id}</span>
                      <span>PR #{row.pr_number}</span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.8rem",
                        color: "rgba(0,0,0,0.7)",
                      }}
                    >
                      <span
                        data-testid={`agent-control-merge-preflight-row-${row.preflight_id}-verdict`}
                      >
                        {row.dry_run_verdict || "—"}
                      </span>{" "}
                      ·{" "}
                      <span
                        data-testid={`agent-control-merge-preflight-row-${row.preflight_id}-merge-state`}
                      >
                        {row.merge_state || "—"}
                      </span>{" "}
                      /{" "}
                      <span
                        data-testid={`agent-control-merge-preflight-row-${row.preflight_id}-checks-state`}
                      >
                        {row.checks_state || "—"}
                      </span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
          <DisciplineInvariants envelope={state.envelope} />
        </section>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

function DetailView({ preflightId }: { preflightId: string }) {
  const [state, setState] = useState<DetailState>({ phase: "loading" });

  useEffect(() => {
    if (!preflightId) {
      setState({ phase: "invalid", reason: "empty" });
      return;
    }
    let cancelled = false;
    setState({ phase: "loading" });
    agentControlApi
      .mergePreflightDetail(preflightId)
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
          case "invalid_preflight_id":
            setState({
              phase: "invalid",
              reason: envelope.reason || "invalid_preflight_id",
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
  }, [preflightId]);

  return (
    <PageShell heading="Merge preflight detail (N5b dry-run)">
      <p
        data-testid="agent-control-merge-preflight-detail-id"
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
        preflight_id: {preflightId || "—"}
      </p>

      <p style={{ margin: "0 0 0.75rem 0" }}>
        <Link
          to="/agent-control/merge-preflight"
          data-testid="agent-control-merge-preflight-detail-list-link"
          style={{ color: "var(--ink, #1a73e8)" }}
        >
          ← Back to list
        </Link>
      </p>

      {state.phase === "loading" && (
        <p data-testid="agent-control-merge-preflight-detail-loading">
          Loading merge preflight detail…
        </p>
      )}

      {state.phase === "ok" && state.envelope.row && (
        <section
          data-testid="agent-control-merge-preflight-detail"
          style={{ marginTop: "0.5rem" }}
        >
          <RowFields
            row={state.envelope.row}
            testIdPrefix="agent-control-merge-preflight-detail"
          />
          {state.envelope.generated_at_utc ? (
            <p
              data-testid="agent-control-merge-preflight-detail-generated-at"
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
          <DisciplineInvariants envelope={state.envelope} />
        </section>
      )}

      {state.phase === "not_found" && (
        <p
          data-testid="agent-control-merge-preflight-detail-not-found"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          No preflight row matches this id ({state.reason}). The N5b
          artefact may have advanced past this head SHA, or the
          recommendation was already resolved upstream.
        </p>
      )}

      {state.phase === "invalid" && (
        <p
          data-testid="agent-control-merge-preflight-detail-invalid"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The preflight_id in this URL is not valid ({state.reason}).
          Go back to the list to pick a current row.
        </p>
      )}

      {state.phase === "not_available" && (
        <p
          data-testid="agent-control-merge-preflight-detail-not-available"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The merge preflight artefact is not available ({state.reason}).
        </p>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Entry point — picks list or detail based on the route parameter
// ---------------------------------------------------------------------------

export function AgentControlMergePreflight() {
  const params = useParams<{ preflightId?: string }>();
  const safeId = boundedPreflightId(params.preflightId);
  if (typeof params.preflightId === "string") {
    return <DetailView preflightId={safeId} />;
  }
  return <ListView />;
}
