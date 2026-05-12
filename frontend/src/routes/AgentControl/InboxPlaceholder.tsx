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
 * N3c polish (v3.15.16.N3c.polish):
 *   - Distinct safe sub-states with dedicated data-testid markers
 *     for ``not_found`` / ``not_available`` / ``invalid_event_id`` /
 *     ``network`` / ``malformed`` (closed mapping). The legacy
 *     ``agent-control-inbox-empty`` testid is preserved as a parent
 *     wrapper so the existing 18 tests keep passing.
 *   - Extra bounded closed-schema fields surfaced when present
 *     (``inbox_row_id``, ``outbound_delivery_intent``, ``open_at``,
 *     ``generated_at_utc``). Defense-in-depth: ``source_id`` and
 *     ``endpoint_hash`` are intentionally NOT rendered to keep the
 *     surface free of hash-shaped data.
 *   - Semantic pills for ``event_severity`` / ``attention_level`` /
 *     ``decision_state``. Visual only — never interactive.
 *
 * Hard guarantees enforced by the unit tests:
 *   - Renders the bounded ``event_id`` query parameter when present.
 *   - When the read-only N3b API at
 *     ``/api/agent-control/mobile-inbox/detail/<event_id>`` returns a
 *     row, the closed-schema scalars are rendered: event_id,
 *     event_kind, event_severity, attention_level, decision_state,
 *     source_module, title, summary, created_at, open_at,
 *     inbox_row_id, outbound_delivery_intent.
 *   - When the API returns ``not_available`` / ``not_found`` /
 *     ``invalid_event_id`` / network failure / malformed body, the
 *     component renders the safe empty state with a precise
 *     ``data-testid="agent-control-inbox-empty-<phase>"`` marker.
 *   - Contains NO ``approve`` / ``reject`` / ``merge`` / ``deploy``
 *     button, link, or visible verb. Approval still requires the
 *     future N4 token gate, never a notification tap.
 *   - Performs ONLY a single same-origin GET to the read-only
 *     detail endpoint. No ``XMLHttpRequest``, no
 *     ``navigator.sendBeacon``, no POST / DELETE / PUT.
 *   - Provides a ``<Link>`` back to ``/agent-control``.
 *   - The banner "Read-only inbox detail. Approval actions are not
 *     implemented in this stage." is always rendered.
 */

import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

const MAX_EVENT_ID_LEN = 64;
const MAX_OPEN_AT_LEN = 200;
const DETAIL_BASE = "/api/agent-control/mobile-inbox/detail/";

function boundedEventId(raw: string | null): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const safe = trimmed.replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_EVENT_ID_LEN);
}

