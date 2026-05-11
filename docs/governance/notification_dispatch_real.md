# Real Web Push delivery — N2b-3 (N2b-3a adapter + N2b-3b internal-only delivery)

> **Status:** N2b-3a (mocked-transport adapter) implemented.
> N2b-3b (real Web Push HTTP transport + internal-only operator
> dispatch endpoint) implemented, **unwired in `dashboard/dashboard.py`**
> and gated by:
>
> 1. The operator setting the env-only VAPID private key on the VPS
>    (`WEB_PUSH_VAPID_PRIVATE_KEY` + `WEB_PUSH_VAPID_SUBJECT`).
> 2. The optional `pywebpush` runtime dependency being installed on
>    the VPS.
> 3. The operator-only two-line wiring diff in
>    `dashboard/dashboard.py` (the no-touch hook blocks the agent
>    from editing that file).
> 4. nginx restricting `/api/push/dispatch` to `127.0.0.1` at the
>    edge (operator infra change).
>
> Until all four conditions hold, N2b-3b is a no-op at runtime.
> Real Web Push delivery, when enabled, is **notification delivery
> only** — never approval, never merge, never deploy.
>
> **Modules:**
> - [`reporting/web_push_dispatch_adapter.py`](../../reporting/web_push_dispatch_adapter.py) — N2b-3a envelope + outcome classifier (mocked transport)
> - [`reporting/web_push_real_transport.py`](../../reporting/web_push_real_transport.py) — N2b-3b env-gated, lazy-imported real transport
> - [`dashboard/api_push_dispatch.py`](../../dashboard/api_push_dispatch.py) — N2b-3b internal-only operator dispatch endpoint (UNWIRED)
>
> **Authority:** development-governance read-only.
> N2b-3 grants ADE **zero** new write authority over trading code,
> never mints approval tokens, never opens an inbox row, never
> merges, and never deploys. Level 6 stays permanently disabled per
> ADR-015 §Doctrine 1.

---

## 1. Purpose

N2b-3 is the **real-delivery** half of the Push Notification Engine.
The split:

| Slice  | Title                                                             | Network call? | Operator action required?                                              |
| ------ | ----------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------- |
| **N2b-3a** | Mocked-transport dispatch adapter                             | **no**        | none                                                                   |
| **N2b-3b** | Real HTTP transport + internal-only operator dispatch route | yes (operator-triggered only) | yes — VAPID env + `pywebpush` install + nginx 127.0.0.1 lock + two-line wiring diff |

N2b-3a sends no real push by itself (it is the mocked-transport
adapter; tests inject a synthetic transport). N2b-3b builds on top:

1. A single env-gated, lazy-imported real-transport callable
   (`reporting/web_push_real_transport.py`).
2. A single internal-only Flask blueprint
   (`dashboard/api_push_dispatch.py`) exposing exactly one route:
   `POST /api/push/dispatch`. The blueprint is **NOT wired into**
   `dashboard/dashboard.py` in this PR — wiring is the operator's
   two-line diff.

---

## 2. Hard constraints

N2b-3a + N2b-3b, in this PR and at runtime, must not:

- send a real push without operator-controlled configuration in place;
- open a network socket unless **all** of (env-set, `pywebpush`
  installed, wired, loopback-only request) are true;
- import a Web Push library at module-load time (`pywebpush` is
  lazy-imported inside the transport call);
- log raw VAPID private key, public key, endpoint URL, or key
  material;
- write to `dashboard/dashboard.py`;
- write to `frontend/**`;
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
- store secrets in the repo;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- accept an approval from a notification click.

The adapter ships its own AST-level forbidden-import scan and
source-text scan. The transport module ships a source-text scan that
forbids any other module from referencing
`WEB_PUSH_VAPID_PRIVATE_KEY`. The dispatch blueprint ships
source-text and AST scans that forbid `subprocess`, `gh`, `git`,
direct Web Push library imports, and decision verbs.

---

## 3. Closed vocabularies

Pinned in
[`reporting/web_push_dispatch_adapter.py`](../../reporting/web_push_dispatch_adapter.py)
and
[`reporting/web_push_real_transport.py`](../../reporting/web_push_real_transport.py):

