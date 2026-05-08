# ADE Notification & Mobile Approval Engine

> **Status:** N1 (event taxonomy) — implemented, read-only, pure data + routing.
> N2–N5 — design only, **not implemented**.
>
> **Module:** [`reporting/notification_event.py`](../../reporting/notification_event.py)
> **Tests:** [`tests/unit/test_notification_event.py`](../../tests/unit/test_notification_event.py)
>
> **Authority:** **none.** This engine grants no autonomous authority.
> Mobile approval is **human approval, not autonomous merge/deploy.**
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 0. TL;DR

The Notification & Mobile Approval Engine is a five-track design that
gives the operator push notifications in the PWA and a phone-friendly
approval surface for high-impact ADE actions (today: PR merge;
later: deploy). It does **not** unlock any new agent capability — it
replaces an absent operator UX with a deterministic, auditable one.

Tracks land **independently** as separate PRs:

| Track | Title                              | Status        |
| ----- | ---------------------------------- | ------------- |
| **N1**  | Notification Event Taxonomy        | implemented   |
| **N2**  | Push Notification Engine           | design only   |
| **N3**  | Mobile Approval Inbox              | design only   |
| **N4**  | Approval Token Gate                | design only   |
| **N5**  | Merge / Deploy Approval Adapter    | design only   |

This document is the canonical anchor for all five.

---

## 1. Authority model

| Capability                                  | Owner today                                                        | After N1–N5                                                            |
| -------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Classify an action                           | `reporting.execution_authority.classify(...)`                      | unchanged                                                              |
| Emit a notification event                    | none today                                                         | future N2 dispatcher (read-only)                                       |
| Persist an approval row                      | `reporting.approval_inbox` (read-only emitter)                     | future N3 mobile inbox (write-only, append-only)                       |
| Mint an approval token                       | does not exist                                                     | future N4 (HMAC; never in repo; ≤15 min; one-time)                     |
| **Execute** merge / deploy                   | operator + GitHub branch protection + manual VPS deploy            | unchanged at the authority layer; N5 only adds a phone UI on top       |
| Autonomous merge / deploy                    | **forbidden, Level 6**                                             | **still forbidden, Level 6 stays permanently disabled**                |

The engine adds **operator UX**, not agent authority. Mobile approval
is human approval. There is no path by which N1–N5 grant autonomous
merge or deploy. There is no path by which they extend Step 5.1 / 5.2.

---

## 2. Hard constraints

This engine, in every track, must not:

- modify `.claude/**`;
- mutate research artefacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- flip `step5_implementation_allowed` (stays `False`);
- change `STEP5_ENABLED_SUBSTAGE` (stays `"none"`);
- store secrets, private keys, or VAPID keys in the repo;
- ingest any payload that has not first passed
  `reporting.agent_audit_summary.assert_no_secrets`;
- enable approval from a notification click alone (see §6);
- introduce a network call, subprocess, `gh`, `git`, `requests`,
  `urllib`, `socket`, `httpx`, or `aiohttp` import from any
  notification-engine module.

Each track ships its own AST-level forbidden-import scan to enforce
the relevant bullets.

---

## 3. Event taxonomy (N1, implemented)

### 3.1. Closed `event_kind` vocabulary

Pinned in [`reporting/notification_event.py`](../../reporting/notification_event.py)
as `EVENT_KINDS`. 31 members, ordered for byte-stable artefacts:

```
queue_item_proposed
queue_item_blocked
queue_item_human_needed
delegation_emitted
delegation_blocked
bugfix_candidate_proposed
bugfix_candidate_blocked
intake_candidate_proposed
intake_candidate_eligible
intake_candidate_blocked
step5_cycle_planned
step5_cycle_halted
step5_cycle_needs_human
release_gate_pass
release_gate_fail
release_gate_needs_human
operational_digest_emitted
e2e_proof_pass
e2e_proof_fail
pr_lifecycle_event
pr_merge_approval_required
pr_merge_approved
pr_merge_rejected
pr_merge_executed
deploy_approval_required
deploy_approved
deploy_rejected
deploy_executed
governance_violation_detected
secret_or_pii_redaction_event
audit_chain_anomaly
unknown_state
```

