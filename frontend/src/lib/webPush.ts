/**
 * N2b-2b — PWA Web Push subscription client.
 *
 * Same-origin fetch helpers for /api/push/*. No third-party push SDK.
 * No secrets are stored in the frontend — VAPID public key is fetched
 * from the backend on-demand, and the private key is never seen by
 * the frontend at all.
 *
 * Hard guarantees:
 *   - All fetches are same-origin against /api/push/*.
 *   - No third-party SDK is imported.
 *   - The service worker (`/sw-push.js`) is registered ONLY when the
 *     operator explicitly opts in via subscribeToPush(); never on
 *     module load.
 *   - subscribeToPush() refuses to proceed if Notification.permission
 *     is "denied" or if the VAPID public key is missing.
 *   - No approval verb (approve/reject/merge/deploy) is ever sent
 *     by this module.
 */

export type PushStatusOk = {
  status: "ok";
  count: number;
  last_subscribed_at: string;
  vapid_public_present: boolean;
  max_active_subscriptions: number;
};

export type PushStatusError = {
  status: "error" | "not_available";
  error?: string;
};

export type PushStatusResponse = PushStatusOk | PushStatusError;

export type SubscribeResult =
  | {
      ok: true;
      endpoint_hash: string;
      kid: string;
      label: string;
    }
  | {
      ok: false;
      reason: string;
    };

export type UnsubscribeResult =
  | { ok: true; removed: boolean }
  | { ok: false; reason: string };

export type TestPushResult =
  | {
      ok: true;
      event_id: string;
      event_kind: string;
      event_severity: string;
      open_at: string;
    }
  | { ok: false; reason: string };

const API_BASE = "/api/push";
const SW_PATH = "/sw-push.js";
const SW_SCOPE = "/agent-control/";

/**
 * Convert a base64url string into an ArrayBuffer suitable for
 * `PushManager.subscribe({ applicationServerKey })`. The VAPID
 * public key is published as base64url. PushManager requires a
 * `BufferSource`; we allocate a real `ArrayBuffer` and fill it
 * through a `Uint8Array` view, then return the underlying buffer
 * so that the function's return type is unambiguously
 * `ArrayBuffer` (the lib.dom.d.ts type for
 * `applicationServerKey`).
 *
 * Returning a `Uint8Array` directly works at runtime in most
 * browsers but trips strict TypeScript builds because
 * `Uint8Array<ArrayBufferLike>` is not assignable to
 * `BufferSource` under tighter lib.dom.d.ts types — observed in
 * the v3.15.16 deploy after PR #167.
 *
 * Exported for unit-test pinning of the return type.
 */
export function base64UrlToArrayBuffer(base64url: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buffer;
}

export async function getPushStatus(): Promise<PushStatusResponse> {
  try {
    const res = await fetch(`${API_BASE}/status`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      return { status: "not_available", error: `http_${res.status}` };
    }
    return (await res.json()) as PushStatusResponse;
  } catch (_err) {
    return { status: "not_available", error: "network" };
  }
}

export async function getVapidPublic(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/vapid_public`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "text/plain" },
    });
    if (!res.ok) return null;
    const text = await res.text();
    return text.trim() || null;
  } catch (_err) {
    return null;
  }
}

export async function subscribeToPush(): Promise<SubscribeResult> {
  if (typeof window === "undefined") {
    return { ok: false, reason: "no_window" };
  }
  if (!("serviceWorker" in navigator)) {
    return { ok: false, reason: "no_service_worker_support" };
  }
  if (!("PushManager" in window)) {
    return { ok: false, reason: "no_push_manager_support" };
  }
  if (Notification.permission === "denied") {
    return { ok: false, reason: "notification_permission_denied" };
  }
  if (Notification.permission !== "granted") {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      return { ok: false, reason: "notification_permission_not_granted" };
    }
  }
  const vapid = await getVapidPublic();
  if (!vapid) {
    return { ok: false, reason: "vapid_public_not_configured" };
  }

  let registration: ServiceWorkerRegistration;
  try {
    registration = await navigator.serviceWorker.register(SW_PATH, {
      scope: SW_SCOPE,
    });
  } catch (_err) {
    return { ok: false, reason: "sw_register_failed" };
  }

  let subscription: PushSubscription;
  try {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToArrayBuffer(vapid),
    });
  } catch (_err) {
    return { ok: false, reason: "push_subscribe_failed" };
  }

  const json = subscription.toJSON();
  const body = {
    endpoint: json.endpoint,
    keys: {
      p256dh: json.keys?.p256dh ?? "",
      auth: json.keys?.auth ?? "",
    },
    kid: "k1",
    label: "PWA",
  };

  try {
    const res = await fetch(`${API_BASE}/subscribe`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      return { ok: false, reason: `http_${res.status}` };
    }
    const payload = (await res.json()) as {
      status: string;
      endpoint_hash?: string;
      kid?: string;
      label?: string;
    };
    if (payload.status !== "ok") {
      return { ok: false, reason: "register_rejected" };
    }
    return {
      ok: true,
      endpoint_hash: payload.endpoint_hash ?? "",
      kid: payload.kid ?? "",
      label: payload.label ?? "",
    };
  } catch (_err) {
    return { ok: false, reason: "network" };
  }
}

export async function unsubscribeFromPush(): Promise<UnsubscribeResult> {
  if (typeof window === "undefined") {
    return { ok: false, reason: "no_window" };
  }
  if (!("serviceWorker" in navigator)) {
    return { ok: false, reason: "no_service_worker_support" };
  }
  let registration: ServiceWorkerRegistration | undefined;
  try {
    registration = await navigator.serviceWorker.getRegistration(SW_SCOPE);
  } catch (_err) {
    registration = undefined;
  }
  if (!registration) {
    return { ok: true, removed: false };
  }
  let endpoint = "";
  try {
    const sub = await registration.pushManager.getSubscription();
    if (sub) {
      endpoint = sub.endpoint;
      try {
        await sub.unsubscribe();
      } catch (_err) {
        // best-effort
      }
    }
  } catch (_err) {
    // best-effort
  }
  if (!endpoint) {
    return { ok: true, removed: false };
  }
  try {
    const res = await fetch(`${API_BASE}/unsubscribe`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint }),
    });
    if (!res.ok) {
      return { ok: false, reason: `http_${res.status}` };
    }
    const payload = (await res.json()) as {
      status: string;
      removed?: boolean;
    };
    return { ok: true, removed: Boolean(payload.removed) };
  } catch (_err) {
    return { ok: false, reason: "network" };
  }
}

export async function sendTestPush(): Promise<TestPushResult> {
  try {
    const res = await fetch(`${API_BASE}/test`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      return { ok: false, reason: `http_${res.status}` };
    }
    const payload = (await res.json()) as {
      status: string;
      test_event?: {
        event_id: string;
        event_kind: string;
        event_severity: string;
        open_at: string;
      };
      real_push_sent?: boolean;
    };
    if (payload.status !== "ok" || !payload.test_event) {
      return { ok: false, reason: "test_rejected" };
    }
    return {
      ok: true,
      event_id: payload.test_event.event_id,
      event_kind: payload.test_event.event_kind,
      event_severity: payload.test_event.event_severity,
      open_at: payload.test_event.open_at,
    };
  } catch (_err) {
    return { ok: false, reason: "network" };
  }
}
