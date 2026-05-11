# Mobile Approval Inbox projector — N3a (read-only)

> **Status:** Implemented (read-only, projector-only).
>
> **Module:** [`reporting/mobile_approval_inbox.py`](../../reporting/mobile_approval_inbox.py)
> **Output artefact:** `logs/mobile_approval_inbox/latest.json`
>
> **Authority:** development-governance read-only.
> N3a mints no token, approves nothing, merges nothing, deploys
> nothing, sends no push, opens no PWA inbox screen, registers no
> Flask blueprint. Level 6 stays permanently disabled per ADR-015
> §Doctrine 1. **No approval can happen from a notification click
> alone.**

---

## 1. Purpose

N3a is the **projector** half of the future Mobile Approval Inbox
surface. It reads the existing N2b-1 outbox at
`logs/notification_dispatch_outbox/latest.json`, classifies each
record's attention level, and emits a bounded inbox artefact at
`logs/mobile_approval_inbox/latest.json`.

The artefact is consumed by:

- **A23 Merge Recommendation** (next slice) — combines this inbox
  with the A22 PR lifecycle observer to produce a recommendation
  record.
- **N3b** (deferred, operator-action) — adds a Flask blueprint
  serving the inbox under `/api/approval-inbox/v2/*`.
- **N3c** (deferred, operator-action) — adds the PWA detail UI.

N3a itself is purely an inspection surface — operators can already
view today what the future N3b API would return and what the future
N3c UI would render.

---

## 2. Hard constraints

N3a, in this PR and at runtime, must not:

- mint or verify approval tokens (N4 territory);
- execute an approve / reject decision (N4 + N5 territory);
- merge or deploy anything (N5 + future deploy adapter territory);
- send any real push (N2b-3b territory);
- register a Flask blueprint or wire into `dashboard/dashboard.py`
  (N3b territory);
- write to `seed.jsonl` / `delegation_seed.jsonl` /
  `generated_seed.jsonl`;
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

N3a ships its own AST-level forbidden-import scan + source-text
scan to enforce the relevant bullets.

---

## 3. Closed vocabularies

Pinned in [`reporting/mobile_approval_inbox.py`](../../reporting/mobile_approval_inbox.py):

### `attention_level` (4 values)

| Value                | When                                                                              |
| -------------------- | --------------------------------------------------------------------------------- |
| `informational`      | severity in `silent` / `digest` / `push_info` and intent is `sent` / `duplicate`  |
| `needs_review`       | severity in `push_action_required` / `approval_required`                          |
| `blocked_attention`  | outbound intent in `failed_secret_check` / `failed_stub_provider` / `rate_limited_outbound` |
| `critical_attention` | severity == `critical`                                                            |

### `decision_state` (6 values, but N3a only emits `pending`)

```
pending  acknowledged  approved  rejected  expired  superseded
```

N3a NEVER writes a value other than `pending`. The remaining values
are reserved for the future N4 approval-token gate — once that lands
and is operator-authorised, it becomes the only path that can flip
`pending → approved` or `pending → rejected`. N3a has no callable
that could effect such a flip.

### `source_module` (1 value)

```
notification_dispatch_outbox
```

Tightly bounded. Adding a new source requires a code change pinned
by an updated unit test.

### `validation_warnings` (4 values)

```
outbox_artifact_absent
outbox_artifact_unparseable
outbox_record_invalid
decision_verb_redacted_in_summary
```

### Per-row schema (14 keys, exact and ordered)

```
inbox_row_id  event_id  event_kind  event_severity
source_module  source_id  endpoint_hash  outbound_delivery_intent
attention_level  decision_state
title  summary  open_at  created_at
```

All scalars bounded: `title ≤ 80 chars`, `summary ≤ 200 chars`,
`open_at ≤ 300 chars`. The inbox surface itself is bounded
(`MAX_INBOX_ROWS = 64`) so even a runaway outbox can't blow up the
artefact size.

---

## 4. Decision-verb redaction

N3a scans every emitted `title` and `summary` for the closed
forbidden-verb set (`approve`, `reject`, `merge`, `deploy`) and
**replaces the whole string with `[redacted-decision-verb]`** if any
match. This is defense-in-depth: the closed N2b-1 payload schema
already refuses decision verbs at the upstream layer, so this should
never fire in production. If it does, a
`decision_verb_redacted_in_summary` warning is added to the snapshot
so the operator sees the upstream contract violation.

