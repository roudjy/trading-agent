# Queue Admission Policy — A17 (read-only, deterministic projector)

> **Status:** Implemented (read-only, **decides nothing**, **mutates
> nothing**). A17 reports policy decisions on A16a promotion-intent
> records. It does NOT promote. It does NOT write to any seed file.
>
> **Module:** [`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py)
> **Status reporter:** [`reporting/development_queue_admission_policy_status.py`](../../reporting/development_queue_admission_policy_status.py)
>
> **Output artefact:** `logs/development_queue_admission_policy/latest.json`
> **Status artefact:** `logs/development_queue_admission_policy_status/latest.json`

---

## 1. Purpose

A17 sits between **A16a Intake Candidate Promotion Staging** (which
emits promotion-intent records) and the future, operator-gated
**A18 Generated Queue Channel** (which would append to a separate
`generated_seed.jsonl` lane). A17 is the *policy* — the closed
rule table that says "these candidates are admissible to the queue,
those need a human, those are blocked outright" — that any future
auto-promotion bridge would consult.

Today A17 is consulted by no one in production. It is a pure
projector that emits a per-candidate admission decision so the
operator can inspect what A18 would do, before A18 is authorised
to do it.

A17 grants ADE **zero** new write authority. The active queue
(`docs/development_work_queue/seed.jsonl` and
`docs/development_work_queue/delegation_seed.jsonl`) remains
operator-authored. `generated_seed.jsonl` does not exist.

---

## 2. Hard constraints

A17, in this PR and at runtime, must not:

- write to `docs/development_work_queue/seed.jsonl`;
- write to `docs/development_work_queue/delegation_seed.jsonl`;
- write to any `generated_seed.jsonl`;
- mutate any A16a promotion artefact;
- mutate any roadmap status field;
- mark any roadmap phase complete;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- send a real push (no notification dispatch from A17 in any case);
- mint approval tokens;
- merge or deploy.

A17 ships its own AST-level forbidden-import scan to enforce these.

---

## 3. Closed vocabularies

Pinned in [`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py):

### `admission_decision` (5 values)

| Value                    | Meaning                                                                     |
| ------------------------ | --------------------------------------------------------------------------- |
| `admissible`             | passes every rule; would be eligible for an A18 generated-lane append       |
| `needs_human`            | requires operator approval before any promotion                             |
| `blocked`                | `PERMANENTLY_DENIED` upstream or post-reclassification — never admissible    |
| `duplicate_of_existing`  | candidate already appears in `seed.jsonl` or `delegation_seed.jsonl`        |
| `not_eligible_upstream`  | the upstream A16a `decision_state` or `intake_status` is not `eligible`     |

### `admission_reason` (11 values, closed)

```
auto_allowed_low_risk_eligible_promotion
needs_human_authority_decision
needs_human_unknown_or_invalid_risk
needs_human_classification_drift
needs_human_protected_target_path
blocked_authority_permanently_denied
blocked_classification_drift_to_denied
already_in_seed_jsonl
already_in_delegation_seed
upstream_intake_status_not_eligible
upstream_decision_state_not_eligible
```

### `promotion_target` (mirror of A16a)

```
none  (always returned by A17 — this PR does not promote)
development_work_queue   (reserved for future A18; A17 surfaces "would_target_lane")
development_delegation   (reserved for future A18)
```

### Per-row schema

23 keys, exact and ordered: `candidate_id`, `title`, `source_document`,
`source_kind`, `roadmap_phase`, `candidate_kind`, `required_agent_role`,
`risk_level`, `target_path`, `upstream_intake_status`,
`upstream_decision_state`, `upstream_execution_authority_decision`,
`reclassified_execution_authority_decision`, `classification_drift`,
`human_needed`, `human_needed_reason`, `admission_decision`,
`admission_reason`, `would_target_lane`, `already_in_seed_jsonl`,
`already_in_delegation_seed`, `policy_version`, `evaluated_at`.

---

## 4. Decision rules (closed table; first match wins)

