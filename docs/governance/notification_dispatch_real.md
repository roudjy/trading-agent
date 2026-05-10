# Real Web Push delivery — N2b-3 (design + N2b-3a adapter)

> **Status:** N2b-3a (mocked-transport adapter) implemented.
> N2b-3b (real Web Push provider call) **deferred** — needs operator
> setup of the VAPID private-key environment variable and an
> nginx 127.0.0.1 lock for `/api/push/dispatch`.
>
> **Module:** [`reporting/web_push_dispatch_adapter.py`](../../reporting/web_push_dispatch_adapter.py)
>
> **Authority:** development-governance read-only.
> N2b-3a sends no real push and grants no agent any new authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

N2b-3 is the **real-delivery** half of the Push Notification Engine.
The split:

| Slice  | Title                                                    | Network call? | Operator action required? |
| ------ | -------------------------------------------------------- | ------------- | ------------------------- |
| **N2b-3a** | Mocked-transport dispatch adapter (this PR)         | **no**        | none                      |
| **N2b-3b** | Real HTTP transport + VAPID JWT signing (deferred) | yes           | yes — VAPID env + nginx lock + key-rotation playbook |

N2b-3a builds the **HTTP envelope** that a real Web Push provider
expects (URL, headers, body metadata, kid, endpoint hash, event id)
and dispatches it through a **caller-supplied transport callable**.
There is no module-level default transport; production wiring in
N2b-3b will provide a real HTTP client via the future
`dashboard/api_push_dispatch.py`.

---

## 2. Hard constraints

N2b-3a, in this PR and at runtime, must not:

- send a real push (Web Push, APNs, FCM, Telegram, email, SMS, anything);
- open a network socket;
- import a Web Push library (`pywebpush`, `web_push`, `webpush`, etc.);
- read or create a VAPID **private** key (the env-var name does
  not appear in N2b-3a source);
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
- store secrets in repo;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- accept an approval from a notification click.

The adapter ships its own AST-level forbidden-import scan and
source-text scan to enforce the relevant bullets.

---

## 3. Closed vocabularies

Pinned in [`reporting/web_push_dispatch_adapter.py`](../../reporting/web_push_dispatch_adapter.py):

### `dispatch_outcome` (6 values)

| Value                       | Meaning                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `sent`                      | provider returned 2xx                                                    |
| `drop_subscription`         | provider returned 410 — subscription is dead, caller should remove it    |
| `failed_provider`           | 4xx other than 410 — payload or VAPID mismatch                           |
| `retry`                     | 5xx or transport_error — try again with backoff                          |
| `skipped_no_subscription`   | record had no subscription record to deliver to                          |
| `skipped_invalid_record`    | record was missing `event_id` or otherwise malformed                     |

### `provider_status_class` (6 values)

```
2xx  410  4xx_other  5xx  transport_error  unknown
```

### Envelope schema (closed, exact, ordered)

```
url            (the subscription endpoint URL)
method         ("POST")
headers        {TTL, Content-Encoding, Content-Type,
                Authorization-Mode, Crypto-Key-Mode}
body_meta      {event_id, event_kind, event_severity,
                title, summary, open_at}
kid
endpoint_hash  (sha256(endpoint)[:16])
event_id
```

### Dispatch-record schema (closed, exact, ordered)

```
event_id
event_kind
event_severity
endpoint_hash
kid
outcome
provider_status_class
provider_status_code
envelope_url
attempted_at
```

---

## 4. Decoupled transport

`dispatch_one(record=..., subscription=..., transport=...)` requires
the caller to supply the transport callable. **There is no default.**
A missing or non-callable `transport` raises `TypeError` immediately.

Outcome classification:

| Provider response                   | `provider_status_class` | `outcome`            |
| ----------------------------------- | ----------------------- | -------------------- |
| 2xx                                 | `2xx`                   | `sent`               |
| 410                                 | `410`                   | `drop_subscription`  |
| 4xx other than 410                  | `4xx_other`             | `failed_provider`    |
| 5xx                                 | `5xx`                   | `retry`              |
| Transport raised exception          | `transport_error`       | `retry`              |
| Other (e.g. status_code=None)       | `unknown`               | `failed_provider`    |

Tests pin every row of this table.

---

## 5. What is NOT yet computed in N2b-3a

| Concern                                  | Status                                                                        |
| ---------------------------------------- | ----------------------------------------------------------------------------- |
| Real HTTP client                         | **deferred to N2b-3b**                                                        |
| Real `Authorization: vapid t=<jwt>`      | **deferred to N2b-3b** — header carries a closed placeholder mode string only |
| Real `Crypto-Key: ...`                   | **deferred to N2b-3b** — header carries a closed placeholder mode string only |
| AES-128-GCM encrypted body               | **deferred to N2b-3b** — body_meta carries the bounded six-key payload only   |
| VAPID private key in env                 | **deferred to N2b-3b** — operator action required to generate keypair        |
| `dashboard/api_push_dispatch.py`         | **deferred to N2b-3b** — wiring requires `dashboard_wiring=NEEDS_HUMAN`      |
| nginx 127.0.0.1 lock for dispatch route  | **deferred to N2b-3b** — operator infra change                                |
| Push subscription auto-drop on 410       | **deferred to N2b-3b** — N2b-3a returns the `drop_subscription` outcome but does not call `pss.unregister_subscription` itself |

