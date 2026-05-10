# Step 5.1 readiness report — A20 (read-only projector)

> **Status:** Implemented (read-only). A20 **reports** preconditions
> for a future Step 5.1 enablement. A20 **never** flips
> ``step5_implementation_allowed`` and **never** changes
> ``STEP5_ENABLED_SUBSTAGE``.
>
> **Module:** [`reporting/development_step5_1_readiness.py`](../../reporting/development_step5_1_readiness.py)
>
> **Authority:** development-governance read-only.
> Step 5.1 / 5.2 remain BLOCKED. Level 6 stays permanently disabled
> per ADR-015 §Doctrine 1. Mobile approval is human approval, never
> autonomous merge or deploy. **No approval can happen from a
> notification click alone.**

---

## 1. Purpose

A20 joins the existing read-only ADE artefacts (intake bridge,
A16a promotion, A17 admission policy, A19 progress, Step 5.0
history) and emits a 13-check readiness report. The output answers:
**have all the preconditions a future, separately authorised Step
5.1 enablement would require been met?**

**Critically, A20 is the report — not the decision.** Even when
``readiness_overall == "ready_pending_operator_authorization"``, no
cap flip is implied. The only path that can flip
``step5_implementation_allowed`` is an operator-authored
governance-bootstrap PR that explicitly amends
[`reporting/development_step5_loop.py`](../../reporting/development_step5_loop.py),
[`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md),
and the autonomy-ladder doctrine. A20 surfaces the signal; it does
not act on it.

---

## 2. Hard constraints

A20, in this PR and at runtime, must not:

- flip ``step5_implementation_allowed``;
- change ``STEP5_ENABLED_SUBSTAGE``;
- mark any roadmap phase complete;
- mutate any upstream artefact;
- write to ``seed.jsonl`` / ``delegation_seed.jsonl`` /
  ``generated_seed.jsonl``;
- mutate canonical roadmap status fields;
- enable Step 5.1 or Step 5.2;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit ``.claude/**``;
- send a real push;
- mint approval tokens;
- merge or deploy.

A20 ships its own AST-level forbidden-import scan and a
source-text scan that asserts the literal token
``step5_implementation_allowed = True`` does not appear anywhere
in the module.

---

## 3. Closed vocabularies

### `readiness_overall` (3 values)

| Value                                       | Meaning                                                                  |
| ------------------------------------------- | ------------------------------------------------------------------------ |
| `not_ready`                                 | every check failed; the pipeline has not produced any signal yet         |
| `preconditions_partially_met`               | at least one check passed and at least one failed                        |
| `ready_pending_operator_authorization`      | every check passed; **still requires** a separate operator-authored PR   |

### `check_status` (3 values)

```
pass  fail  not_applicable
```

### `check_id` (13 values, closed)

```
step5_implementation_allowed_currently_false
step5_enabled_substage_currently_none
intake_bridge_artifact_present
promotion_artifact_present
admission_artifact_present
progress_artifact_present
step5_history_present
at_least_one_eligible_intake_candidate
at_least_one_admissible_admission_row
at_least_one_step5_plan_emitted_cycle
no_classification_drift_in_promotion_rows
no_blocked_admission_rows
no_phase_marked_complete_by_a19
```

The first two checks are the load-bearing ones — they assert that
the live cap is at the BLOCKED defaults. Those are the *required*
state for any future flip to be safe to author.

The last check, ``no_phase_marked_complete_by_a19``, is a
defense-in-depth check: A19 is forbidden from assigning
``phase_progress_state="complete"``, so a non-zero count there
would indicate either a bug in A19 or a manual edit — either way,
not a green-light for Step 5.1 enablement.

### Per-check row schema

```
check_id   status   value   threshold   note
```

---

## 4. Discipline invariants (emitted on every artefact)

```
flips_step5_implementation_allowed       = false
changes_step5_enabled_substage           = false
marks_any_phase_complete                 = false
writes_to_seed_jsonl                     = false
writes_to_delegation_seed_jsonl          = false
writes_to_generated_seed_jsonl           = false
mutates_canonical_roadmap_status_fields  = false
operator_promotion_required              = true
step5_implementation_allowed             = false
step5_enabled_substage                   = "none"
diagnostics_do_not_trade                 = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write.

---

## 5. CLI

```sh
python -m reporting.development_step5_1_readiness --no-write
python -m reporting.development_step5_1_readiness
```

Pure stdlib + read-only ADE deps. No subprocess, no network,
no `gh`, no `git`.

---

## 6. Authority chain summary

| Capability                                              | Today (post-A19) | After A20                                                  | After a separate operator-authored Step 5.1 enablement PR |
| ------------------------------------------------------- | ---------------- | ----------------------------------------------------------- | ---------------------------------------------------------- |
| Compute pipeline progress                                | A19              | unchanged                                                   | unchanged                                                  |
| Report Step 5.1 readiness                                | does not exist   | yes — A20 read-only                                         | unchanged                                                  |
| Flip ``step5_implementation_allowed``                    | forbidden        | **forbidden**                                               | yes — operator-authored governance-bootstrap PR only       |
| Change ``STEP5_ENABLED_SUBSTAGE``                        | forbidden        | **forbidden**                                               | yes — same PR                                              |
| Step 5.1 docs-only branch executor (A21)                 | does not exist   | does not exist                                              | conditional; remains its own gated PR                      |
| Autonomous merge / deploy                                | forbidden, Level 6 | unchanged — Level 6 stays permanently disabled            | unchanged — Level 6 stays permanently disabled             |

---

## 7. Test coverage

Pinned in [`tests/unit/test_development_step5_1_readiness.py`](../../tests/unit/test_development_step5_1_readiness.py):

- closed `READINESS_OVERALL`, `CHECK_STATUSES`, `CHECK_IDS`,
  `CHECK_ROW_KEYS` pinned exactly;
- the two Step 5 invariant checks always reflect the live constants
  (re-emit, never mutate);
- A20 NEVER assigns a readiness value that bypasses operator
  authorisation — the closed `READINESS_OVERALL` set's "all-pass"
  value is `ready_pending_operator_authorization`, not "ready" /
  "approved" / etc.;
- per-check row schema is exact;
- atomic write refuses any path outside
  `logs/development_step5_1_readiness/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: the literal `step5_implementation_allowed = True`
  must NOT appear in this module's source;
- importing the module does not flip Step 5 invariants;
- this doc states A20 is reports-only and that the cap flip
  remains operator-authored.

---

## 8. What A20 does NOT do

- A20 never flips `step5_implementation_allowed`.
- A20 never changes `STEP5_ENABLED_SUBSTAGE`.
- A20 never marks any roadmap phase complete.
- A20 never writes to any seed file.
- A20 never edits canonical roadmap docs.
- A20 does not enable Step 5.1 or Step 5.2.
- Step 5.1 / Step 5.2 remain BLOCKED.
- A21 (Step 5.1 docs-only branch executor) remains unimplemented
  and is permanently blocked while
  `step5_implementation_allowed=false`.
- A18 / N2b-3b / N3 (live wiring) / N4 (live wiring) / N5
  (merge adapter) / deploy adapter all remain unimplemented.
- Level 6 stays permanently disabled.
