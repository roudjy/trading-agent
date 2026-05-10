# PWA Push Settings — N2b-2b (subscription UI + service worker)

> **Status:** Implemented (frontend UI + service worker; backend wiring
> requires a one-line operator edit to
> `dashboard/dashboard.py`).
>
> **Modules:**
> - [`frontend/public/sw-push.js`](../../frontend/public/sw-push.js) — push service worker
> - [`frontend/src/lib/webPush.ts`](../../frontend/src/lib/webPush.ts) — same-origin subscription client
> - [`frontend/src/routes/AgentControl/PushSettings.tsx`](../../frontend/src/routes/AgentControl/PushSettings.tsx) — operator UI
>
> **Authority:** development-governance UI surface only.
> **No real Web Push is delivered in N2b-2b.** Real delivery is
> N2b-3 only and requires an env-only VAPID private key. Level 6
> stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

N2b-2b adds the PWA-side surface required to opt in / out of Web
Push notifications and exercises the already-merged N2b-2a backend
(`/api/push/*`). It also includes the one-line wiring change to
[`dashboard/dashboard.py`](../../dashboard/dashboard.py) that
activates the API blueprint.

The [`dashboard/dashboard.py`](../../dashboard/dashboard.py) file is
classified `dashboard_wiring` in
[`execution_authority.md`](execution_authority.md), which means
edits to it are `NEEDS_HUMAN`. The operator approves the merge of
this PR only after reviewing the wiring diff, which must be exactly:

```diff
+from dashboard.api_push_subscribe import register_push_subscribe_routes
 ...
+register_push_subscribe_routes(app)
```

Until that edit lands, the API routes are unreachable through the
live dashboard. The PWA degrades gracefully: `getPushStatus()`
returns `{ status: "not_available", error: "http_404" }` and the
PushSettings card displays a clear disabled state.

---

## 2. Hard constraints

N2b-2b, in this PR and at runtime, must not:

- send a real push (Web Push, APNs, FCM, Telegram, email, SMS, anything);
- create `dashboard/api_push_dispatch.py` (real-delivery endpoint);
- read `WEB_PUSH_VAPID_PRIVATE_KEY` (env-only and N2b-3 territory);
- mint approval tokens (N4 territory);
- open mobile approval inbox rows (N3 territory);
- merge or deploy (N5 / future);
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- store secrets in repo;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- accept an approval from a notification click. The SW
  `notificationclick` handler **only** opens the PWA at the inbox
  row.

---

## 3. Service worker (`frontend/public/sw-push.js`)

```text
push handler:
  - reads payload (tolerates missing JSON body)
  - bounds title to 80 chars, summary to 200 chars
  - sanitizes open_at: must start with "/agent-control/inbox" and
    contain no ".." path traversal; otherwise falls back to
    "/agent-control/inbox?event=<event_id>" or "/agent-control"
  - displays the notification with the bounded fields only

notificationclick handler:
  - closes the notification
  - opens self.clients.openWindow(open_at)
  - that is the entire interactive surface

NOT in this SW:
  - fetch
  - XMLHttpRequest
  - navigator.sendBeacon
  - postMessage
  - any decision verb (approve / reject / merge / deploy)
  - any cookie / client / cache manipulation
```

The SW is registered **only** on operator opt-in via the Push
Settings card; never automatically. Scope is `/agent-control/`.

---

## 4. Subscription client (`frontend/src/lib/webPush.ts`)

| Function                  | Purpose                                                         |
| ------------------------- | --------------------------------------------------------------- |
| `getPushStatus()`         | GET `/api/push/status`. Returns count + last_subscribed_at + vapid_public_present + max_active_subscriptions only — never endpoints/keys. |
| `getVapidPublic()`        | GET `/api/push/vapid_public`. Returns text or null on 404.      |
| `subscribeToPush()`       | Operator-tap-driven only. Requests `Notification.permission`, registers the SW at `/agent-control/`, calls `pushManager.subscribe`, POSTs the subscription to the backend. |
| `unsubscribeFromPush()`   | Calls `subscription.unsubscribe()` then DELETE the backend record. Idempotent. |
| `sendTestPush()`          | POST `/api/push/test`. Returns the synthetic six-key event; **no real push.** |

All calls are same-origin against `/api/push/*`. No third-party SDK.
No secrets in the frontend bundle.

---

## 5. PushSettings UI (`frontend/src/routes/AgentControl/PushSettings.tsx`)

