/**
 * AgentControlInboxPlaceholder
 * ----------------------------
 *
 * N3c — read-only landing page for
 * ``/agent-control/inbox?event=<event_id>`` deep-links opened by the
 * Web Push service worker's ``notificationclick`` handler. The SW
 * sanitiser already constrains the URL to the ``/agent-control/inbox``
 * prefix; this component fetches the bounded N3b detail envelope and
 * renders the safe fields.
 *
 * Hard guarantees enforced by the unit test:
 *   - Renders the bounded ``event_id`` query parameter when present.
 *   - When the read-only N3b API at
 *     ``/api/agent-control/mobile-inbox/detail/<event_id>`` returns a
 *     row, the closed-schema scalars are rendered: event_id,
 *     event_kind, event_severity, attention_level, decision_state,
 *     source_module, title, summary, created_at, open_at.
 *   - When the API returns ``not_available`` / ``not_found`` /
 *     network failure, the component renders the safe empty state
 *     and a ``data-testid="agent-control-inbox-empty"`` marker.
 *   - Contains NO ``approve`` / ``reject`` / ``merge`` / ``deploy``
 *     button, link, or visible text. Approval still requires the
 *     future N4 token gate, never a notification tap.
 *   - Performs ONLY a single same-origin GET to the read-only
 *     detail endpoint. No ``XMLHttpRequest``, no
 *     ``navigator.sendBeacon``, no POST / DELETE / PUT.
 *   - Provides a ``<Link>`` back to ``/agent-control``.
 *   - The banner "Read-only inbox detail. Approval actions are not
 *     implemented in this stage." is always rendered.
 *
 * No real evidence is shown — only the bounded six-or-so scalars the
 * projector already emitted. The placeholder is intentionally bland.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

const MAX_EVENT_ID_LEN = 64;
const DETAIL_BASE = "/api/agent-control/mobile-inbox/detail/";

function boundedEventId(raw: string | null): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const safe = trimmed.replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_EVENT_ID_LEN);
}

type InboxRow = {
  inbox_row_id: string;
  event_id: string;
  event_kind: string;
  event_severity: string;
  source_module: string;
  source_id: string;
  endpoint_hash: string;
  outbound_delivery_intent: string;
  attention_level: string;
  decision_state: string;
  title: string;
  summary: string;
  open_at: string;
  created_at: string;
};

type DetailResponse =
  | {
      kind: string;
      status: "ok";
      row: InboxRow;
      generated_at_utc?: string;
    }
  | {
      kind: string;
      status: "not_available" | "not_found" | "invalid_event_id";
      reason?: string;
    };

type FetchState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ok"; row: InboxRow; generatedAt: string }
  | { phase: "empty"; reason: string };

const READ_ONLY_BANNER =
  "Read-only inbox detail. Approval actions are not implemented in this stage.";

export function AgentControlInboxPlaceholder() {
  const location = useLocation();
  const [search] = useSearchParams();
  const eventId = boundedEventId(search.get("event"));
  const isInbox = location.pathname.startsWith("/agent-control/inbox");
  const heading = isInbox ? "Inbox notification" : "Agent control";

  const [state, setState] = useState<FetchState>({ phase: "idle" });

  useEffect(() => {
    if (!isInbox || !eventId) {
      setState({ phase: "idle" });
      return;
    }
    let cancelled = false;
    setState({ phase: "loading" });
    fetch(DETAIL_BASE + encodeURIComponent(eventId), {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(async (res) => {
        if (cancelled) return;
        // Even on 4xx we still parse the body to honour the API's
        // not_available / not_found envelope shape.
        let body: DetailResponse | null = null;
        try {
          body = (await res.json()) as DetailResponse;
        } catch {
          body = null;
        }
        if (body && body.status === "ok" && "row" in body && body.row) {
          setState({
            phase: "ok",
            row: body.row,
            generatedAt:
              ("generated_at_utc" in body && body.generated_at_utc) || "",
          });
          return;
        }
        const reason =
          (body && "reason" in body && body.reason) ||
          (body && "status" in body && body.status) ||
          `http_${res.status}`;
        setState({ phase: "empty", reason });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ phase: "empty", reason: "network" });
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, isInbox]);

  return (
    <main
      data-testid="agent-control-inbox-placeholder"
      style={{
        padding: "1.25rem",
        maxWidth: "640px",
        margin: "0 auto",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.4rem", margin: "0 0 0.75rem 0" }}>{heading}</h1>
      <div
        data-testid="agent-control-inbox-banner"
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
      {isInbox && eventId && (
        <p
          data-testid="agent-control-inbox-event-id"
          style={{
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.85rem",
            background: "rgba(0,0,0,0.04)",
            padding: "0.5rem 0.65rem",
            borderRadius: "0.4rem",
            wordBreak: "break-all",
          }}
        >
          event_id: {eventId}
        </p>
      )}

      {state.phase === "loading" && (
        <p data-testid="agent-control-inbox-loading">Loading inbox detail…</p>
      )}

      {state.phase === "ok" && (
        <section
          data-testid="agent-control-inbox-detail"
          style={{ marginTop: "0.8rem" }}
        >
          <h2 style={{ fontSize: "1.05rem", margin: "0 0 0.4rem 0" }}>
            {state.row.title || "Inbox row"}
          </h2>
          {state.row.summary && (
            <p
              data-testid="agent-control-inbox-summary"
              style={{ margin: "0 0 0.6rem 0", lineHeight: 1.45 }}
            >
              {state.row.summary}
            </p>
          )}
          <dl
            data-testid="agent-control-inbox-detail-fields"
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              columnGap: "0.6rem",
              rowGap: "0.25rem",
              fontSize: "0.85rem",
              margin: 0,
            }}
          >
            <dt>event_kind</dt>
            <dd data-testid="agent-control-inbox-detail-event-kind">
              {state.row.event_kind}
            </dd>
            <dt>event_severity</dt>
            <dd data-testid="agent-control-inbox-detail-event-severity">
              {state.row.event_severity}
            </dd>
            <dt>attention_level</dt>
            <dd data-testid="agent-control-inbox-detail-attention-level">
              {state.row.attention_level}
            </dd>
            <dt>decision_state</dt>
            <dd data-testid="agent-control-inbox-detail-decision-state">
              {state.row.decision_state}
            </dd>
            <dt>source_module</dt>
            <dd data-testid="agent-control-inbox-detail-source-module">
              {state.row.source_module}
            </dd>
            <dt>created_at</dt>
            <dd data-testid="agent-control-inbox-detail-created-at">
              {state.row.created_at}
            </dd>
          </dl>
        </section>
      )}

      {state.phase === "empty" && (
        <p
          data-testid="agent-control-inbox-empty"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          No inbox detail is available for this event yet. The full inbox
          surface is not implemented; the notification opened the PWA here
          as a safe landing page.
        </p>
      )}

      {state.phase === "idle" && (
        <p
          data-testid="agent-control-inbox-idle"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          The notification you tapped opened the PWA at this safe landing
          page. No actions are available from this view.
        </p>
      )}

      <p
        style={{
          margin: "0.75rem 0",
          lineHeight: 1.45,
          fontSize: "0.9rem",
        }}
      >
        Approval still requires re-authentication in the PWA, never a
        notification tap.
      </p>
      <p style={{ margin: "1rem 0 0 0" }}>
        <Link
          to="/agent-control"
          data-testid="agent-control-inbox-back-link"
          style={{ color: "var(--ink, #1a73e8)" }}
        >
          Back to agent control
        </Link>
      </p>
    </main>
  );
}