function boundedOpenAt(raw: string | undefined): string {
  if (typeof raw !== "string") return "";
  // Display-only sanitisation: keep anchor-safe chars; drop anything
  // that could open an attack surface in human eyes. The SW already
  // pins the open_at to the /agent-control prefix; this is a second
  // layer of belt-and-braces.
  const safe = raw.replace(/[^A-Za-z0-9_\-./?=&]/g, "");
  return safe.slice(0, MAX_OPEN_AT_LEN);
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

type EmptyPhase =
  | "not_found"
  | "not_available"
  | "invalid"
  | "network"
  | "malformed";

type FetchState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ok"; row: InboxRow; generatedAt: string }
  | { phase: "empty"; sub: EmptyPhase; reason: string };

const READ_ONLY_BANNER =
  "Read-only inbox detail. Approval actions are not implemented in this stage.";

// Map a backend status + reason + http status into one of the closed
// EmptyPhase tokens above. Defense-in-depth: anything unexpected
// collapses to ``malformed`` rather than crashing.
function emptyPhaseFor(
  status: string | undefined,
  reason: string | undefined,
  httpStatus: number,
): EmptyPhase {
  if (status === "not_found") return "not_found";
  if (status === "invalid_event_id") return "invalid";
  if (status === "not_available") return "not_available";
  if (reason === "network") return "network";
  // Body said "malformed", or no parseable body at all with non-2xx
  // → treat as malformed; 5xx without body → also malformed.
  if (reason === "malformed") return "malformed";
  if (httpStatus >= 500) return "malformed";
  // Default: assume the artefact / row is simply missing.
  return "not_available";
}

// Pill tone derivation — purely visual, never interactive.
type PillTone = "ok" | "warn" | "danger" | "info" | "muted";

function severityTone(severity: string | undefined): PillTone {
  switch ((severity ?? "").toLowerCase()) {
    case "push_critical":
    case "critical":
      return "danger";
    case "push_warning":
    case "warning":
    case "warn":
      return "warn";
    case "push_info":
    case "info":
    case "informational":
      return "info";
    default:
      return "muted";
  }
}

function attentionTone(attention: string | undefined): PillTone {
  switch ((attention ?? "").toLowerCase()) {
    case "critical_attention":
      return "danger";
    case "blocked_attention":
      return "danger";
    case "needs_review":
      return "warn";
    case "informational":
      return "info";
    default:
      return "muted";
  }
}

function decisionTone(decision: string | undefined): PillTone {
  switch ((decision ?? "").toLowerCase()) {
    case "pending":
      return "warn";
    case "resolved":
      return "ok";
    case "expired":
      return "muted";
    case "dismissed":
      return "muted";
    default:
      return "muted";
  }
}

const PILL_BG: Record<PillTone, string> = {
  ok: "rgba(46, 160, 67, 0.12)",
  warn: "rgba(212, 153, 0, 0.14)",
  danger: "rgba(207, 34, 46, 0.12)",
  info: "rgba(26, 115, 232, 0.12)",
  muted: "rgba(0, 0, 0, 0.06)",
};

const PILL_FG: Record<PillTone, string> = {
  ok: "#1a7f37",
  warn: "#8c5e00",
  danger: "#a4232f",
  info: "#1255b3",
  muted: "#444",
};

function Pill({
  tone,
  label,
  testId,
}: {
  tone: PillTone;
  label: string;
  testId?: string;
}) {
  return (
    <span
      data-testid={testId}
      data-tone={tone}
      style={{
        display: "inline-block",
        padding: "0.1rem 0.45rem",
        borderRadius: "999px",
        background: PILL_BG[tone],
        color: PILL_FG[tone],
        fontSize: "0.75rem",
        fontWeight: 600,
        lineHeight: 1.4,
        letterSpacing: "0.01em",
      }}
    >
      {label}
    </span>
  );
}

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
        // not_available / not_found / invalid_event_id envelope shape.
        let body: DetailResponse | null = null;
        let parseFailed = false;
        try {
          body = (await res.json()) as DetailResponse;
        } catch {
          body = null;
          parseFailed = true;
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
          (parseFailed ? "malformed" : undefined) ||
          (body && "status" in body && body.status) ||
          `http_${res.status}`;
        const sub = emptyPhaseFor(
          body && "status" in body ? body.status : undefined,
          parseFailed ? "malformed" : reason,
          res.status,
        );
        setState({ phase: "empty", sub, reason });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ phase: "empty", sub: "network", reason: "network" });
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

          <div
            data-testid="agent-control-inbox-pills"
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.35rem",
              margin: "0 0 0.7rem 0",
            }}
          >
            {state.row.event_severity ? (
              <Pill
                tone={severityTone(state.row.event_severity)}
                label={`severity: ${state.row.event_severity}`}
                testId="inbox-pill-severity"
              />
            ) : null}
            {state.row.attention_level ? (
              <Pill
                tone={attentionTone(state.row.attention_level)}
                label={`attention: ${state.row.attention_level}`}
                testId="inbox-pill-attention"
              />
            ) : null}
            {state.row.decision_state ? (
              <Pill
                tone={decisionTone(state.row.decision_state)}
                label={`decision: ${state.row.decision_state}`}
                testId="inbox-pill-decision"
              />
            ) : null}
          </div>

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
            {state.row.inbox_row_id ? (
              <>
                <dt>inbox_row_id</dt>
                <dd
                  data-testid="agent-control-inbox-detail-inbox-row-id"
                  style={{
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, monospace",
                    wordBreak: "break-all",
                  }}
                >
                  {state.row.inbox_row_id}
                </dd>
              </>
            ) : null}
            {state.row.outbound_delivery_intent ? (
              <>
                <dt>delivery</dt>
                <dd data-testid="agent-control-inbox-detail-delivery-intent">
                  {state.row.outbound_delivery_intent}
                </dd>
              </>
            ) : null}
            {state.row.open_at ? (
              <>
                <dt>open_at</dt>
                <dd
                  data-testid="agent-control-inbox-detail-open-at"
                  style={{
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, monospace",
                    wordBreak: "break-all",
                  }}
                >
                  {boundedOpenAt(state.row.open_at)}
                </dd>
              </>
            ) : null}
          </dl>
          {state.generatedAt ? (
            <p
              data-testid="agent-control-inbox-detail-generated-at"
              style={{
                marginTop: "0.6rem",
                fontSize: "0.75rem",
                color: "rgba(0,0,0,0.55)",
              }}
            >
              generated_at_utc: <code>{state.generatedAt}</code>
            </p>
          ) : null}
        </section>
      )}

      {state.phase === "empty" && (
        <div
          data-testid="agent-control-inbox-empty"
          style={{ margin: "0.75rem 0", lineHeight: 1.45 }}
        >
          {state.sub === "not_found" && (
            <p data-testid="agent-control-inbox-empty-not-found">
              No inbox row matches this event id yet. It may have been
              resolved upstream, or the projector has advanced past it.
            </p>
          )}
          {state.sub === "not_available" && (
            <p data-testid="agent-control-inbox-empty-not-available">
              The mobile-inbox artefact is not available
              ({state.reason || "missing"}). The full inbox surface is
              not implemented; the notification opened the PWA here as
              a safe landing page.
            </p>
          )}
          {state.sub === "invalid" && (
            <p data-testid="agent-control-inbox-empty-invalid">
              The event id in this URL is not valid ({state.reason}).
              No inbox row was looked up.
            </p>
          )}
          {state.sub === "network" && (
            <p data-testid="agent-control-inbox-empty-network">
              The inbox endpoint could not be reached. Check your
              connection — no row was fetched.
            </p>
          )}
          {state.sub === "malformed" && (
            <p data-testid="agent-control-inbox-empty-malformed">
              The inbox endpoint returned an unexpected response
              ({state.reason || "malformed"}). Nothing to render.
            </p>
          )}
        </div>
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
