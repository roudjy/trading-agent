# Autonomous Development Step 5.0 Loop (A14)

> Canonical governance document for the Step 5.0 dry-run planner
> introduced as the first agent-implementable Step 5 slice.
> Read-only consumer of the four ADE-core peer artefacts (A8 work
> queue, A9 release gate via authority decision, A10 bugfix loop,
> A11 delegation). Pure deterministic scorer plus an atomic-write
> wrapper. Step 5 implementation remains BLOCKED.

## Status

Active. Modifications to this document require operator approval.

## What this is — and is not

Step 5.0 is the **first agent-implementable Step 5 slice** authorised
by:

- ADR-017 (`docs/adr/ADR-017-step5-autonomous-implementation-loop.md`,
  Accepted)
- `docs/governance/step5_design.md` §13 (first slice proposal)
- `docs/roadmap/autonomous_development.txt` §A14 (canonical
  roadmap anchor)

Step 5.0 is **dry-run-only**. It produces three artefacts under
`logs/step5_*/...`:

```text
logs/step5_plan/<cycle_id>.json       per-cycle plan, atomic
logs/step5_plan/history.jsonl         bounded 90-entry rolling window
logs/step5_loop/latest.json           loop snapshot, atomic
```

Step 5.0 is **not**:

- a real autonomous-implementation loop;
- a code-modification engine;
- a Step 5.1 / Step 5.2 capability;
- an authoriser for any real action;
- an LLM reasoner;
- a flip of `step5_implementation_allowed` (which remains the
  literal `False` constant in
  `reporting.development_operational_digest._evaluate_step5(...)`
  and in `reporting.development_step5_loop` itself);
- an autonomy-ladder amendment (Level 6 remains permanently
  disabled per ADR-015 §Doctrine 1).

## Architectural separation

ADE core (this module):

```text
reporting/development_step5_loop.py
```

Stdlib + ADE peer modules' read-only API only:

- `reporting.development_work_queue` (A8)
- `reporting.development_bugfix_loop` (A10)
- `reporting.development_delegation` (A11)
- `reporting.execution_authority` (read-only classifier reference)
- `reporting.approval_policy` (read-only classifier reference)
- `reporting.agent_audit` (audit-ledger writer; best-effort emission)

**No** `subprocess`, **no** `socket`, **no** `requests`/`urllib3`/`httpx`,
**no** `git` / `gh` invocations. AST-level pin in
`tests/unit/test_development_step5_loop.py::test_step5_module_no_subprocess_socket_or_network_imports`.

## Closed vocabularies

| Constant | Cardinality | Values |
|---|---|---|
| `STEP5_SUBSTAGES` | 4 | `none`, `5.0`, `5.1`, `5.2` |
| `STEP5_ENABLED_SUBSTAGE` | scalar | `none` (default-deny) |
| `STEP5_HALT_REASONS` | 5 | `needs_human`, `permanently_denied`, `out_of_allowlist`, `no_eligible_item`, `ok` |
| `STEP5_OUTCOME_KINDS` | 5 | `halt_needs_human`, `halt_permanently_denied`, `halt_out_of_allowlist`, `no_op_no_eligible_item`, `plan_emitted` |
| `STEP5_SOURCE_KINDS` | 3 | `delegation`, `bugfix`, `queue` |

Adding an entry to any of these tuples requires a code change pinned
by an updated test in `tests/unit/test_development_step5_loop.py`.

## Discipline invariants (load-bearing)

Every Step 5.0 plan artefact carries a `discipline_invariants` block:

```text
actually_modifies_target:           false
creates_real_branches:              false
opens_real_prs:                     false
mergeable_by_agent:                 false
deployable_by_agent:                false
mutates_qre_artifacts:              false
mutates_frozen_contracts:           false
mutates_protected_paths:            false
uses_subprocess_or_network:         false
operator_step5_authorisation_required: true
```

These keys are pinned at the test layer
(`test_dry_run_discipline_invariants_are_pinned_in_plan`).

## Selection algorithm

Per cycle, at most one item is processed. Order:

1. **Delegation** — sorted by `delegation_id` ASC.
2. **Bugfix candidate** — sorted by `candidate_id` ASC.
3. **Queue item** — sorted by `item_id` ASC.

`cycle_id` is `sha256("<source_kind>|<source_id>")` and is stable
across runs. The "no eligible item" cycle uses
`sha256("no_eligible_item|")` to make repeated empty ticks
byte-identical.

## Authority classification

Step 5.0 reads the upstream-recorded `execution_authority` decision
verbatim. It does **not** re-classify. Mapping:

| Upstream decision | `halt_reason` | `outcome` |
|---|---|---|
| `AUTO_ALLOWED` | `ok` | `plan_emitted` |
| `NEEDS_HUMAN` | `needs_human` | `halt_needs_human` |
| `PERMANENTLY_DENIED` | `permanently_denied` | `halt_permanently_denied` |
| missing / unknown | `needs_human` (fail-safe) | `halt_needs_human` |