Adding a value requires a code change pinned by an updated unit test.

### 3.2. Closed `event_severity` vocabulary

Pinned as `EVENT_SEVERITIES`, ordered low → high:

```
silent
digest
push_info
push_action_required
approval_required
critical
```

### 3.3. Closed `decision_state` vocabulary

Pinned as `DECISION_STATES` (reserved for future N3):

```
pending
acknowledged
approved
rejected
expired
superseded
```

`approved` and `rejected` are writable **only** through the future N4
approval-token gate.

---

## 4. Severity routing (N1, implemented)

The default-severity table `EVENT_KIND_DEFAULT_SEVERITY` is pinned
verbatim in code and verified by `test_routing_table_pinned`. Every
member of `EVENT_KINDS` has exactly one default severity.

**Unknown event kinds fail closed** to `push_action_required` (the
constant `UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY`) — never `silent`,
never `digest`. Unknown is never silently OK.

### 4.1. `route_for(event_kind, *, risk_class=None, execution_authority_decision=None)`

Pure, deterministic, side-effect-free. Looks up the default and
applies the following minimal escalation rules (pinned by tests):

| Hint                                   | Effect                                                      |
| -------------------------------------- | ----------------------------------------------------------- |
| `risk_class="HIGH"`                    | floor at `push_info`                                        |
| `risk_class="UNKNOWN"`                 | floor at `push_action_required`                             |
| `execution_authority_decision="NEEDS_HUMAN"` | floor at `approval_required`                          |
| `execution_authority_decision="PERMANENTLY_DENIED"` | floor at `critical`                              |

Escalations only **lift** the severity; the routing-table default is
never downgraded. Future tracks (N2–N5) may add escalation rules only
via a code change pinned by an updated test.

---

## 5. Approval token design (future N4 only)

> Not implemented in N1. Documented here so emitters can reason about
> the eventual contract.

| Property                | Decision                                                        |
| ----------------------- | --------------------------------------------------------------- |
| Algorithm               | HMAC-SHA256                                                     |
| Secret location         | VPS environment, `secret_kid`-rotated; never in repo            |
| Expiry                  | ≤ 15 minutes; tunable downward only                             |
| Reuse                   | one-time; second verify returns 410 GONE                        |
| Bindings                | `pr_number`, `pr_head_sha`, `evidence_hash`, optional `release_tag` |
| Drift behaviour         | head_sha advance OR evidence_hash mutation invalidates the token |
| Replay protection       | 24 h server-side seen-nonce set                                 |
| Transport               | HTTPS only; never in URL query string                           |
| Audit                   | mint, verify, approve, reject, execute each append one ledger event with `autonomy_level_claimed=0` |

The token surface lives **server-side** (dashboard backend). The
PWA receives only a public `token_id`; the secret never leaves the
server.

---

## 6. Merge / deploy approval (future N5 only)

> Not implemented in N1. Documented here so reviewers can confirm
> the design preserves the no-autonomous-merge invariant.

### 6.1. The "no approval from notification click alone" rule

A push payload **never** contains a decision verb. Tapping the
notification opens the PWA at the inbox row. To approve or reject,
the operator must:

1. open the PWA (authenticated session);
2. read the bounded evidence summary;
3. tap **Approve** or **Reject**;
4. **re-authenticate** with the PWA session passphrase (one-shot
   per session, ≤ 15 min);
5. confirm in a modal that displays `pr_head_sha`, `evidence_hash`,
   `expires_at`;
6. submit. Only then does the dashboard backend mint and verify a
   token and invoke the merge adapter.

