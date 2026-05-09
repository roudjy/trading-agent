# Push Subscription Store + API — N2b-2a (backend, unwired)

> **Status:** Implemented (backend-only, **unwired**, **no real
> push**).
>
> **Modules:**
> - [`reporting/push_subscription_store.py`](../../reporting/push_subscription_store.py) — pure-stdlib subscription store
> - [`dashboard/api_push_subscribe.py`](../../dashboard/api_push_subscribe.py) — Flask blueprint (NOT yet wired)
>
> **Runtime config (gitignored):**
> - `config/web_push_subscriptions.json` — active subscriptions
> - `config/web_push_vapid_public.txt` — VAPID public key (text)
>
> **Authority:** development-governance backend-only.
> N2b-2a sends no real push and grants no agent any new authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
> `dashboard/dashboard.py` is **unchanged** in this PR. `frontend/**`
> is **unchanged** in this PR.

---

## 1. Purpose

N2b-2a adds the backend storage primitive and the Flask blueprint
required for the future PWA Web Push subscription surface. The
blueprint is fully implemented and unit-tested on a fresh Flask app,
but it is **not wired into `dashboard/dashboard.py`**. Wiring is a
single-line change (`register_push_subscribe_routes(app)`) that lands
later in N2b-2b, behind explicit operator approval — the dashboard's
central wiring file is `dashboard_wiring` per
[`execution_authority.md`](execution_authority.md), which classifies
edits to it as `NEEDS_HUMAN`.

This means: at runtime today, after this PR merges, **nothing
operator-visible changes**. The Python module exists; the Flask
blueprint exists; the gitignored runtime-config paths are recognised.
No HTTP route is reachable through the live dashboard. No
subscription is ever stored automatically. No push is ever sent —
real, stub, or otherwise. The N2b-2a PR is, at runtime, equivalent to
a no-op.

---

## 2. Hard constraints

N2b-2a, in this PR and at runtime, must not:

- send a real push (Web Push, APNs, FCM, Telegram, email, SMS, anything);
- open a network socket;
- import a Web Push library;
- read a VAPID **private** key (the literal env name
  `WEB_PUSH_VAPID_PRIVATE_KEY` does not appear in N2b-2a source);
- write to `dashboard/dashboard.py`;
- write to `frontend/**`;
- add a service worker;
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
- mark any roadmap phase complete.

The module ships an AST-level forbidden-import scan and a
source-text scan to enforce the relevant bullets.

---

## 3. Closed vocabularies + bounds

Pinned in [`reporting/push_subscription_store.py`](../../reporting/push_subscription_store.py):

### Per-record schema (closed, exact, ordered)

```
endpoint
keys: {p256dh, auth}
kid
created_at
last_seen_at
label
```

### Bounds

| Bound                                   | Value                          |
| --------------------------------------- | ------------------------------ |
| `MAX_ACTIVE_SUBSCRIPTIONS`              | 16 (single-operator guard)     |
| `MAX_ENDPOINT_LEN`                      | 1024 chars                     |
| `MAX_P256DH_LEN` / `MAX_AUTH_LEN`       | 200 chars each                 |
| `MAX_KID_LEN`                           | 64 chars                       |
| `MAX_LABEL_LEN`                         | 80 chars                       |
| `_MAX_REQUEST_BYTES` (API layer)        | 8 KiB JSON request body         |

### Allowed endpoint origins (closed)

```
https://fcm.googleapis.com/                        (Chrome / Edge / Android)
https://updates.push.services.mozilla.com/         (Firefox)
https://web.push.apple.com/                        (Safari)
https://wns2-                                      (Microsoft WNS hosts)
```

Anything else is refused at register time with a
`endpoint_origin_not_allowed` warning. Expansion requires a code
change pinned by an updated test.

---

## 4. Storage path and gitignore

| Path                                       | Tracked? | Purpose                                    |
| ------------------------------------------ | -------- | ------------------------------------------ |
| `config/web_push_subscriptions.json`       | **no** (gitignored) | active subscriptions JSON envelope |
| `config/web_push_vapid_public.txt`         | **no** (gitignored) | VAPID public key (text/plain)      |
| `WEB_PUSH_VAPID_PRIVATE_KEY` (env)         | **no** (env-only, **N2b-3 only**)  | private key never in repo |

Both paths are added to `.gitignore` in this PR. A pin test asserts
neither path appears in `git ls-files`.

The store path is gitignored because:

1. The file holds operator-specific Web Push endpoint URLs.
2. Any `kid` rotation, unsubscribe, or auto-cleanup edit is
   operational state, not source-of-truth.
3. Committing it would let an attacker who briefly read the repo
   deliver pushes that look like ADE notifications.

The VAPID public key is gitignored because:

1. The keypair is per-operator, generated by an out-of-band one-shot
   script in **N2b-3** (lands later).
