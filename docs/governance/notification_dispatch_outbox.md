# Notification Dispatch Outbox — N2b-1 (stub provider, dry-run)

> **Status:** Implemented (read-only-upstream, deterministic,
> **stub-provider dry-run only**).
>
> **Module:** [`reporting/notification_dispatch_outbox.py`](../../reporting/notification_dispatch_outbox.py)
> **Status reporter:** [`reporting/notification_dispatch_outbox_status.py`](../../reporting/notification_dispatch_outbox_status.py)
>
> **Output artefact:** `logs/notification_dispatch_outbox/latest.json`
> **Bounded outbox history:** `logs/notification_dispatch_outbox/outbox.jsonl` (≤ 500 rows)
> **Status artefact:** `logs/notification_dispatch_outbox_status/latest.json`
>
> **Authority:** development-governance read-only (upstream); local
> persistence + audit-ledger append on normal runs.
> N2b-1 sends no real push and grants no agent any new authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

N2b-1 is the **delivery side** of the push engine, in dry-run shape.
It reads N2a's `logs/notification_dispatcher/latest.json`, filters
to records with `delivery_intent="ready"`, builds a bounded six-key
push payload per event, runs every payload through the existing
closed credential-pattern guard
(`reporting.agent_audit_summary.assert_no_secrets`), and dispatches
via a **stub provider** that records the *intended* URL / status /
result but **never opens a network socket**. Each attempted record
also produces a pair of audit-ledger events (`push_dispatch_attempt`
+ a result event) with `autonomy_level_claimed=0`, but **only on
normal non-`--no-write` runs**.

**N2b-2** (PWA subscription UI + service worker) and **N2b-3** (real
Web Push delivery using an env-provided VAPID private key) remain
unimplemented and require their own separate operator go-signals.

**N3** (mobile approval inbox), **N4** (approval-token gate), and
**N5** (merge/deploy adapter) remain out of scope.

**No approval can happen from a notification click alone.** Even
when a real push goes out (later, in N2b-3), the only action it
triggers is opening the PWA at the inbox row. The operator must read
evidence and re-authenticate to act. This rule is mirrored from
[`docs/governance/notification_engine.md`](notification_engine.md)
and pinned by the doc tests below.

---

## 2. Hard constraints

N2b-1, in this PR and at runtime, must not:

- send a real push (Web Push, APNs, FCM, Telegram, email, SMS, anything);
- open a network socket;
- import a Web Push library;
- read or create a subscription file;
- read or create any VAPID key;
- write to `dashboard/**` or `frontend/**`;
- mint approval tokens (N4 territory);
- open mobile approval inbox rows (N3 territory);
- merge or deploy (N5 / future);
- emit audit events on `--no-write` runs;
- amend the N1 closed `EVENT_KINDS` vocabulary (uses only existing kinds);
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

The module ships its own AST-level forbidden-import scan and
source-text scan to enforce the relevant bullets.

---

## 3. Closed vocabularies

Pinned in [`reporting/notification_dispatch_outbox.py`](../../reporting/notification_dispatch_outbox.py):

### `outbound_delivery_intent` (6 values)

| Value                       | Meaning                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `sent`                      | stub provider accepted offline; the real N2b-3 surface would deliver this |
| `duplicate`                 | `event_id` already in `outbox.jsonl` — not re-attempted                 |
| `skipped_not_ready`         | upstream `delivery_intent != "ready"` — recorded but never dispatched   |
| `rate_limited_outbound`     | exceeded `MAX_DISPATCH_PER_CYCLE = 16` `sent` events for this cycle     |
| `failed_secret_check`       | payload failed the closed-pattern credential guard or the              |
|                             | decision-verb / diff / PEM substring guard                              |
| `failed_stub_provider`      | stub provider rejected the payload (e.g. wrong shape)                   |

### `audit_event_names` (5 values)

```
push_dispatch_attempt
push_dispatch_success
push_dispatch_skipped_duplicate
push_dispatch_skipped_rate_limit
push_dispatch_failure
```

### Push payload schema (closed, exact, ordered)