| State                                | UI behaviour                                                              |
| ------------------------------------ | ------------------------------------------------------------------------- |
| Loading                              | shows "Loading…" muted text                                               |
| `vapid_public_present=false`         | Enable button is disabled; shows "VAPID public key not configured" state |
| Not subscribed                       | Disable button is hidden; Send-test-push button is disabled              |
| Subscribed                           | Enable button is disabled; Disable + Send-test-push buttons are enabled  |
| Error from `subscribeToPush`         | shows a red flash with the closed-vocab reason                            |

**Critical:** the component does not auto-subscribe on render. The
operator must tap the Enable button explicitly. Pinned by
`tests/frontend/push_settings.test.tsx`.

The component renders a fixed disclaimer at the bottom:
> Notifications open the inbox for context only. Approval requires
> re-authentication in the PWA — not a notification tap.

---

## 6. dashboard.py wiring (operator-only edit at review time)

The agent's no-touch hook prevents in-PR edits to
`dashboard/dashboard.py`. The operator adds the two lines at PR
review:

```diff
+from dashboard.api_push_subscribe import register_push_subscribe_routes
 ...
+register_push_subscribe_routes(app)
```

The diff guard test
([`tests/unit/test_dashboard_dashboard_one_line_wiring.py`](../../tests/unit/test_dashboard_dashboard_one_line_wiring.py))
runs in two modes:

- if the import is **absent** in `dashboard/dashboard.py`, the test
  **skips** with a clear message saying the operator must add the
  wiring;
- if the import is **present**, the test asserts that the diff
  consists of exactly one new import + one new register call, with
  zero existing registrations removed or reordered.

This means CI passes today; the operator adds the two lines; CI
re-runs and now actively enforces the exact two-line shape. After
merge, the routes are live and the PWA exits its degraded state.

---

## 7. Authentication

Auth is provided by the existing PWA session middleware that already
wraps `/api/agent-control/*` and `/api/approval-inbox/*`. N2b-2b
adds no new auth surface. The blueprint becomes session-protected as
soon as the wiring lands.

---

## 8. No-approval-from-notification-click guarantee

Three independent layers, each pin-tested:

1. **Payload layer (already merged in N2b-1):** the closed six-key
   schema contains no decision verb. `_payload_passes_no_decision_verb`
   refuses any payload containing `approve`, `reject`, `merge`, or
   `deploy`.
2. **SW layer (this PR):** the `notificationclick` handler does
   `clients.openWindow(open_at)` and returns. No `fetch`, no
   `XMLHttpRequest`, no `navigator.sendBeacon`, no decision verb in
   any code path. Pinned by
   `tests/frontend/sw_push_click.test.ts`.
3. **PWA-route layer (this PR):** PushSettings does not render any
   approve/reject/merge/deploy button. The disclaimer text reminds
   the operator that approval requires re-authentication. The future
   N3 inbox detail (separate slice) is where evidence lives;
   approval still requires the future N4 token, never a notification
   tap.

---

## 9. Test coverage

Pinned in:

- [`tests/unit/test_dashboard_dashboard_one_line_wiring.py`](../../tests/unit/test_dashboard_dashboard_one_line_wiring.py)
  — wiring diff guard (dual-mode skip-or-enforce).
- [`tests/unit/test_api_push_subscribe.py`](../../tests/unit/test_api_push_subscribe.py)
  — API blueprint behaviour (already passing in N2b-2a).
- [`tests/unit/test_push_subscription_store.py`](../../tests/unit/test_push_subscription_store.py)
  — store behaviour (already passing in N2b-2a).
- `frontend/src/test/PushSettings.test.tsx` — PushSettings UI:
  no auto-subscribe, VAPID-missing disabled state, unsubscribe
  visible when subscribed, send-test-push hits `/api/push/test`,
  no decision-verb DOM, flash messaging.
- `frontend/src/test/sw_push_click.test.ts` — SW source contract:
  no `fetch`, no `XMLHttpRequest`, no `sendBeacon`, no decision-verb
  literal, `notificationclick` only opens window, `open_at`
  sanitiser refuses external URLs and path traversal.

---

## 10. What N2b-2b does NOT do

- N2b-2b sends no real push.
- N2b-2b does not create `dashboard/api_push_dispatch.py`.
- N2b-2b does not read any VAPID private key.
- N2b-2b adds no third-party push SDK.
- N2b-2b mints no approval token.
- N2b-2b opens no inbox row (N3 territory).
- N2b-2b does not change Step 5.0 logic.
- N2b-2b does not flip `step5_implementation_allowed`.
- N2b-2b does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N2b-3 (real Web Push), N3 (mobile approval inbox), N4 (token
  gate), and N5 (merge/deploy adapter) remain unimplemented.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. **No approval can happen
  from notification click alone.**