2. The public key is non-secret per the W3C Web Push spec, but
   committing it would couple the repo to a specific operator's
   keypair, defeating future rotation.

---

## 5. Public Python API (`reporting.push_subscription_store`)

| Function                                  | Returns                                           | Notes                                                                  |
| ----------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------- |
| `list_subscriptions()`                    | `list[dict]`                                      | pure read; empty list on first read                                    |
| `register_subscription(record)`           | `(record, warnings)`                              | idempotent on `endpoint`; refreshes `last_seen_at`; refuses on cap reached |
| `unregister_subscription(endpoint)`       | `bool`                                            | idempotent — `True` if removed, `False` if absent                       |
| `get_by_endpoint(endpoint)`               | `dict | None`                                     | pure read                                                               |
| `load_store()` / `save_store(store)`      | envelope dict / path                              | atomic write; refused for any non-sentinel path                         |
| `endpoint_hash(endpoint)`                 | `str` (sha256[:16])                               | the only operator-visible identifier in audit / log surfaces            |
| `vapid_public_present()`                  | `bool`                                            | does not read content                                                   |
| `vapid_public_text()`                     | `str | None`                                      | best-effort read; never raises                                          |

Every register / unregister / refresh call is a full atomic rewrite
of `config/web_push_subscriptions.json`. The atomic-write helper
refuses any path other than the closed sentinel.

---

## 6. Flask blueprint (`dashboard.api_push_subscribe`)

The blueprint exposes 5 routes via `register_push_subscribe_routes(app)`:

| Method | Path                          | Behaviour                                                                                                        |
| ------ | ----------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| POST   | `/api/push/subscribe`         | accepts a `PushSubscription.toJSON()`, validates closed schema, registers via the store. Returns `endpoint_hash` only — never the endpoint URL. |
| DELETE | `/api/push/unsubscribe`       | removes by `endpoint`. Idempotent. Returns `endpoint_hash` + `removed: bool`.                                    |
| GET    | `/api/push/vapid_public`      | returns `text/plain` public key, or 404 with `{"status":"not_available","error":"vapid_public_not_configured"}` |
| GET    | `/api/push/status`            | returns ONLY `count`, `last_subscribed_at`, `vapid_public_present`, `max_active_subscriptions`. **Never** endpoints or keys. |
| POST   | `/api/push/test`              | synthesizes a six-key test event payload for the existing N2b-1 stub-provider outbox; **no real push.** Returns `real_push_sent: false`. |

Every response is run through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before send. A pin test asserts the `/api/push/status` body does not
contain `endpoint`, `p256dh`, or `auth` keys.

The blueprint is **NOT** wired into `dashboard/dashboard.py` in this
PR. To activate the routes, a future operator-approved PR adds
exactly two lines to `dashboard/dashboard.py`:

```diff
+from dashboard.api_push_subscribe import register_push_subscribe_routes
 ...
+register_push_subscribe_routes(app)
```

That edit is N2b-2b territory; it is `dashboard_wiring` →
NEEDS_HUMAN per
[`execution_authority.md`](execution_authority.md). The agent may
author the PR; the operator approves the merge.

---

## 7. Authentication

Auth is provided by the existing PWA session middleware at the
dashboard wiring layer. This blueprint does not register any auth
itself; tests register the blueprint on a fresh Flask app and
exercise the routes directly. When N2b-2b lands, the existing
session middleware applies automatically.

The `/api/push/dispatch` endpoint (real Web Push) is **N2b-3 only**
and will be restricted to `127.0.0.1` by the existing nginx config.
N2b-2a does not implement that endpoint.

---

## 8. No-approval-from-notification-click guarantee

Two layers from N2b-2a's perspective:

1. **Payload layer (already merged in N2b-1):** the closed six-key
   schema contains no decision verb, no PR head SHA, no acceptance
   body, no command summary. The N2b-1 pin test
   `test_payload_contains_no_decision_verb` enforces this.
2. **Test-event helper (this PR):** `POST /api/push/test` returns a
   payload that explicitly carries `real_push_sent: false` and
   reuses the same closed-schema event; no decision verb, no diff,
   no body content.

The SW layer (the actual `notificationclick` handler that opens the
PWA at the inbox row) lands in N2b-2b alongside the frontend files.
N2b-2a ships **no service worker**, no `frontend/**` change, and
hence no path by which a notification click can do anything at all.

---

## 9. CLI / runtime

There is no new CLI. The Python store is exercised via:

- the unit tests
  ([`tests/unit/test_push_subscription_store.py`](../../tests/unit/test_push_subscription_store.py));
- the API blueprint unit tests
  ([`tests/unit/test_api_push_subscribe.py`](../../tests/unit/test_api_push_subscribe.py));
- a future N2b-2b dashboard.py wiring change (one line) that the
  operator approves.

After this PR merges, the only operator-visible artefact at runtime
is the absence of `config/web_push_subscriptions.json` (because no
PWA has subscribed yet). The dashboard route table is unchanged.