```
event_id
event_kind
event_severity
title       (≤ 80 chars; mobile rendering constraint)
summary     (≤ 200 chars)
open_at     ("/agent-control/inbox?event=<event_id>"; ≤ 300 chars)
```

Strictly forbidden in the payload (pinned by tests):

- PR diff, file diff, patch hunks (`diff --git`, `+++ b/`, `--- a/`, `@@ -`)
- PEM private-key blocks (`BEGIN PRIVATE KEY`, etc.)
- credential-shaped strings (caught by `assert_no_secrets`)
- decision verbs (`approve`, `reject`, `merge`, `deploy`)

### Outbox record schema (closed, exact, ordered)

```
event_id
event_kind
event_severity
source_module
source_id
outbound_delivery_intent
payload
stub_provider_url
stub_provider_status
stub_provider_result
secret_guard_ok
attempted_at
audit_event_seq
```

### Wrapper-level fields

```
schema_version, module_version, report_kind, generated_at_utc,
step5_enabled_substage, step5_implementation_allowed,
dispatcher_artifact_path, dispatcher_artifact_available,
outbox_history_path, stub_provider_url, note, validation_warnings,
vocabularies, counts, records,
notification_dispatcher_module_version,
notification_event_module_version, discipline_invariants
```

---

## 4. Stub provider

N2b-1's `stub_provider(payload)` is a synthetic dispatch sink:

- Validates the payload shape against `PUSH_PAYLOAD_KEYS`.
- Records the *intended* URL as the closed sentinel
  `stub://web-push-provider-disabled`.
- Returns a result dict with `url`, `status`, `result`.
- **Opens no socket. Imports no Web Push library. Reads no
  subscription file. Reads no VAPID key.** The `subscription`
  argument is accepted for forward-compat with N2b-3 but ignored.

This is deliberate: the stub gives us end-to-end coverage of the
gate / dedupe / payload-bound / audit machinery before any real push
goes out the door. When N2b-3 lands later, the **real** provider
will live in `dashboard/api_push_dispatch.py` (a single, audited
file) and the stub stays in this module for tests.

---

## 5. `--no-write` discipline

| Mode               | Writes `latest.json` | Appends to `outbox.jsonl` | Emits audit events |
| ------------------ | -------------------- | -------------------------- | ------------------ |
| `--no-write`       | **no**               | **no**                     | **no**             |
| normal (default)   | yes                  | yes                        | yes (per-record pair) |

Pinned by tests: `test_no_write_mode_writes_no_files_and_no_audit`
and `test_normal_run_writes_artifacts_and_emits_audit`.

---

## 6. Discipline invariants

```
sends_real_push                = false
invokes_network                = false
invokes_subprocess             = false
reads_subscription_files       = false
reads_vapid_keys               = false
writes_dashboard_or_frontend   = false
opens_mobile_inbox             = false
mints_approval_token           = false
invokes_merge_or_deploy        = false
uses_real_push_provider        = false
secret_redactor_invoked        = true
operator_promotion_required    = true
step5_implementation_allowed   = false
step5_enabled_substage         = "none"
diagnostics_do_not_trade       = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write. Defense in depth — the module emits no
secret-shaped strings by construction; the redactor is the safety
net.

---

## 7. CLI

```sh
# Pure inspection — does not write artefacts and does not emit audit events:
python -m reporting.notification_dispatch_outbox --no-write
python -m reporting.notification_dispatch_outbox_status --no-write

