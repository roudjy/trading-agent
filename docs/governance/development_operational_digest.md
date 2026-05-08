# Autonomous Development Operational Digest (A12)

> Canonical governance document for the Operational Digest
> introduced in A12. Read-only aggregator across the four ADE
> artifacts. No notifications. No dashboard work. No upstream
> mutation. Step 5 implementation remains operator-gated.

## Status

Active. Modifications to this document require operator approval.

## What this is — and is not

A12 aggregates the four ADE artifacts (A8 work queue, A9 release
gate, A10 bugfix loop, A11 delegation) into a single
operator-facing snapshot plus a bounded append-only history. The
digest computes a `step5_readiness` block whose `step5_ready` flag
is the closed-form measurable signal that A9–A12 are coherent
enough to consider Step 5 (Autonomous Implementation Loop)
implementation.

A12 is **not**:

- a notification service,
- a dashboard,
- a mutation surface for any upstream artifact,
- an authoriser for Step 5 implementation,
- an LLM reasoner.

`step5_ready=true` is **necessary but not sufficient**. The
operator authorises Step 5 separately.

## Architectural separation

ADE core (this PR):

```text
reporting/development_operational_digest.py
```

Stdlib + ADE peer modules' read-only API only
(`reporting.development_work_queue`,
`reporting.development_release_gate`,
`reporting.development_bugfix_loop`,
`reporting.development_delegation`). No subprocess, no network, no
`gh`, no `git`. AST-level pin forbids imports from
`dashboard`/`automation`/`broker`/`agent.risk`/`agent.execution`/
`research`/`reporting.intelligent_routing`.

There is no out-of-core collector for A12 — its inputs are the
four ADE artifacts, all already produced by ADE-core CLIs.

## Output — current snapshot

```
logs/development_operational_digest/latest.json
```

Top-level keys:

```
schema_version, module_version, report_kind, generated_at_utc,
note, presence_count, sources, operator_action_list,
step5_readiness, vocabularies,
queue_module_version, release_gate_module_version,
bugfix_loop_module_version, delegation_module_version,
max_history_entries, discipline_invariants
```

`sources` carries one summary per upstream artifact, with closed
counts projected onto closed vocabularies. Missing upstream
artifacts produce `present=false` summaries with zeroed counts —
the digest is robust to any subset of upstream artifacts.

`note` ∈ {`no_upstream_artifacts_present`,
`partial_upstream_artifacts_present`,
`all_upstream_artifacts_present`}.

## Output — bounded append-only history

```
logs/development_operational_digest/history.jsonl
```

Strict JSONL. Each line is a compact projection (no full source
payloads). Truncated to **`MAX_HISTORY_ENTRIES = 90`** (operator-
approved) most-recent entries. Rewritten atomically on every
append — never partial.

History entry fields:

```
generated_at_utc, module_version, presence_count,
step5_ready, criteria, operator_action_count,
queue_total, release_gate_total,
bugfix_loop_total, delegation_total
```

## Step 5 readiness criteria (closed)

```
release_gate_artifact_present
release_gate_no_protected_surface_leakage
bugfix_loop_artifact_present
bugfix_loop_no_test_weakening_proposals
delegation_artifact_present
delegation_no_fuzzy_parsing_evidence
queue_artifact_present
queue_human_needed_signal_meaningful
ade_qre_loose_coupling_clean
no_protected_path_violations
```

`step5_ready = all(criteria.values())`. Any future criterion must
be added to `STEP5_CRITERIA` and pinned by tests.

`step5_design_planning_allowed` is reported as **always true**
(operator-authored design planning is unrestricted).
`step5_implementation_allowed` is reported as **always false** in
this release — Step 5 implementation requires a separate operator
authorisation step that the digest is not authoritative for.

## Operator action list

Bounded, deduplicated, deterministic. At most
`MAX_OPERATOR_ACTIONS = 20` rows. Sorted by `(source, kind)`.

Closed `kind` vocabulary:

```
queue_human_needed_items_present
queue_blocked_items_present
release_gate_no_go_human_needed
release_gate_no_go_blocked
bugfix_repeated_validation_failure
bugfix_human_needed_candidates
delegation_ready_for_operator_promotion
delegation_human_needed_entries
```

## Hard guarantees (pinned by tests)

- Stdlib + ADE peer modules' read-only API only.
- No subprocess, no network, no `gh`, no `git`.
- AST-level forbidden-import pin.
- Atomic write only under
  `logs/development_operational_digest/latest.json`. The history
  guard refuses non-`logs/` paths.
- Reading upstream artifacts never mutates them (pinned by
  before/after byte comparison).
- Wrapper carries an explicit `discipline_invariants` block:
  ```
  mutates_upstream_artifacts: false
  sends_notifications: false
  writes_dashboard: false
  auto_authorises_step5: false
  operator_step5_authorisation_required: true
  ```

## CLI surface

```
python -m reporting.development_operational_digest            # writes latest + history
python -m reporting.development_operational_digest --no-write  # stdout only
```

## Modifying this document

Standard governance discipline. Scope-bounded PR, CI green,
post-merge gates, no `--admin` merge.
