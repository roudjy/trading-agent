# Notification Dispatcher — N2a (artifact-only)

> **Status:** Implemented (read-only, deterministic, **artifact-only**).
>
> **Module:** [`reporting/notification_dispatcher.py`](../../reporting/notification_dispatcher.py)
> **Status reporter:** [`reporting/notification_dispatcher_status.py`](../../reporting/notification_dispatcher_status.py)
>
> **Output artefact:** `logs/notification_dispatcher/latest.json`
> **Bounded events history:** `logs/notification_dispatcher/events.jsonl` (≤ 500 rows)
> **Status artefact:** `logs/notification_dispatcher_status/latest.json`
>
> **Authority:** development-governance read-only.
> N2a sends no real push and grants no agent any new authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

N2a converts existing ADE upstream artefacts (A8 work queue, A14 Step
5.0 plan, A16a intake promotion, Step 5.0.1 roadmap intake) into
notification-ready event records using the closed N1 taxonomy, and
writes them to a single dedicated log directory. **No push is sent.**
The dispatcher decides nothing; it computes which event would be
delivered and persists the result. Future N2b adds the actual Web
Push delivery on top of these records, behind a separate explicit
operator go-signal.

---

## 2. Hard constraints

N2a, in this PR and at runtime, must not:

- send a real push (Web Push, APNs, FCM, Telegram, email, SMS, anything);
- open a network socket;
- import a Web Push library;
- read or create a subscription file;
- read or create any VAPID key;
- write to `dashboard/**` or `frontend/**`;
- mint approval tokens (N4 territory);
- open mobile approval inbox rows (N3 territory);
- merge or deploy (N5 / future);
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

The dispatcher ships its own AST-level forbidden-import scan and
source-text scan to enforce the relevant bullets.

**No approval can happen from a notification click alone.** N2a
emits *records*; even the future N2b never carries a decision verb in
its payload. The PWA UI (a future track) is the only path that can
submit an approval, and that path passes through re-authentication and
the future N4 token gate. This rule is mirrored from
[`docs/governance/notification_engine.md`](notification_engine.md).

---

## 3. Closed vocabularies

Pinned in [`reporting/notification_dispatcher.py`](../../reporting/notification_dispatcher.py):

### `delivery_intent` (5 values)

| Value                       | Meaning                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `ready`                     | passes all gates; would be delivered by a future N2b push surface        |
| `suppressed`                | severity is `silent` or `digest` — never delivered                       |
| `suppressed_cooldown`       | within the cooldown window for its `event_kind`                          |
| `duplicate_within_window`   | `event_id` seen within the 24-h sliding window                           |
| `rate_limited`              | exceeded `MAX_DISPATCH_PER_CYCLE = 16` `ready` events for this cycle     |

### `source_module` (3 values)

```
development_intake_promotion
development_step5_loop
development_roadmap_intake
```

### Cooldown table (`COOLDOWN_SECONDS_PER_EVENT_KIND`)

Pinned per-event-kind cooldown in seconds. Default for any unlisted
kind is `600`. Cross-cutting kinds (`governance_violation_detected`,
`secret_or_pii_redaction_event`, `audit_chain_anomaly`) are `0` —
never silenced. Operator-attention kinds (`*_needs_human`,
`*_approval_required`, `release_gate_fail`, `e2e_proof_fail`) are also
`0`.

### `EVENT_SCHEMA_KEYS` (closed and ordered)

```
event_id
event_kind
event_severity
delivery_intent
source_module
source_artifact_path
source_id
title
summary
risk_class
execution_authority_decision
acceptance_criteria
target_path
evidence_hash
created_at
notes
```

Wrapper-level fields: `schema_version`, `module_version`,
`report_kind`, `generated_at_utc`, `step5_enabled_substage`,
`step5_implementation_allowed`, `sources_read`, `events_history_path`,
`note`, `validation_warnings`, `vocabularies`,
`cooldown_seconds_per_event_kind`, `counts`, `events`,
`execution_authority_module_version`,
`notification_event_module_version`,
`intake_promotion_module_version`, `step5_module_version`,
`roadmap_intake_module_version`, `discipline_invariants`.

---

## 4. Delivery-intent gating (closed table)

Pinned in `_apply_delivery_gates(...)` and tested verbatim. Priority
order, first match wins:

| Condition                                                            | Outcome                  |
| -------------------------------------------------------------------- | ------------------------ |
| `event_severity in {silent, digest}`                                 | `suppressed`             |
| `event_id` seen within the 24-h sliding window                       | `duplicate_within_window`|
| `event_kind` cooldown not yet elapsed                                | `suppressed_cooldown`    |
| ready_count ≥ `MAX_DISPATCH_PER_CYCLE`                               | `rate_limited`           |
| otherwise                                                            | `ready`                  |

The dispatcher never **drops** an event from the artefact — it only
re-labels its `delivery_intent`. The full set is always written, so
the operator can inspect every gate decision after the fact.

---

## 5. Discipline invariants (emitted on every artefact)

