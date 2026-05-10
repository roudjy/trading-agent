/**
 * N2b-2b — Agent Control Push Settings card.
 *
 * Operator UI for opting in/out of PWA Web Push notifications. Wires
 * the already-merged N2b-2a backend (`/api/push/*`) and the new
 * `/sw-push.js` service worker.
 *
 * Hard guarantees:
 *   - Does NOT auto-subscribe on render. The operator must tap
 *     the Enable button explicitly.
 *   - Shows a clear "VAPID public key not configured" disabled
 *     state when the backend reports vapid_public_present=false.
 *   - The Disable button is visible whenever a subscription is
 *     registered.
 *   - The Send-test-push button calls /api/push/test only — N2b-2b
 *     does NOT deliver a real Web Push (that's N2b-3).
 *   - No approval verb (approve/reject/merge/deploy) is rendered
 *     anywhere in this component.
 */

import { useCallback, useEffect, useState } from "react";

import {
  getPushStatus,
  sendTestPush,
  subscribeToPush,
  unsubscribeFromPush,
  type PushStatusResponse,
  type SubscribeResult,
  type TestPushResult,
  type UnsubscribeResult,
} from "../../lib/webPush";

type PushFlash =
  | { kind: "ok"; message: string }
  | { kind: "error"; message: string }
  | null;

function isOkStatus(s: PushStatusResponse): s is Extract<
  PushStatusResponse,
  { status: "ok" }
> {
  return s.status === "ok";
}

export function PushSettings(): JSX.Element {
  const [status, setStatus] = useState<PushStatusResponse | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [flash, setFlash] = useState<PushFlash>(null);

  const refresh = useCallback(async () => {
    const next = await getPushStatus();
    setStatus(next);
  }, []);

  // Refresh status on mount. CRITICAL: we never auto-subscribe.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onEnable = useCallback(async () => {
    setBusy(true);
    setFlash(null);
    const res: SubscribeResult = await subscribeToPush();
    if (res.ok) {
      setFlash({
        kind: "ok",
        message: `Subscribed (${res.endpoint_hash.slice(0, 8)}…).`,
      });
    } else {
      setFlash({ kind: "error", message: `Enable failed: ${res.reason}` });
    }
    await refresh();
    setBusy(false);
  }, [refresh]);

  const onDisable = useCallback(async () => {
    setBusy(true);
    setFlash(null);
    const res: UnsubscribeResult = await unsubscribeFromPush();
    if (res.ok) {
      setFlash({
        kind: "ok",
        message: res.removed ? "Unsubscribed." : "No active subscription.",
      });
    } else {
      setFlash({ kind: "error", message: `Disable failed: ${res.reason}` });
    }
    await refresh();
    setBusy(false);
  }, [refresh]);

  const onTest = useCallback(async () => {
    setBusy(true);
    setFlash(null);
    const res: TestPushResult = await sendTestPush();
    if (res.ok) {
      setFlash({
        kind: "ok",
        message: `Test event ${res.event_id} (no real push sent).`,
      });
    } else {
      setFlash({ kind: "error", message: `Test failed: ${res.reason}` });
    }
    setBusy(false);
  }, []);

  const okStatus = status && isOkStatus(status) ? status : null;
  const vapidConfigured = okStatus ? okStatus.vapid_public_present : false;
  const subscribed = (okStatus?.count ?? 0) > 0;
  const enableDisabled = !vapidConfigured || busy || subscribed;
  const disableHidden = !subscribed;
  const testDisabled = !subscribed || busy;

  return (
    <section
      className="agent-control-card push-settings"
      aria-labelledby="push-settings-heading"
      data-testid="push-settings-card"
    >
      <h2 id="push-settings-heading">Push Notifications</h2>
      {!status && <p className="muted">Loading…</p>}
      {status && status.status !== "ok" && (
        <p className="status-error" data-testid="push-status-error">
          Push status unavailable
          {"error" in status && status.error ? `: ${status.error}` : ""}.
        </p>
      )}
      {okStatus && (
        <dl className="push-status">
          <dt>Status</dt>
          <dd data-testid="push-subscribed-state">
            {subscribed ? `Subscribed (${okStatus.count})` : "Not subscribed"}
          </dd>
          <dt>Last subscribed at</dt>
          <dd data-testid="push-last-subscribed-at">
            {okStatus.last_subscribed_at || "—"}
          </dd>
          <dt>VAPID public key</dt>
          <dd data-testid="push-vapid-state">
            {vapidConfigured
              ? "configured"
              : "not configured (operator must generate keypair before enabling)"}
          </dd>
        </dl>
      )}
      <div className="push-actions">
        <button
          type="button"
          onClick={() => void onEnable()}
          disabled={enableDisabled}
          data-testid="push-enable-button"
          aria-label="Enable push notifications"
        >
          Enable push notifications
        </button>
        {!disableHidden && (
          <button
            type="button"
            onClick={() => void onDisable()}
            disabled={busy}
            data-testid="push-disable-button"
            aria-label="Disable push notifications"
          >
            Disable push notifications
          </button>
        )}
        <button
          type="button"
          onClick={() => void onTest()}
          disabled={testDisabled}
          data-testid="push-test-button"
          aria-label="Send test push (no real push)"
        >
          Send test push
        </button>
      </div>
      {flash && (
        <p
          className={`push-flash push-flash-${flash.kind}`}
          data-testid="push-flash"
          role="status"
        >
          {flash.message}
        </p>
      )}
      <p className="push-disclaimer">
        Notifications open the inbox for context only. Approval requires
        re-authentication in the PWA — not a notification tap.
      </p>
    </section>
  );
}

export default PushSettings;