### `dispatch_outcome` (6 values, owned by N2b-3a)

| Value                       | Meaning                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `sent`                      | provider returned 2xx                                                    |
| `drop_subscription`         | provider returned 410 — subscription is dead, caller removes it          |
| `failed_provider`           | 4xx other than 410 — payload or VAPID mismatch                           |
| `retry`                     | 5xx or transport_error — try again with backoff                          |
| `skipped_no_subscription`   | record had no subscription record to deliver to                          |
| `skipped_invalid_record`    | record was missing `event_id` or otherwise malformed                     |

### `provider_status_class` (6 values, owned by N2b-3a)

```
2xx  410  4xx_other  5xx  transport_error  unknown
```

### `error_class` (5 values, owned by N2b-3b real transport)

| Value                  | Meaning                                                                            |
| ---------------------- | ---------------------------------------------------------------------------------- |
| `ok`                   | the provider returned an HTTP response (status_code is set)                        |
| `config_missing`       | one or both VAPID env vars are absent at call time                                 |
| `library_missing`      | the optional `pywebpush` dependency is not importable on the VPS                   |
| `invalid_envelope`     | the envelope failed defense-in-depth shape validation                              |
| `transport_exception` | `pywebpush` raised an unexpected exception, or returned no status code             |

Every error_class except `ok` produces ``status_code=None`` in the
transport result, which the adapter classifies as `transport_error`
→ outcome `retry`.

### Transport-result envelope (closed, exact)

```
status_code   (int | None)
error_class   (one of ERROR_CLASSES)
```

### Dispatch-summary record (closed, exact, ordered)

The dispatch endpoint writes per-attempt rows to
`logs/notification_dispatch_real/latest.json` with **only** these
fields — never the endpoint URL, never key material:

```
event_id
endpoint_hash
outcome
provider_status_class
provider_status_code
attempted_at
```

---

## 4. Decoupled transport (N2b-3a)

`dispatch_one(record=..., subscription=..., transport=...)` requires
the caller to supply the transport callable. **There is no default.**
Tests inject a synthetic transport; production wiring in N2b-3b uses
`reporting.web_push_real_transport.make_transport_for_subscription(...)`.

Outcome classification (unchanged from N2b-3a):

| Provider response                   | `provider_status_class` | `outcome`            |
| ----------------------------------- | ----------------------- | -------------------- |
| 2xx                                 | `2xx`                   | `sent`               |
| 410                                 | `410`                   | `drop_subscription`  |
| 4xx other than 410                  | `4xx_other`             | `failed_provider`    |
| 5xx                                 | `5xx`                   | `retry`              |
| Transport raised exception          | `transport_error`       | `retry`              |
| Other (e.g. status_code=None)       | `unknown`               | `failed_provider`    |

---

## 5. Real transport (N2b-3b)

`reporting.web_push_real_transport` exposes three public symbols:

| Symbol                                    | Purpose                                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `is_configured()`                         | Boolean predicate — True iff both VAPID env vars are present and non-empty. Never echoes values. |
| `make_transport()`                        | Returns a `Transport` callable that exercises env/library guards only (returns `invalid_envelope` on any real envelope — keys are not in the adapter envelope). Reserved for tests. |
| `make_transport_for_subscription(*, subscription)` | Returns a per-subscription closure that performs the real Web Push request via `pywebpush`. The closure captures `subscription.keys.{p256dh,auth}` and re-reads the env at call time. |

The real send call:

1. Re-reads `WEB_PUSH_VAPID_PRIVATE_KEY` and `WEB_PUSH_VAPID_SUBJECT`
   from env at call time (honours a rotation without restart).
2. Validates the envelope shape against the closed key set.
3. Confirms the envelope's `url` matches the subscription's
   `endpoint` (defense in depth against caller mix-up).
4. Lazy-imports `pywebpush`. Missing dependency → `library_missing`.
5. Calls `pywebpush.webpush(subscription_info=..., data=...,
   vapid_private_key=..., vapid_claims={"sub": subject}, ttl=...)`.