There is no swipe-to-approve. There is no approve-all. There is no
approval channel that does not pass through the PWA UI.

### 6.2. Merge flow (future N5)

```
ADE producer            →  pr_merge_approval_required
notification_dispatcher →  routes → severity = approval_required
mobile_approval_inbox   →  appends row, decision_state = pending
push engine             →  opaque payload to PWA
operator                →  opens PWA, reads evidence, taps Approve
dashboard backend       →  re-auth → mints token (head_sha + evidence_hash)
                       →  verifies token (one-time)
                       →  appends ledger event approved
                       →  invokes existing PR-merge path (gh pr merge --squash --delete-branch)
                       →  emits pr_merge_executed
```

If the PR's HEAD advances after token mint, verify fails closed and
the operator is shown a "head_sha drift" error. They re-open, re-read,
re-approve with a fresh token.

### 6.3. Deploy flow (future N5, design only)

Same shape as merge with three additions: token binding includes
`release_tag`; post-deploy emitter calls
`python -m reporting.development_release_gate` and only emits
`deploy_executed` when the gate is green; deploy approval can never
bind a `head_sha` of a non-`main` branch.

The deploy adapter is **described** but **not implemented** in
N1–N5. A separate later track (e.g. A20+) is where deploy adapters
land. Reason for the split: deploy touches the Hetzner VPS; the
merge adapter does not.

---

## 7. What N1 does NOT do

- N1 emits no notification.
- N1 mints no token.
- N1 opens no inbox row.
- N1 changes no dashboard route.
- N1 changes no frontend code.
- N1 changes no roadmap-status field.
- N1 marks no phase complete.
- N1 does not flip `step5_implementation_allowed`.
- N1 does not change `STEP5_ENABLED_SUBSTAGE`.
- N1 grants no agent any new authority.
- N1 enables no autonomous merge or deploy.
- Level 6 remains permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy. No approval can happen
  from a notification click alone.

---

## 8. Test coverage (N1)

Pinned in
[`tests/unit/test_notification_event.py`](../../tests/unit/test_notification_event.py):

- `EVENT_KINDS` order and content pinned exactly.
- `EVENT_SEVERITIES` order and content pinned exactly.
- `DECISION_STATES` order and content pinned exactly.
- Routing table covers every `event_kind` (no kind without a default).
- `route_for(known_kind)` returns the pinned default.
- `route_for(unknown_kind)` returns `push_action_required` (fail-closed).
- Risk-class and authority-decision escalations only lift severity,
  never lower it.
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `research`, `automation`, `broker`, `agent.risk`,
  `agent.execution`, `reporting.intelligent_routing`.
- Source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `gh`, `git`.
- Importing the module does not flip Step 5 invariants.
- This document mentions Level 6 only with the qualifier
  "permanently disabled".
- This document mentions "no approval from notification click alone"
  verbatim.

---

## 9. Track plan summary

| Track | Files (allowlist when implemented)                                                                 | Authority delta                |
| ----- | -------------------------------------------------------------------------------------------------- | ------------------------------ |
| **N1**  | `reporting/notification_event.py`, this doc, `tests/unit/test_notification_event.py`             | none                           |
| **N2**  | `reporting/notification_dispatcher.py` + status sibling, dashboard subscribe API, frontend stub  | none (read-only emitter)       |
| **N3**  | `reporting/mobile_approval_inbox.py` + status sibling, dashboard inbox API, frontend list/detail | new write-only artefact        |
| **N4**  | `reporting/approval_token_gate.py`, dashboard mint/verify API, audit hooks                       | tokens exist; not yet attached |
| **N5**  | merge adapter; deploy is design-only here                                                          | unlocks merge-from-mobile only |

Each track is one PR with its own no-touch scope and its own
revertibility. None of the tracks lifts the Level 6 ceiling — Level 6
stays permanently disabled per ADR-015 §Doctrine 1.