```
sends_real_push                = false
opens_mobile_inbox             = false
mints_approval_token           = false
invokes_network                = false
invokes_subprocess             = false
mutates_upstream_artifacts     = false
reads_subscription_files       = false
reads_vapid_keys               = false
writes_dashboard_or_frontend   = false
secret_redactor_invoked        = true
operator_promotion_required    = true
step5_implementation_allowed   = false
step5_enabled_substage         = "none"
diagnostics_do_not_trade       = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write. Defense in depth — the dispatcher emits no
secret-shaped strings by construction; the redactor is the safety
net.

---

## 6. CLI

```sh
# Pure inspection — does not write artifacts:
python -m reporting.notification_dispatcher --no-write
python -m reporting.notification_dispatcher_status --no-write

# Writes logs/notification_dispatcher[_status]/latest.json:
python -m reporting.notification_dispatcher
python -m reporting.notification_dispatcher_status
```

Both modules are pure-stdlib + the read-only ADE/reporting deps
(`notification_event`, `execution_authority`,
`development_intake_promotion`, `development_step5_loop`,
`development_roadmap_intake` for the writer module;
`notification_dispatcher`, `notification_event`,
`execution_authority` for the status module). No subprocess, no
network, no `gh`, no `git`.

---

## 7. Authority chain summary

| Capability                                                | Today                                | After N2a                                          | After N2b (future, gated)                          |
| --------------------------------------------------------- | ------------------------------------ | -------------------------------------------------- | -------------------------------------------------- |
| Read upstream artefacts (A8/A10/A11/A14/A16a)             | step5_loop, intake_promotion         | unchanged + notification_dispatcher                | unchanged                                          |
| Compute severity per event                                | N1 `route_for(...)`                  | unchanged                                          | unchanged                                          |
| Persist a notification-intent record                      | none                                 | `logs/notification_dispatcher/latest.json` + `events.jsonl` | unchanged                              |
| Send a Web Push to a phone                                | does not exist                       | does not exist                                     | `dashboard/api_push_dispatch.py` (server-side)     |
| Mint approval tokens                                      | does not exist                       | does not exist                                     | does not exist (N4 territory)                      |
| Open mobile inbox row                                     | does not exist                       | does not exist                                     | does not exist (N3 territory)                      |
| Execute merge / deploy                                    | operator + branch protection         | unchanged                                          | unchanged                                          |
| Autonomous merge / deploy                                 | **forbidden, Level 6**               | unchanged — Level 6 stays permanently disabled     | unchanged — Level 6 stays permanently disabled     |

N2a is operator-supervised. **N2b stays paused** until the operator
sees the dispatcher artefact in production, validates the dedupe and
cooldown behaviour, and explicitly authorises a real push surface.

N3 (mobile approval inbox), N4 (approval-token gate), and N5
(merge/deploy adapter) remain **out of scope** for both N2a and N2b.

---

## 8. Test coverage

Pinned in
[`tests/unit/test_notification_dispatcher.py`](../../tests/unit/test_notification_dispatcher.py)
and
[`tests/unit/test_notification_dispatcher_status.py`](../../tests/unit/test_notification_dispatcher_status.py):

- closed `DELIVERY_INTENTS`, `SOURCE_MODULES`, `EVENT_SCHEMA_KEYS`
  pinned exactly;
- the current real A16a candidate becomes
  `event_kind="intake_candidate_eligible"`,
  `event_severity="push_info"`,
  `delivery_intent="ready"` when fed in;
- a Step 5.0 `plan_emitted` cycle becomes
  `event_kind="step5_cycle_planned"`,
  `event_severity="silent"`,
  `delivery_intent="suppressed"`;
- duplicate `event_id` within the 24-h sliding window becomes
  `delivery_intent="duplicate_within_window"`;
- cooldown suppression works per pinned cooldown table;
- excess events become `delivery_intent="rate_limited"` once the
  per-cycle cap is reached;
- atomic write refuses any path outside
  `logs/notification_dispatcher/`;
- `events.jsonl` is bounded ≤ 500 rows;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `pywebpush`, `web_push`, `gh`, `git`;
- importing the module does not flip Step 5 invariants on
  `reporting.development_step5_loop`;
- deterministic byte-stable output with an injected
  `generated_at_utc`;
- `assert_no_secrets` is invoked before every write;
- this doc explicitly states no real push in N2a and that N2b is
  operator-gated;
- this doc states "no approval from notification click alone"
  verbatim;
- this doc states "Level 6 stays permanently disabled" verbatim.

---

## 9. What N2a does NOT do

- N2a sends no real push.
- N2a opens no network socket.
- N2a reads no subscription file.
- N2a reads no VAPID key.
- N2a writes no `dashboard/**` or `frontend/**` file.
- N2a opens no inbox row.
- N2a mints no token.
- N2a does not change Step 5.0 logic.
- N2a does not flip `step5_implementation_allowed`.
- N2a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N3 (mobile approval inbox), N4 (token gate), N5 (merge/deploy
  adapter) and N2b (real Web Push) remain unimplemented.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. **No approval can happen
  from notification click alone.**