---

## 6. N2b-3b operator-action checklist (preview, for when the slice lands)

Before N2b-3b can ship:

1. Operator generates a VAPID keypair (one-shot script — agent can prepare, operator runs):
   - public key written to gitignored `config/web_push_vapid_public.txt`;
   - private key printed once to stdout, never to disk in repo.
2. Operator sets `WEB_PUSH_VAPID_PRIVATE_KEY` in the VPS environment
   (e.g. systemd unit override, `.env` outside repo).
3. Operator confirms nginx restricts `/api/push/dispatch` to `127.0.0.1`
   (existing pattern; agent prepares the operator-approved diff).
4. Operator authorises the wiring PR for
   `dashboard/api_push_dispatch.py` + the one-line
   `register_push_dispatch_routes(app)` in `dashboard/dashboard.py`.

Until all four are done, N2b-3b stays paused.

---

## 7. Authority chain summary

| Capability                               | Today (post-N2b-2b) | After N2b-3a                                                  | After N2b-3b (future, gated)                                  |
| ---------------------------------------- | ------------------- | ------------------------------------------------------------- | -------------------------------------------------------------- |
| Compute notification-ready event         | N2a                 | unchanged                                                     | unchanged                                                     |
| Build bounded six-key payload            | N2b-1 stub          | unchanged                                                     | unchanged                                                     |
| Build Web Push HTTP envelope             | does not exist      | yes — N2b-3a `build_envelope(...)`                            | unchanged                                                     |
| Open network socket / send a real push   | does not exist      | **does not exist** (transport is caller-supplied; tests use a synthetic) | yes — single audited callable in `dashboard/api_push_dispatch.py` |
| Sign VAPID JWT                           | does not exist      | does not exist (placeholder `Authorization-Mode` header only) | yes — using env-only `WEB_PUSH_VAPID_PRIVATE_KEY`             |
| Mint approval tokens                     | does not exist      | does not exist                                                | does not exist (N4 territory)                                 |
| Open mobile inbox row                    | does not exist      | does not exist                                                | does not exist (N3 territory)                                 |
| Execute merge / deploy                   | operator + branch protection | unchanged                                              | unchanged                                                     |
| Autonomous merge / deploy                | **forbidden, Level 6** | unchanged — Level 6 stays permanently disabled              | unchanged — Level 6 stays permanently disabled                |

N2b-3a grants ADE **zero** new write authority, opens **zero**
network sockets, and ships **zero** secret-handling code.

---

## 8. Test coverage

Pinned in [`tests/unit/test_web_push_dispatch_adapter.py`](../../tests/unit/test_web_push_dispatch_adapter.py):

- closed `DISPATCH_OUTCOMES`, `PROVIDER_STATUS_CLASSES`,
  `ENVELOPE_KEYS`, `ENVELOPE_HEADERS_KEYS`, `DISPATCH_RECORD_KEYS`
  pinned exactly;
- envelope shape: exactly the closed key set; no extras;
- header set: exactly the five closed header keys;
- `body_meta` is the six-key payload mirror;
- `dispatch_one` requires the transport kwarg (`TypeError` on
  missing or non-callable);
- 2xx → `sent`; 410 → `drop_subscription`; 4xx-other →
  `failed_provider`; 5xx → `retry`; transport exception → `retry`;
- skipped paths: missing event_id → `skipped_invalid_record`;
  missing subscription → `skipped_no_subscription`;
- `endpoint_hash` is sha256[:16]; full endpoint URL never appears
  in the dispatch record;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `pywebpush`, `web_push`, `webpush`, `gh`,
  `git`;
- no `WEB_PUSH_VAPID_PRIVATE_KEY` literal in source;
- importing the module does not flip Step 5 invariants;
- `assert_no_secrets` is invoked on every envelope and every
  dispatch record.

---

## 9. What N2b-3a does NOT do

- N2b-3a sends no real push.
- N2b-3a opens no network socket.
- N2b-3a reads no VAPID private key.
- N2b-3a does not create `dashboard/api_push_dispatch.py`.
- N2b-3a writes no `dashboard/**` or `frontend/**` file.
- N2b-3a opens no inbox row (N3 territory).
- N2b-3a mints no token (N4 territory).
- N2b-3a does not change Step 5.0 logic.
- N2b-3a does not flip `step5_implementation_allowed`.
- N2b-3a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N2b-3b (real Web Push), N3 (mobile approval inbox), N4 (token
  gate), and N5 (merge/deploy adapter) remain unimplemented.
- Level 6 stays permanently disabled. **No approval can happen
  from notification click alone.**
