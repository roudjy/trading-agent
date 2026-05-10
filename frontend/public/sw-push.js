/**
 * N2b-2b — JvR Agent Control PWA push service worker.
 *
 * Hard guarantees:
 *   - The SW handles ONLY ``push`` and ``notificationclick`` events.
 *   - ``notificationclick`` ONLY closes the notification and opens
 *     the PWA at ``/agent-control/inbox?event=<event_id>``. Anything
 *     else is refused.
 *   - The SW NEVER calls ``fetch``, ``XMLHttpRequest``, or
 *     ``navigator.sendBeacon``. There is no path by which a click
 *     can post an action.
 *   - The SW NEVER trusts an arbitrary URL from the push payload.
 *     Only ``open_at`` strings starting with ``/agent-control/inbox``
 *     are honoured; anything else falls back to the safe default.
 *   - The SW never imports a Web Push library, never references
 *     VAPID keys, never reads cookies, never enumerates clients.
 *
 * No approval can happen from a notification click alone. The click
 * opens the PWA at the inbox row; the operator must read evidence
 * and re-authenticate to act.
 */

const SAFE_OPEN_AT_PREFIX = "/agent-control/inbox";
const FALLBACK_URL = "/agent-control";
const MAX_TITLE_LEN = 80;
const MAX_SUMMARY_LEN = 200;

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  /** @type {{ event_id?: string, title?: string, summary?: string, open_at?: string }} */
  let data = {};
  try {
    if (event.data) {
      data = event.data.json();
    }
  } catch (_err) {
    data = {};
  }
  const title = bound(data.title || "ADE", MAX_TITLE_LEN);
  const body = bound(data.summary || "", MAX_SUMMARY_LEN);
  const eventId = typeof data.event_id === "string" ? data.event_id : "";
  const openAt = sanitizeOpenAt(data.open_at, eventId);

  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      tag: eventId || undefined,
      data: { event_id: eventId, open_at: openAt },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const openAt = sanitizeOpenAt(data.open_at, data.event_id);
  event.waitUntil(self.clients.openWindow(openAt));
});

function bound(s, max) {
  if (typeof s !== "string") return "";
  return s.length <= max ? s : s.slice(0, max);
}

/**
 * Refuse any open_at that does not start with /agent-control/inbox.
 * No external URLs are honoured. No path traversal is honoured.
 * Falls back to /agent-control.
 */
function sanitizeOpenAt(candidate, eventId) {
  if (typeof candidate !== "string" || !candidate) {
    return safeInboxUrl(eventId);
  }
  if (!candidate.startsWith(SAFE_OPEN_AT_PREFIX)) {
    return safeInboxUrl(eventId);
  }
  if (candidate.includes("..")) {
    return safeInboxUrl(eventId);
  }
  return candidate;
}

function safeInboxUrl(eventId) {
  if (typeof eventId === "string" && eventId.length > 0) {
    return SAFE_OPEN_AT_PREFIX + "?event=" + encodeURIComponent(eventId);
  }
  return FALLBACK_URL;
}