6. Returns the closed `{status_code, error_class}` envelope.

The transport NEVER raises; it classifies every failure mode.

---

## 6. Dispatch endpoint (N2b-3b)

`dashboard.api_push_dispatch` exposes one route:

| Method | Path                       | Behaviour                                                                                                                                                                                  |
| ------ | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| POST   | `/api/push/dispatch`       | reads `logs/notification_dispatch_outbox/latest.json`, filters records with `outbound_delivery_intent=="sent"`, and dispatches each (record × subscription) via the real transport. Writes a redacted summary to `logs/notification_dispatch_real/latest.json`. |

Hard gates, in order, before any dispatch is attempted:

1. **Loopback gate** — request must come from `127.0.0.1` or `::1`,
   else HTTP 403 `remote_not_loopback`. nginx is expected to enforce
   the same restriction at the edge; the Python check is defense in
   depth.
2. **Body-size gate** — body > 1 KiB → 413 `payload_too_large`.
3. **Configuration gate** — `web_push_real_transport.is_configured()`
   must return True, else HTTP 503 `configuration_missing`.

On any `drop_subscription` outcome the endpoint calls
`push_subscription_store.unregister_subscription(endpoint)`.

The response body is run through
`reporting.agent_audit_summary.assert_no_secrets` and contains only
counts + per-attempt rows with `endpoint_hash` (never the endpoint
URL, never key material).

**The blueprint is NOT wired into `dashboard/dashboard.py` in this
PR.** Wiring is the two-line operator diff:

```diff
+from dashboard.api_push_dispatch import register_push_dispatch_routes
 ...
+register_push_dispatch_routes(app)
```

The same skip-or-enforce dual-mode pin pattern used for N2b-2b
applies: until the operator adds the two lines, the wiring pin tests
return early; once added, they actively enforce the exact shape.

---

## 7. Authority chain summary

| Capability                               | Today (post-N2b-3a) | After N2b-3b (this PR, unwired) | After operator wiring + env + nginx                          |
| ---------------------------------------- | ------------------- | ------------------------------- | ------------------------------------------------------------- |
| Compute notification-ready event         | N2a                 | unchanged                       | unchanged                                                     |
| Build bounded six-key payload            | N2b-1 stub          | unchanged                       | unchanged                                                     |
| Build Web Push HTTP envelope             | N2b-3a              | unchanged                       | unchanged                                                     |
| Open network socket / send a real push   | does not exist      | **exists but disabled** (env unset, blueprint unwired, dependency optional) | yes — single audited callable in `reporting/web_push_real_transport.py`, invoked only by `dashboard/api_push_dispatch.py` |
| Sign VAPID JWT                           | does not exist      | does not exist (env unset)      | yes — via env-only `WEB_PUSH_VAPID_PRIVATE_KEY`              |
| Mint approval tokens                     | does not exist      | does not exist                  | does not exist (N4 territory)                                 |
| Open mobile inbox row                    | does not exist      | does not exist                  | does not exist (N3 territory)                                 |
| Execute merge / deploy                   | operator + branch protection | unchanged              | unchanged                                                     |
| Autonomous merge / deploy                | **forbidden, Level 6** | unchanged — Level 6 stays permanently disabled | unchanged — Level 6 stays permanently disabled               |

N2b-3b grants ADE **zero** new write authority over trading code,
opens **zero** new approval/merge/deploy paths, and ships **zero**
secret-in-repo code. The single real-push capability is gated by
four independent operator-controlled signals (env, library, nginx,
wiring).

---

## 8. Operator setup checklist

Before the dispatch endpoint can deliver a real push, the operator
must complete these one-shot setup steps on the VPS:

1. **Generate a VAPID keypair** (one-shot, agent prepares the script
   on operator request; the operator runs it):

   ```bash
   python -c "from py_vapid import Vapid01; v = Vapid01(); v.generate_keys(); v.save_key('config/web_push_vapid_private.pem'); v.save_public_key('config/web_push_vapid_public.txt'); print('done')"
   ```

   Write the public key text to `config/web_push_vapid_public.txt`
   (gitignored). Keep the private key out of the repo entirely;
   re-encode it as the env-var value (see step 2).

