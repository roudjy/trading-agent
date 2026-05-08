# Intake Candidate Promotion Staging — A16a

> **Status:** Implemented (read-only, deterministic, **staging-only**).
>
> **Module:** [`reporting/development_intake_promotion.py`](../../reporting/development_intake_promotion.py)
> **Status reporter:** [`reporting/development_intake_promotion_status.py`](../../reporting/development_intake_promotion_status.py)
>
> **Output artifact:** `logs/development_intake_promotion/latest.json`
> **Bounded history:** `logs/development_intake_promotion/history.jsonl` (≤ 90 entries)
> **Status artifact:** `logs/development_intake_promotion_status/latest.json`
>
> **Authority:** development-governance read-only.
> A16a grants no new queue write authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

A16a closes the gap between "the Roadmap Intake Bridge has discovered
an eligible candidate" (PR #158, in production) and "Step 5.0 can plan
from a queue/delegation row" (existing). It is a **staging-only**
read-only projector:

1. Reads the upstream Roadmap Intake Bridge artefact at
   `logs/development_roadmap_intake/latest.json`.
2. **Re-runs** `reporting.execution_authority.classify(...)` on each
   candidate. The upstream-recorded decision is never trusted blindly.
3. De-duplicates against
   - the same cycle's seen `candidate_id`s,
   - the operator-authored
     [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl),
   - the operator-authored
     [`docs/development_work_queue/delegation_seed.jsonl`](../development_work_queue/delegation_seed.jsonl),
   - prior `(candidate_id, evidence_hash)` pairs in
     `logs/development_intake_promotion/history.jsonl`.
4. Computes the N1 default `notification_event` kind + severity for
   each row using `reporting.notification_event.route_for(...)`.
   **A16a never emits a notification** — the future N2 dispatcher
   does.
5. Emits a deterministic, closed-vocabulary promotion-intent record
   per candidate at `logs/development_intake_promotion/latest.json`,
   atomically.

**A16a does not** mutate any seed file. **A16a does not** write a
`generated_seed.jsonl`. Operator promotion of any candidate into
`seed.jsonl` or `delegation_seed.jsonl` remains an **explicit manual
action** — exactly the same posture as before A16a, just informed by
a deterministic intent projection.

---

## 2. Hard constraints

A16a, in this PR and at runtime, must not:

- write to `docs/development_work_queue/seed.jsonl` (the operator-authored
  queue seed remains operator-authored);
- write to `docs/development_work_queue/delegation_seed.jsonl` (same);
- create or write any `generated_seed.jsonl` (that is **A16b only**
  and is not implemented in this PR);
- auto-promote a candidate into the active queue;
- emit push notifications (N2 territory);
- open mobile approval inbox rows (N3 territory);
- mint approval tokens (N4 territory);
- merge or deploy (N5 / future);
- change Step 5.0 selection or classification logic;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- amend the N1 `EVENT_KINDS` closed vocabulary (uses only existing kinds);
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- edit canonical roadmap status fields;
- mark any roadmap phase complete.

A16a ships its own AST-level forbidden-import scan and source-text
scan to enforce the relevant bullets.

---

## 3. Closed vocabularies

Pinned in [`reporting/development_intake_promotion.py`](../../reporting/development_intake_promotion.py):

### `decision_state`

| Value              | Meaning                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------- |
| `pending`          | seen but not classified (fail-safe; not promoted)                                                  |
| `eligible`         | upstream `eligible` + re-classified `AUTO_ALLOWED` + `human_needed=false`; ready for operator-led promotion |
| `human_needed`     | upstream `human_needed`, re-classified `NEEDS_HUMAN`, or operator-explicit `human_needed=true`     |
| `blocked`          | re-classified `PERMANENTLY_DENIED`, or classification drift between upstream and re-classification |
| `rejected`         | upstream operator-terminal `rejected` state                                                        |
| `already_promoted` | candidate already present in `seed.jsonl` or `delegation_seed.jsonl` (id-based dedupe)             |

### `promotion_target`