| # | Condition                                                            | Outcome                          |
| - | -------------------------------------------------------------------- | -------------------------------- |
| 1 | `already_in_seed_jsonl == true`                                      | `duplicate_of_existing` / `already_in_seed_jsonl` |
| 2 | `already_in_delegation_seed == true`                                 | `duplicate_of_existing` / `already_in_delegation_seed` |
| 3 | upstream OR reclassified == `PERMANENTLY_DENIED`                     | `blocked` / `blocked_authority_permanently_denied` |
| 4 | `classification_drift == true` AND reclassified == `PERMANENTLY_DENIED` | `blocked` / `blocked_classification_drift_to_denied` |
| 5 | upstream OR reclassified == `NEEDS_HUMAN` (path is protected)        | `needs_human` / `needs_human_protected_target_path` |
| 6 | upstream OR reclassified == `NEEDS_HUMAN` (otherwise)                | `needs_human` / `needs_human_authority_decision` |
| 7 | operator `human_needed == true`                                      | `needs_human` / `needs_human_authority_decision` |
| 8 | `classification_drift == true` (not denied)                          | `needs_human` / `needs_human_classification_drift` |
| 9 | `decision_state != "eligible"`                                       | `not_eligible_upstream` / `upstream_decision_state_not_eligible` |
| 10 | `intake_status != "eligible"`                                       | `not_eligible_upstream` / `upstream_intake_status_not_eligible` |
| 11 | `risk_level` not in `RISK_CLASSES` OR == `UNKNOWN`                  | `needs_human` / `needs_human_unknown_or_invalid_risk` |
| 12 | `reclassified == AUTO_ALLOWED` AND `risk_level == LOW`              | `admissible` / `auto_allowed_low_risk_eligible_promotion` |
| 13 | default-deny                                                         | `needs_human` / `needs_human_authority_decision` |

`would_target_lane` is `development_work_queue` only when the row is
`admissible`; otherwise `none`.

---

## 5. Discipline invariants (emitted on every artefact)

```
writes_to_seed_jsonl              = false
writes_to_delegation_seed_jsonl   = false
writes_to_generated_seed_jsonl    = false
actually_modifies_target          = false
operator_promotion_required       = true
step5_implementation_allowed      = false
step5_enabled_substage            = "none"
diagnostics_do_not_trade          = true
```

---

## 6. CLI

```sh
python -m reporting.development_queue_admission_policy --no-write
python -m reporting.development_queue_admission_policy
python -m reporting.development_queue_admission_policy_status --no-write
```

Pure stdlib + `reporting.development_intake_promotion` (read-only) +
`reporting.execution_authority` + `reporting.development_work_queue`
(read-only) + `reporting.agent_audit_summary.assert_no_secrets`. No
subprocess, no network, no `gh`, no `git`.

---

## 7. Authority chain summary

| Capability                                         | Today (post-A16a)         | After A17                                        | After A18 (future, gated)                               |
| -------------------------------------------------- | ------------------------- | ------------------------------------------------ | -------------------------------------------------------- |
| Discover marker → candidate                         | Roadmap Intake Bridge     | unchanged                                        | unchanged                                                |
| Promotion-intent staging                            | A16a                      | unchanged                                        | unchanged                                                |
| Per-candidate admission decision                    | does not exist            | yes — A17 (read-only)                            | unchanged                                                |
| Append to operator-authored `seed.jsonl`            | operator only             | **operator only**                                | **operator only**                                        |
| Append to **new** `generated_seed.jsonl`            | does not exist            | does not exist                                   | A18 only, behind explicit operator go-signal             |
| Step 5.0 consumption                                | from delegation/bugfix/queue | unchanged                                     | unchanged + new `generated_seed.jsonl` lane              |
| Autonomous merge / deploy                           | **forbidden, Level 6**    | unchanged — Level 6 stays permanently disabled    | unchanged — Level 6 stays permanently disabled            |

---

## 8. Test coverage

Pinned in [`tests/unit/test_development_queue_admission_policy.py`](../../tests/unit/test_development_queue_admission_policy.py)
and [`tests/unit/test_development_queue_admission_policy_status.py`](../../tests/unit/test_development_queue_admission_policy_status.py):

- closed `ADMISSION_DECISIONS`, `ADMISSION_REASONS`,
  `PROMOTION_TARGETS`, `ADMISSION_SCHEMA_KEYS` pinned exactly;
- every rule row of §4 fires correctly on a synthetic A16a row;
- the live A15 → A16a candidate (
  `qre_v3_15_16_addendum_source_manifest_001`) lands as `admissible`
  / `auto_allowed_low_risk_eligible_promotion`;
- `would_target_lane = "development_work_queue"` only for admissible;
- atomic write refuses any path outside
  `logs/development_queue_admission_policy/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `gh`, `git`;
- importing the module does not flip Step 5 invariants;
- this doc states no seed writes and that A18 is operator-gated.

---

## 9. What A17 does NOT do

- A17 writes nothing to `seed.jsonl`.
- A17 writes nothing to `delegation_seed.jsonl`.
- A17 does not create `generated_seed.jsonl`.
- A17 does not change Step 5.0 logic.
- A17 does not flip `step5_implementation_allowed`.
- A17 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- A18 (generated queue channel), N3 (mobile inbox), N4 (token gate),
  N5 (merge adapter) all remain unimplemented.
- Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