2. **Set the env vars** in the systemd unit override or
   `/etc/trading-agent.env` (outside the repo):

   ```
   WEB_PUSH_VAPID_PRIVATE_KEY=<base64url-or-pem-of-private-key>
   WEB_PUSH_VAPID_SUBJECT=mailto:joeryvanrooij@gmail.com
   ```

3. **Install the optional runtime dependency** on the VPS:

   ```bash
   pip install pywebpush
   ```

4. **Restrict the dispatch route to 127.0.0.1** in the nginx config
   (defense in depth on top of the Python loopback check):

   ```nginx
   location = /api/push/dispatch {
       allow 127.0.0.1;
       allow ::1;
       deny all;
       proxy_pass http://127.0.0.1:8050;
   }
   ```

5. **Authorise the two-line wiring diff** in
   `dashboard/dashboard.py` (operator commits; the agent prepares
   the PR):

   ```diff
   +from dashboard.api_push_dispatch import register_push_dispatch_routes
    ...
   +register_push_dispatch_routes(app)
   ```

6. **Verify**:

   ```bash
   curl -sI http://127.0.0.1:8050/api/push/vapid_public
   # → 200 (vapid_public_present=true via /api/push/status)
   curl -sX POST http://127.0.0.1:8050/api/push/dispatch
   # → 200 with a JSON summary; or 503 configuration_missing; or 403 remote_not_loopback
   ```

Until all six steps are done, the dispatch endpoint stays a no-op.

---

## 9. Test coverage

Pinned in:

- [`tests/unit/test_web_push_dispatch_adapter.py`](../../tests/unit/test_web_push_dispatch_adapter.py)
  — N2b-3a envelope + outcome classifier + closed vocabularies.
- [`tests/unit/test_web_push_real_transport.py`](../../tests/unit/test_web_push_real_transport.py)
  — env gate, lazy-import gate, envelope validation, mocked
  `pywebpush` call, transport-result envelope shape, no secret leak,
  source-text scans.
- [`tests/unit/test_api_push_dispatch.py`](../../tests/unit/test_api_push_dispatch.py)
  — method set (POST only), loopback gate (403 from non-loopback),
  env gate (503 from no env), body-size gate (413), happy path with
  injected mock transport factory, 410 → unregister call, summary
  redaction (no endpoint URLs, no keys, no decision verbs), atomic
  sentinel-restricted write, AST + source-text guard scans.
- [`tests/unit/test_dashboard_dashboard_one_line_wiring.py`](../../tests/unit/test_dashboard_dashboard_one_line_wiring.py)
  — N2b-2b skip-or-enforce wiring pin (unchanged) + a new
  skip-or-enforce pin for the N2b-3b dispatch wiring (until the
  operator adds the two lines, the pin returns early; once added,
  the file must contain EXACTLY one import + one register call,
  with all existing registrations preserved).

---

## 10. What N2b-3b does NOT do

- N2b-3b never sends a real push without all four operator-controlled
  signals (env, library, nginx, wiring) in place.
- N2b-3b does not edit `dashboard/dashboard.py` directly — the
  no-touch hook blocks the agent.
- N2b-3b does not store the VAPID private key in the repo.
- N2b-3b does not log raw endpoint URLs or key material.
- N2b-3b does not open a mobile inbox row (N3 territory remains
  future).
- N2b-3b does not mint approval tokens (N4 territory remains
  future).
- N2b-3b does not merge or deploy (N5 / future remain
  unimplemented).
- N2b-3b does not change Step 5.0 logic.
- N2b-3b does not flip `step5_implementation_allowed`.
- N2b-3b does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N3 (mobile approval inbox), N4 (token gate), and N5 (merge/deploy
  adapter) remain unimplemented.
- Level 6 stays permanently disabled. **No approval can happen from
  notification click alone.** Real push delivery, when enabled, is
  notification delivery only — never approval, never merge, never
  deploy.