---

## 10. Authority chain summary

| Capability                                           | Today (post-N2b-1)                | After N2b-2a                                              | After N2b-2b (future, operator-approved)                  | After N2b-3 (future, operator-approved + release-gate)            |
| ---------------------------------------------------- | --------------------------------- | --------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------- |
| Compute notification-ready event                     | `notification_dispatcher`         | unchanged                                                 | unchanged                                                  | unchanged                                                          |
| Build bounded six-key payload                        | `notification_dispatch_outbox` (stub) | unchanged                                             | unchanged                                                  | unchanged                                                          |
| Read subscription store                              | does not exist                    | `reporting/push_subscription_store.py` (Python API)       | `dashboard/api_push_subscribe.py` (HTTP API, wired)       | unchanged                                                          |
| Persist a subscription                               | does not exist                    | yes via the Python API; HTTP path unwired                 | yes via the HTTP API (operator-tap-driven)                | unchanged                                                          |
| Open network socket / send real push                 | does not exist                    | does not exist                                            | does not exist (stub-only via `/api/push/test`)            | yes (single audited callable in `dashboard/api_push_dispatch.py`) |
| Touch `dashboard/dashboard.py`                       | unchanged                         | **no**                                                    | yes — one-line `register_push_subscribe_routes(app)`     | yes — one-line `register_push_dispatch_routes(app)`               |
| Touch `frontend/**`                                  | unchanged                         | **no**                                                    | yes (PushSettings.tsx, webPush.ts, sw-push.js)           | unchanged                                                          |
| Mint approval tokens                                 | does not exist                    | does not exist                                            | does not exist                                            | does not exist (N4 territory)                                      |
| Open mobile inbox row                                | does not exist                    | does not exist                                            | does not exist                                            | does not exist (N3 territory)                                      |
| Execute merge / deploy                               | operator + branch protection      | unchanged                                                 | unchanged                                                  | unchanged                                                          |
| Autonomous merge / deploy                            | **forbidden, Level 6**            | unchanged — Level 6 stays permanently disabled            | unchanged — Level 6 stays permanently disabled            | unchanged — Level 6 stays permanently disabled                     |

---

## 11. Test coverage

Pinned in
[`tests/unit/test_push_subscription_store.py`](../../tests/unit/test_push_subscription_store.py)
and
[`tests/unit/test_api_push_subscribe.py`](../../tests/unit/test_api_push_subscribe.py):

**Store-side tests:**

- subscriptions path is gitignored;
- VAPID public path is gitignored;
- neither path appears in `git ls-files`;
- empty store on first read;
- `register_subscription` writes one record;
- registering the same `endpoint` is idempotent (refreshes `last_seen_at`);
- `unregister_subscription` removes by endpoint and is idempotent;
- store caps at `MAX_ACTIVE_SUBSCRIPTIONS = 16`;
- per-record schema keys exact;
- invalid subscription shape rejected;
- atomic write refuses any path other than the closed sentinel
  `config/web_push_subscriptions.json`;
- AST forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `socket`, `urllib`, `requests`, `httpx`,
  `aiohttp`, `pywebpush`, `webpush`, `web_push`,
  `WEB_PUSH_VAPID_PRIVATE_KEY`, `subprocess`, `gh`, `git`;
- importing the store does not flip Step 5 invariants.

**API-side tests:**

- API routes register on an explicit fresh Flask app;
- `dashboard/dashboard.py` does not import `api_push_subscribe`;
- `dashboard/dashboard.py` has no `register_push_subscribe_routes`
  call;
- `/api/push/status` body redacts endpoints and keys;
- `/api/push/vapid_public` 404s cleanly when missing;
- `/api/push/test` uses the synthetic event helper only;
  `real_push_sent` is `false`;
- `POST /api/push/subscribe` accepts a valid payload;
- `POST /api/push/subscribe` rejects an invalid payload with 400;
- `DELETE /api/push/unsubscribe` is idempotent;
- request bodies > 8 KiB are refused 413;
- this doc states no real push in N2b-2a;
- this doc states "no approval from notification click alone";
- this doc states "Level 6 stays permanently disabled".

---

## 12. What N2b-2a does NOT do

- N2b-2a sends no real push.
- N2b-2a opens no network socket.
- N2b-2a reads no VAPID private key.
- N2b-2a writes no `dashboard/dashboard.py`.
- N2b-2a writes no `frontend/**` file.
- N2b-2a adds no service worker.
- N2b-2a opens no inbox row.
- N2b-2a mints no token.
- N2b-2a does not change Step 5.0 logic.
- N2b-2a does not flip `step5_implementation_allowed`.
- N2b-2a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N2b-2b (PWA UI + SW + wiring), N2b-3 (real Web Push), N3 (mobile
  approval inbox), N4 (token gate), and N5 (merge/deploy adapter)
  remain unimplemented.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. **No approval can happen
  from notification click alone.**