| Value                     | Meaning                                                            |
| ------------------------- | ------------------------------------------------------------------ |
| `none`                    | the only legal value in A16a — **no automatic queue promotion**    |
| `development_work_queue`  | reserved for **A16b** (operator-gated; not implemented)            |
| `development_delegation`  | reserved for **A16b** (operator-gated; not implemented)            |

### `validation_warnings`

```
intake_artifact_absent
intake_artifact_unparseable
classification_drift
duplicate_candidate_id_in_cycle
duplicate_unchanged_history_entry
candidate_missing_target_path
candidate_invalid_risk_level
candidate_invalid_intake_status
```

### N1 integration vocabulary

A16a imports the entire closed taxonomy from
[`reporting.notification_event`](../../reporting/notification_event.py)
and uses **only** `route_for(...)`. No new event kinds, no new
severities are introduced.

---

## 4. Per-row schema (closed and ordered)

```
candidate_id
title
source_document
source_kind
roadmap_phase
candidate_kind
required_agent_role
risk_level
target_path
upstream_intake_status
upstream_execution_authority_decision
reclassified_execution_authority_decision
reclassified_execution_authority_reason
classification_drift               # bool
human_needed
human_needed_reason
acceptance_criteria
evidence_hash                       # sha256 over canonical evidence
notification_event_kind             # from N1
notification_event_severity         # from N1 routing
already_in_seed_jsonl               # bool
already_in_delegation_seed          # bool
duplicate_of_history_entry          # bool
decision_state                      # closed enum (see §3)
promotion_target                    # closed enum (see §3)
notes
```

Wrapper-level keys: `schema_version`, `module_version`, `report_kind`,
`generated_at_utc`, `step5_enabled_substage`,
`step5_implementation_allowed`, `intake_artifact_path`,
`intake_artifact_available`, `seed_path`, `seed_present`,
`delegation_seed_path`, `delegation_seed_present`, `history_path`,
`note`, `validation_warnings`, `vocabularies`, `counts`, `rows`,
`execution_authority_module_version`, `intake_module_version`,
`notification_event_module_version`, `discipline_invariants`.

---

## 5. Decision-state derivation (closed table)

Pinned in `_decision_state(...)` and tested verbatim:

| Condition (in priority order)                                                | Outcome                  |
| ---------------------------------------------------------------------------- | ------------------------ |
| `already_in_seed_jsonl OR already_in_delegation_seed`                        | `already_promoted`       |
| upstream-recorded decision differs from re-classification                    | `blocked` + `classification_drift` warning |
| re-classification is `PERMANENTLY_DENIED`                                    | `blocked`                |
| re-classification is `NEEDS_HUMAN`                                           | `human_needed`           |
| upstream `intake_status == "rejected"`                                       | `rejected`               |
| upstream `intake_status == "blocked"`                                        | `blocked`                |
| upstream `intake_status == "human_needed"`                                   | `human_needed`           |
| upstream `intake_status` not in {`eligible`, `proposed`}                     | `pending` + `candidate_invalid_intake_status` warning |
| operator-explicit `human_needed=true`                                        | `human_needed`           |
| upstream `intake_status == "eligible"` AND re-classification `AUTO_ALLOWED`  | `eligible`               |
| anything else (default-deny)                                                 | `pending`                |

`promotion_target` is always `none` in A16a — there is no path from
A16a's projector to a queue lane.

---

## 6. Discipline invariants (emitted on every artefact)

```
writes_to_seed_jsonl              = false
writes_to_delegation_seed_jsonl   = false
writes_to_generated_seed_jsonl    = false
actually_modifies_target          = false
creates_real_branches             = false
opens_real_prs                    = false
mergeable_by_agent                = false
deployable_by_agent               = false
fuzzy_parsing                     = false
uses_subprocess_or_network        = false
calls_llm_or_external_api         = false
mutates_research_artifacts        = false
mutates_roadmap_status_fields     = false
marks_phase_complete              = false
operator_promotion_required       = true
step5_implementation_allowed      = false
step5_enabled_substage            = "none"
diagnostics_do_not_trade          = true
```

---

## 7. CLI

