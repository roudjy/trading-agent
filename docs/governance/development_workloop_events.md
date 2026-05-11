# Autonomous Development Workloop event-taxonomy projector — A24

> **Status:** Implemented (read-only, projector-only).
>
> **Module:** [`reporting/development_workloop_events.py`](../../reporting/development_workloop_events.py)
> **Output artefact:** `logs/development_workloop_events/latest.json`
>
> **Authority:** development-governance read-only.
> A24 NEVER calls `git` / `gh`, NEVER invokes any workloop function,
> NEVER emits a notification, NEVER mints an approval token, NEVER
> merges or deploys. Level 6 stays permanently disabled per ADR-015
> §Doctrine 1. **No approval can happen from a notification click
> alone.**

---

## 1. Purpose

A24 is the read-only **wiring layer** between the existing
[`reporting.autonomous_workloop`](../../reporting/autonomous_workloop.py)
controller and the N1 notification-event taxonomy.

The workloop is allowed to call `git` / `gh` and produces a
structured digest at `logs/autonomous_workloop/latest.json` with
sections like `pr_queue`, `dependabot_queue`, `roadmap_queue`,
`blocked_items`, `audit_chain_status`, `governance_status`, and
`actions_taken`. A24 reads that digest and classifies each signal
into the closed N1 `event_kind` / `event_severity` vocabulary, then
emits a bounded per-event projection at
`logs/development_workloop_events/latest.json`.

A24 itself is **strictly read-only**. Tests assert (via AST) that
no callable in this module invokes any function from the workloop
module — the upstream module is imported only for its
`MODULE_VERSION` constant.

---

## 2. Hard constraints

A24, in this PR and at runtime, must not:

- call `git`, `gh`, or any other CLI / subprocess;
- open a network socket;
- emit a real notification or push;
- mint or verify approval tokens (N4 territory);
- execute an approve / reject / merge / deploy action;
- register a Flask blueprint or wire into `dashboard/dashboard.py`;
- touch `frontend/**`;
- mutate any upstream artefact;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- store secrets in repo.

A24 ships its own AST-level forbidden-import scan, source-text
scans, **and an AST scan that no callable from the workloop module
is invoked**.

---

## 3. Closed vocabularies

### `workloop_signal_source` (7 values)

```
pr_queue
dependabot_queue
roadmap_queue
blocked_items
audit_chain_status
governance_status
actions_taken
```

These are the sections of the workloop digest A24 projects from.

### N1 event mapping (closed table)

| Workloop signal               | N1 `event_kind`                  |
| ----------------------------- | -------------------------------- |
| `pr_queue` item               | `pr_lifecycle_event`             |
| `dependabot_queue` item       | `pr_lifecycle_event`             |
| `roadmap_queue` (normal risk) | `queue_item_proposed`            |
| `roadmap_queue` (blocked risk)| `queue_item_blocked`             |
| `blocked_items` row           | `queue_item_blocked`             |
| `audit_chain_status` (any)    | `audit_chain_anomaly` (severity: `critical` regardless of value, by N1 routing) |
| `governance_status` ok        | `operational_digest_emitted`     |
| `governance_status` anomaly   | `governance_violation_detected`  |
| `actions_taken` row           | `operational_digest_emitted`     |

The severity for each row is computed by
`reporting.notification_event.route_for(event_kind)` — A24 reuses
the N1 routing table verbatim; no custom severity logic.

### Per-row schema (9 keys, exact and ordered)

```
workloop_event_id  source_signal  source_index
event_kind  event_severity
decision_or_outcome
title  summary  extracted_at
```

`workloop_event_id = "awe_<source_signal>_<index04d>_<identity_key_prefix32>"` — stable per signal+index+identity.

### `validation_warnings` (3 values, closed)

```
workloop_digest_absent
workloop_digest_unparseable
workloop_signal_invalid
```

---

## 4. Bounded surface

- `MAX_EVENT_ROWS = 128` — projection capped per snapshot.
- `title ≤ 200 chars`, `summary ≤ 480 chars` — bounded scalars.
- No PR body, no diff, no command output, no commit message
  propagated into the artefact.

---

## 5. Discipline invariants (emitted on every artefact)

```
calls_workloop_functions                       = false
calls_gh_cli                                   = false
calls_git_cli                                  = false
uses_subprocess_or_network                     = false
emits_real_notification                        = false
mints_approval_token                           = false
merges_or_deploys                              = false
operator_promotion_required                    = true
step5_implementation_allowed                   = false
step5_enabled_substage                         = "none"
diagnostics_do_not_trade                       = true
no_approval_from_notification_click_alone      = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write.

---

## 6. CLI

```sh
python -m reporting.development_workloop_events --no-write
python -m reporting.development_workloop_events
```

Pure stdlib + `reporting.notification_event` (read-only) +
`reporting.autonomous_workloop` (imported for `MODULE_VERSION` constant
only; AST-pinned not to be called) +
`reporting.agent_audit_summary.assert_no_secrets`.

---

## 7. Authority chain summary

| Capability                                              | Today (post-N4a) | After A24                                |
| ------------------------------------------------------- | ---------------- | ---------------------------------------- |
| Read autonomous_workloop digest                          | does not exist   | yes — A24 (read-only)                    |
| Map workloop signals to N1 event taxonomy                | does not exist   | yes — closed table, deterministic        |
| Call `git` / `gh` from A24 itself                        | does not exist   | **does not exist** (AST-pinned)         |
| Invoke any workloop function from A24                    | does not exist   | **does not exist** (AST-pinned)         |
| Emit a real notification                                 | does not exist   | does not exist                           |
| Autonomous merge / deploy                                | forbidden, Level 6 | unchanged — Level 6 permanently disabled |

---

## 8. Test coverage

Pinned in [`tests/unit/test_development_workloop_events.py`](../../tests/unit/test_development_workloop_events.py):

- closed `WORKLOOP_SIGNAL_SOURCES` (7), `VALIDATION_WARNINGS` (3),
  `EVENT_ROW_KEYS` (9) pinned exactly;
- every entry in the workloop-signal → N1-event-kind mapping table
  produces the expected `event_kind`;
- `event_severity` is always routed through N1's `route_for`
  (no custom severity logic in A24);
- atomic write refuses any path outside
  `logs/development_workloop_events/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`,
  `requests`, `httpx`, `aiohttp`, `gh`, `git`;
- **AST scan: no callable in A24 invokes any function from
  `reporting.autonomous_workloop`**. The upstream module is
  imported only for the `MODULE_VERSION` constant;
- importing the module does not flip Step 5 invariants;
- this doc states "no approval from notification click alone" and
  "Level 6 stays permanently disabled".

---

## 9. What A24 does NOT do

- A24 never calls `git` or `gh`.
- A24 never invokes any workloop function.
- A24 never emits a real notification.
- A24 never mints or verifies approval tokens.
- A24 never merges or deploys.
- A24 never sends a real push.
- A24 never registers a Flask blueprint.
- A24 never writes to `dashboard/dashboard.py` or `frontend/**`.
- A24 never writes to any seed file.
- A24 never edits canonical roadmap status fields.
- A24 does not flip `step5_implementation_allowed`.
- A24 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N2b-3b / N3b / N3c / N4b / N5 / A18 / A21 / deploy adapter all
  remain unimplemented.
- Level 6 stays permanently disabled.
