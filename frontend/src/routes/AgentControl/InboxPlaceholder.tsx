/**
 * AgentControlInboxPlaceholder
 * ----------------------------
 *
 * Read-only landing page for ``/agent-control/inbox?event=<event_id>``
 * deep-links opened from the Web Push service worker's
 * ``notificationclick`` handler. The notification click is constrained
 * to this prefix by the SW sanitiser; this placeholder gives the
 * operator a safe destination until the real N3c inbox-detail UI
 * ships.
 *
 * Hard guarantees enforced by the unit test:
 *   - Renders the bounded ``event_id`` query parameter when present.
 *   - Contains NO ``approve`` / ``reject`` / ``merge`` / ``deploy``
 *     button, action, or text. Approval still requires the future N4
 *     token gate, never a notification tap.
 *   - Performs NO ``fetch`` / ``XMLHttpRequest`` / ``navigator.sendBeacon``
 *     calls. Strictly read-only.
 *   - Provides a ``<Link>`` back to ``/agent-control`` so the operator
 *     can reach the existing standalone surface.
 *
 * No real evidence is shown — that lives in the not-yet-implemented
 * N3c inbox detail. The placeholder is intentionally bland.
 */

import { Link, useLocation, useSearchParams } from "react-router-dom";

const MAX_EVENT_ID_LEN = 64;

function boundedEventId(raw: string | null): string {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  // Allow only the safe character set the N2b-1 outbox event_ids use.
  const safe = trimmed.replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_EVENT_ID_LEN);
}

export function AgentControlInboxPlaceholder() {
  const location = useLocation();
  const [search] = useSearchParams();
  const eventId = boundedEventId(search.get("event"));
  const isInbox = location.pathname.startsWith("/agent-control/inbox");
  const heading = isInbox ? "Inbox notification" : "Agent control";

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
      <h1 style={{ fontSize: "1.4rem", margin: "0 0 0.75rem 0" }}>
        {heading}
      </h1>
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
      <p style={{ margin: "0.75rem 0", lineHeight: 1.45 }}>
        The notification you tapped opened the PWA at this safe landing
        page. The inbox-detail surface is not implemented yet; no
        actions are available from this view.
      </p>
      <p style={{ margin: "0.75rem 0", lineHeight: 1.45, fontSize: "0.9rem" }}>
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