```sh
# Pure inspection — does not write artifacts:
python -m reporting.development_intake_promotion --no-write
python -m reporting.development_intake_promotion_status --no-write

# Writes logs/development_intake_promotion[_status]/latest.json:
python -m reporting.development_intake_promotion
python -m reporting.development_intake_promotion_status
```

Both modules are pure-stdlib + the read-only ADE/reporting deps
(`execution_authority`, `notification_event`,
`development_roadmap_intake` for the writer module;
`development_intake_promotion`, `notification_event`,
`execution_authority` for the status module). No subprocess, no
network, no `gh`, no `git`.

---

## 8. Authority chain summary

| Capability                                          | Owner today                       | After A16a                       | After A16b (later, gated)                     |
| --------------------------------------------------- | --------------------------------- | -------------------------------- | ---------------------------------------------- |
| Discover marker → candidate                          | `development_roadmap_intake`      | unchanged                        | unchanged                                      |
| Re-classify candidate against authority              | none                              | `development_intake_promotion`   | unchanged                                      |
| Emit a "promotion intent" projection                 | none                              | `logs/development_intake_promotion/latest.json` | unchanged                       |
| Write to operator-authored `seed.jsonl`              | operator only                     | **operator only — never A16**    | **operator only — never A16**                  |
| Write to operator-authored `delegation_seed.jsonl`   | operator only                     | **operator only — never A16**    | **operator only — never A16**                  |
| Write to **new** `generated_seed.jsonl` channel      | does not exist                    | does not exist                   | A16b only, behind explicit operator go-signal  |
| Step 5.0 consumption                                 | from delegation/bugfix/queue      | unchanged                        | unchanged + new `generated_seed.jsonl` lane    |
| Autonomous merge / deploy                            | **forbidden, Level 6**            | unchanged — Level 6 stays permanently disabled | unchanged — Level 6 stays permanently disabled |

A16a is operator-supervised. **A16b stays paused** until the operator
sees the A16a projection in production, validates the dedupe and
drift behaviour, and explicitly authorises a generated-seed channel.

---

## 9. Test coverage

Pinned in
[`tests/unit/test_development_intake_promotion.py`](../../tests/unit/test_development_intake_promotion.py)
and
[`tests/unit/test_development_intake_promotion_status.py`](../../tests/unit/test_development_intake_promotion_status.py):

- closed `DECISION_STATES`, `VALIDATION_WARNINGS`, `PROMOTION_TARGETS`,
  `PROMOTION_SCHEMA_KEYS` pinned exactly;
- the current real candidate
  `qre_v3_15_16_addendum_source_manifest_001` becomes
  `decision_state="eligible"`, `promotion_target="none"` when the
  upstream Roadmap Intake artefact is fed in;
- non-eligible upstream statuses never become `eligible`;
- classification drift forces `blocked` plus the
  `classification_drift` warning;
- candidate present in `seed.jsonl` deduplicates to
  `already_promoted`;
- candidate present in `delegation_seed.jsonl` deduplicates to
  `already_promoted`;
- history `(candidate_id, evidence_hash)` dedupe sets
  `duplicate_of_history_entry`;
- atomic write refuses any path outside
  `logs/development_intake_promotion/`;
- module does **not** open `seed.jsonl` or `delegation_seed.jsonl`
  for writing (`O_WRONLY` / `"w"` / `"a"` checks);
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, no `gh`, no `git`;
- importing the module does **not** flip the Step 5 invariants on
  `reporting.development_step5_loop`;
- deterministic byte-stable output with an injected
  `generated_at_utc`;
- status summary counts mirror the upstream artefact across every
  closed vocabulary;
- this doc explicitly states no seed writes and that A16b is
  operator-gated.

---

## 10. What A16a does NOT do

- A16a writes nothing to `seed.jsonl`.
- A16a writes nothing to `delegation_seed.jsonl`.
- A16a does not create `generated_seed.jsonl`.
- A16a emits no notification.
- A16a opens no inbox row.
- A16a mints no token.
- A16a does not change Step 5.0 logic.
- A16a does not flip `step5_implementation_allowed`.
- A16a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- Level 6 stays permanently disabled. Mobile approval is human
  approval, not autonomous merge or deploy.