# Writes logs/notification_dispatch_outbox[_status]/latest.json AND
# appends per-record audit events to today's agent_audit ledger:
python -m reporting.notification_dispatch_outbox
python -m reporting.notification_dispatch_outbox_status
```

Both modules are pure-stdlib + the read-only ADE/reporting deps. No
subprocess, no network, no `gh`, no `git`.

---

## 8. Authority chain summary

| Capability                                                | Today (post-N2a)                  | After N2b-1                                        | After N2b-2 (future)                                | After N2b-3 (future, gated)                                  |
| --------------------------------------------------------- | --------------------------------- | -------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------ |
| Compute notification-ready event                          | `notification_dispatcher`         | unchanged                                          | unchanged                                           | unchanged                                                    |
| Persist outbound *intent* per event                       | none                              | `logs/notification_dispatch_outbox/latest.json` + `outbox.jsonl` | unchanged                              | unchanged                                                    |
| Open network socket / send a real push                    | does not exist                    | **does not exist** (stub provider only)            | **does not exist**                                  | yes (single, audited callable in `dashboard/api_push_dispatch.py`) |
| Register / store a Web Push subscription                  | does not exist                    | does not exist                                     | yes (PWA → `POST /api/push/subscribe` → gitignored) | unchanged                                                    |
| Mint approval tokens                                      | does not exist                    | does not exist                                     | does not exist                                      | does not exist (N4 territory)                                |
| Open mobile inbox row                                     | does not exist                    | does not exist                                     | does not exist                                      | does not exist (N3 territory)                                |
| Execute merge / deploy                                    | operator + branch protection      | unchanged                                          | unchanged                                           | unchanged                                                    |
| Autonomous merge / deploy                                 | **forbidden, Level 6**            | unchanged — Level 6 stays permanently disabled     | unchanged — Level 6 stays permanently disabled      | unchanged — Level 6 stays permanently disabled                 |

N2b-1 grants ADE **zero** new write authority over operator-authored
surfaces. Real Web Push delivery (N2b-3) and the PWA subscription UI
(N2b-2) each require their own explicit operator go-signal.

---

## 9. Test coverage

Pinned in
[`tests/unit/test_notification_dispatch_outbox.py`](../../tests/unit/test_notification_dispatch_outbox.py)
and
[`tests/unit/test_notification_dispatch_outbox_status.py`](../../tests/unit/test_notification_dispatch_outbox_status.py):

- closed `OUTBOUND_DELIVERY_INTENTS`, `AUDIT_EVENT_NAMES`,
  `PUSH_PAYLOAD_KEYS`, `OUTBOX_RECORD_SCHEMA_KEYS` pinned exactly;
- only `delivery_intent="ready"` records reach the stub provider;
- non-ready records record as `skipped_not_ready` and never dispatch;
- the current real N2a `intake_candidate_eligible` event becomes
  `outbound_delivery_intent="sent"` with a six-key payload;
- duplicate `event_id` becomes `outbound_delivery_intent="duplicate"`;
- excess `ready` events become `rate_limited_outbound` once the
  `MAX_DISPATCH_PER_CYCLE=16` cap is reached;
- payload contains no decision verbs (`approve`, `reject`, `merge`,
  `deploy`);
- payload contains no diff / PR-body / command-output substrings;
- `assert_no_secrets` is invoked on every payload; a credential-
  shaped string in upstream forces `failed_secret_check`;
- `--no-write` writes nothing to either log directory and emits no
  audit event;
- a normal run writes both `latest.json` and `outbox.jsonl` and emits
  audit events with `autonomy_level_claimed=0`;
- atomic write refuses any path outside
  `logs/notification_dispatch_outbox/`;
- `outbox.jsonl` is bounded ≤ 500 rows;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `pywebpush`, `web_push`, `webpush`, `gh`, `git`;
- importing the module does not flip Step 5 invariants on
  `reporting.development_step5_loop`;
- deterministic byte-stable output with an injected
  `generated_at_utc`;
- this doc explicitly states no real push in N2b-1, no approval from
  notification click alone, and Level 6 stays permanently disabled.

---

## 10. What N2b-1 does NOT do

- N2b-1 sends no real push.
- N2b-1 opens no network socket.
- N2b-1 reads no subscription file.
- N2b-1 reads no VAPID key.
- N2b-1 writes no `dashboard/**` or `frontend/**` file.
- N2b-1 opens no inbox row.
- N2b-1 mints no token.
- N2b-1 does not change Step 5.0 logic.
- N2b-1 does not flip `step5_implementation_allowed`.
- N2b-1 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N2b-2 (PWA UI + SW), N2b-3 (real Web Push), N3 (mobile approval
  inbox), N4 (token gate), and N5 (merge/deploy adapter) remain
  unimplemented.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. **No approval can happen
  from notification click alone.**