---

## 5. Discipline invariants (emitted on every artefact)

```
mints_approval_token                          = false
verifies_approval_token                       = false
executes_approve_or_reject                    = false
merges_or_deploys                             = false
sends_real_push                               = false
opens_pwa_inbox_screen                        = false
registers_flask_blueprint                     = false
uses_subprocess_or_network                    = false
operator_promotion_required                   = true
step5_implementation_allowed                  = false
step5_enabled_substage                        = "none"
diagnostics_do_not_trade                      = true
no_approval_from_notification_click_alone     = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write.

---

## 6. CLI

```sh
python -m reporting.mobile_approval_inbox --no-write
python -m reporting.mobile_approval_inbox
```

Pure stdlib + `reporting.notification_dispatch_outbox` (read-only) +
`reporting.notification_event` (read-only) +
`reporting.agent_audit_summary.assert_no_secrets`. No subprocess, no
network, no `gh`, no `git`.

---

## 7. Authority chain summary

| Capability                                              | Today (post-A22) | After N3a                                | After N3b (future, operator-authored) | After N3c (future, operator-authored) | After N4b (future, operator-authored) | After N5 (future, operator-authored) |
| ------------------------------------------------------- | ---------------- | ---------------------------------------- | -------------------------------------- | -------------------------------------- | --------------------------------------- | ------------------------------------- |
| Compute inbox rows from outbox                          | does not exist   | yes — N3a (read-only)                    | unchanged                              | unchanged                              | unchanged                               | unchanged                             |
| Serve inbox over HTTP                                    | does not exist   | does not exist                           | yes — `dashboard/api_approval_inbox_v2.py` | unchanged                          | unchanged                               | unchanged                             |
| Render inbox in PWA                                      | does not exist   | does not exist                           | does not exist                         | yes — `frontend/src/routes/AgentControl/InboxDetail.tsx` | unchanged                  | unchanged                             |
| Mint approval token                                      | does not exist   | does not exist                           | does not exist                         | does not exist                         | yes — operator-env-only                 | unchanged                             |
| Execute approve / reject                                 | does not exist   | does not exist                           | does not exist                         | does not exist                         | does not exist                          | yes — bounded merge adapter           |
| Autonomous merge / deploy                                | forbidden, Level 6 | unchanged — Level 6 permanently disabled | unchanged                              | unchanged                              | unchanged                               | unchanged                             |

N3a is the **inspection-only** surface that lets the operator see
what the future N3b/N3c/N4b/N5 stack would expose, **without**
adding any of those surfaces yet.

---

## 8. Test coverage

Pinned in [`tests/unit/test_mobile_approval_inbox.py`](../../tests/unit/test_mobile_approval_inbox.py):

- closed `ATTENTION_LEVELS`, `INBOX_DECISION_STATES`,
  `SOURCE_MODULES`, `VALIDATION_WARNINGS`, `INBOX_ROW_KEYS` pinned
  exactly;
- every row of §3's attention-level table maps correctly to one
  of the four levels;
- `decision_state` is NEVER set to anything other than `pending`
  by N3a (pinned with synthetic upstream that already carries an
  `approved` decision state — N3a still emits `pending`);
- decision-verb redaction triggers on a forbidden token in the
  upstream payload (defense-in-depth);
- inbox rows are bounded to `MAX_INBOX_ROWS = 64` even when the
  upstream outbox is larger;
- `endpoint_hash` is propagated; full endpoint URL is NOT leaked
  in any inbox scalar;
- atomic write refuses any path outside
  `logs/mobile_approval_inbox/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`,
  `requests`, `httpx`, `aiohttp`, `pywebpush`, `web_push`, `gh`,
  `git`;
- importing the module does not flip Step 5 invariants;
- this doc states "no approval from notification click alone".

---

## 9. What N3a does NOT do

- N3a never mints or verifies approval tokens.
- N3a never approves or rejects any row.
- N3a never merges or deploys.
- N3a never sends a real push.
- N3a never registers a Flask blueprint.
- N3a never writes to `dashboard/dashboard.py` or `frontend/**`.
- N3a never writes to any seed file.
- N3a never edits canonical roadmap status fields.
- N3a never marks a roadmap phase complete.
- N3a does not flip `step5_implementation_allowed`.
- N3a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N3b / N3c / N4 (live) / N5 / deploy adapter remain
  unimplemented.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. **No approval can
  happen from notification click alone.**