The cycle exits 0 in every case — Step 5.0 is diagnostic, not gating.

## Output schemas

### `step5_plan.v1.json` (per-cycle plan)

```text
schema_version, module_version, report_kind, generated_at_utc,
cycle_id, source_kind, source_id, step5_enabled_substage,
step5_implementation_allowed, execution_authority_decision,
halt_reason, outcome, human_required, release_gate_required,
acceptance_criteria, target_paths, discipline_invariants,
vocabularies
```

### `step5_loop_latest.v1.json` (loop snapshot)

```text
schema_version, module_version, report_kind, generated_at_utc,
step5_enabled_substage, step5_implementation_allowed, presence,
current_plan, discipline_invariants, max_history_entries,
queue_module_version, release_gate_module_version,
bugfix_loop_module_version, delegation_module_version
```

### `step5_plan_history.v1.jsonl` (bounded append-only)

```text
generated_at_utc, cycle_id, source_kind, source_id,
execution_authority_decision, halt_reason, outcome,
module_version
```

Truncated to the last `MAX_HISTORY_ENTRIES = 90` lines on every
write. Atomic rewrite.

## Atomic-write guard

`_atomic_write_json` refuses any path whose POSIX form does not
contain `logs/step5_loop/` or `logs/step5_plan/`. Pinned by
`test_atomic_write_refuses_paths_outside_logs_step5`.

`_append_history` refuses any path outside `logs/step5_plan/`.

## CLI surface

```text
python -m reporting.development_step5_loop                   # writes plan + history + loop
python -m reporting.development_step5_loop --dry-run         # explicit dry-run flag (forward-compatible)
python -m reporting.development_step5_loop --no-write        # stdout only; no log file mutation
python -m reporting.development_step5_loop --indent 0        # compact JSON output
```

The module exits 0 on every diagnostic outcome, including halts.

## Audit-ledger event

Each persisted cycle emits **one**
`reporting.agent_audit.append_event(...)` call with:

- `actor: step5_loop:dry_run`
- `event: step5_cycle`
- `tool: development_step5_loop`
- `outcome: ok` (when `plan_emitted`) or `blocked` (otherwise)
- `block_reason: <halt_reason>` for halts
- `autonomy_level_claimed: 0` (always)
- `step5_cycle_id`, `step5_outcome`, `step5_halt_reason`,
  `step5_module_version`

Audit emission is best-effort: a raising audit ledger does not gate
the cycle. `--no-write` mode skips audit emission entirely.

## Kill-switch path (per `step5_design.md` §9.1)

1. **Per-cycle stop** — operator deletes
   `logs/step5_plan/<cycle_id>.json` (or stages the deletion in a
   docs-only PR). The next cycle re-evaluates idempotently.
2. **Sub-stage cap** — `STEP5_ENABLED_SUBSTAGE = "none"` is the
   default. Flipping to `"5.0"` / `"5.1"` / `"5.2"` requires a
   governance-bootstrap PR amending this module — never at runtime.
3. **Global ADE shutdown** — operator removes Step 5.0 from the
   ADE-core import list in
   `reporting.development_operational_digest` via a
   governance-bootstrap PR.

## Hard guarantees (pinned by tests)

- Stdlib + ADE peers + classifiers + audit ledger only (AST-level pin).
- No subprocess / socket / requests / urllib / httpx / aiohttp imports.
- No `gh` / `git` / `os.system` / `os.popen` / `subprocess.run`.
- No imports of `research`, `dashboard.dashboard`, `automation`,
  `broker`, `agent.risk`, `agent.execution`,
  `reporting.intelligent_routing`.
- `step5_implementation_allowed: False` literal constant.
- Deterministic snapshot under same `(inputs, generated_at_utc)`.
- Atomic-write guard rejects every non-`logs/step5_*/` target.
- Bounded history at 90 entries.
- Audit-ledger emission with `autonomy_level_claimed=0`.
- Discipline-invariants block byte-identical across cycles.

## Out of scope (deferred to later sub-stages)

- Step 5.1 (bounded edits on a feature branch, no merge) — separately
  authorised, requires §11 documentation modernization plus an ADR
  amendment plus fresh release-gate report + rollback drill plus
  explicit operator authorisation in the Step 5.1 PR body.
- Step 5.2 (merge recommendation) — requires the L4 unlock per
  ADR-015 (≥30 days L1–3 stable + ADR amendment).
- Real branch creation, real PR creation, real commit creation by
  the loop — none of these are reachable from Step 5.0.
- Autonomous merge / deploy — Level 6 permanently disabled per
  ADR-015 §Doctrine 1; Step 5 never reaches L5 or L6.
- QRE behavior, Intelligent Routing scoring, research artifact
  mutation, live / paper / shadow / risk / broker / execution code
  changes — all permanently outside Step 5's authority.

## Modifying this document

Standard governance discipline. Scope-bounded PR, CI green,
post-merge gates, no `--admin` merge. Material changes require
operator approval.
