# Step 5 — Bounded Autonomous Implementation Loop (Foundation)

> **Status:** Step 5 implementation remains **BLOCKED**.
> Autonomy-ladder Level 6 remains **permanently disabled** per
> ADR-015 §Doctrine 1. N5b Phase 4 production-merge authority
> remains **permanently denied for ADE**.
>
> This document specifies the **foundation** for the future
> bounded autonomous implementation loop. The foundation lives in
> [`reporting/roadmap_unit_status.py`](../../reporting/roadmap_unit_status.py)
> (the **A21a dynamic unit-status ledger**) and the matching A20e
> selector overlay in
> [`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py).
> The actual loop (branch / implement / PR / merge / deploy) is
> **not implemented in this PR**.
>
> **Phase:** Step 5 / A21 foundation. Each future slice (A21b,
> A21c, …) ships its own governance section in this doc plus its
> own implementation PR.
> **Authority class on this PR:** `AUTO_ALLOWED` (LOW risk,
> `operator_gate = none`, read-only deterministic projections +
> documentation).

---

## 1. Why a bounded autonomous loop is needed

After A20a–A20e shipped, the Roadmap v6 development queue is fully
deterministic and operator-readable, but the operator still has to
hand-walk Claude through every unit:

1. "Tell Claude to implement the next selected unit."
2. "Tell Claude to merge the PR."
3. "Tell Claude to mark the unit as merged in A20b's `_UNIT_SEED`."
4. "Tell Claude to continue."

That four-step manual cycle defeats the purpose of ADE. The
operator wants to focus on strategic QRE direction (which roadmap
phase to fund next, which research bets to take), **not** on
engineering-loop babysitting.

The bounded autonomous loop is the path off the babysitting
treadmill. The two foundation surfaces it requires — neither of
which executes anything — are:

* a **dynamic unit-status ledger** so completing a unit no longer
  requires editing
  [`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py)
  (the A20b static decomposition); and
* a **selector overlay** so A20e advances past completed units
  using the ledger instead of the static seed.

This PR ships exactly those two surfaces. It does **not** ship the
loop itself.

## 2. Hard permanent constraints (carried into every future slice)

Every future Step 5 / A21 slice — and every future bounded
autonomous loop run — MUST honour the following invariants without
exception. They are pinned on every emitted projection of A21a and
A20e:

* No live trading.
* No paper / shadow runtime activation unless a future explicit
  operator-approved roadmap phase enables it.
* No broker / order / risk / execution path changes.
* No capital allocation.
* No live / paper / shadow / broker credentials.
* No mutation of `research/research_latest.json`.
* No mutation of `research/strategy_matrix.csv`.
* No `.claude/**` mutation.
* No `dashboard/dashboard.py` mutation unless explicitly
  operator-approved.
* No approval-inbox mutation.
* No mutation routes.
* No approval buttons.
* No direct `main` push.
* No force push.
* No `--admin` merge.
* No hook bypass.
* No test weakening.
* No execution of `NEEDS_HUMAN` units.
* No execution of `PERMANENTLY_DENIED` units.
* No execution of `MEDIUM` / `HIGH` / `CRITICAL` risk units.
* No execution if `expected_files` / `forbidden_files` are missing.
* No execution if the selector result is ambiguous.
* No hidden LLM judgment overriding the queue.

`step5_implementation_allowed` remains `Final[bool] = False`
everywhere in the A21 / A20 surface. Autonomy-ladder Level 6
remains permanently disabled.

## 3. The two foundation surfaces shipped by this PR

### 3.1 A21a — Dynamic Unit Status Ledger

[`reporting/roadmap_unit_status.py`](../../reporting/roadmap_unit_status.py)
emits a deterministic projection at
`logs/roadmap_unit_status/latest.json` containing one
`DynamicUnitStatusRecord` per pinned ledger entry.

**Schema (10 fields, pinned by tests):**

| Field | Type | Notes |
|---|---|---|
| `unit_id` | string | implementation unit id |
| `status` | closed enum | one of `DYNAMIC_UNIT_STATUS` |
| `source` | closed enum | one of `DYNAMIC_STATUS_SOURCE` |
| `updated_at_utc` | string | ISO-8601 |
| `pr_number` | int | required for `merged` |
| `merge_sha` | string | required for `merged`; hex-only |
| `reason` | string | required for `merged` |
| `evidence` | list[string] | optional, bounded |
| `valid` | bool | computed by validator |
| `validation_reason` | closed enum | empty for valid records |

**Closed `DYNAMIC_UNIT_STATUS` vocabulary (7 values):**

* `not_started` — no work begun
* `in_progress` — implementation underway (future loop state)
* `pr_open` — PR opened, awaiting review / merge
* `merged` — PR squash-merged (terminal)
* `failed` — implementation aborted (e.g. CI failure)
* `blocked` — operator blocked (terminal)
* `skipped` — operator skipped (terminal)

**Closed `DYNAMIC_STATUS_SOURCE` vocabulary (5 values):**

* `pr_merge` — observed PR merge fact (bootstrap path used today)
* `operator_override` — operator manually set
* `loop_state` — set by a future Step 5 loop slice
* `ci_failure` — set by a future CI watcher slice
* `operator_block` — operator blocked

**Validation rules:**

* `merged` requires a positive `pr_number`, a hex `merge_sha`, and a
  non-empty `reason`. Any of these missing => `valid = False`.
* Unknown `status` or unknown `source` => `valid = False`.
* Empty `unit_id` => `valid = False`.
* Missing `updated_at_utc` => `valid = False`.
* `evidence` not a list / tuple => `valid = False`.
* `merge_sha` not hex-only (length 7..64) => `valid = False`.
* Duplicate `unit_id` => every record sharing that id is
  `valid = False` with `validation_reason = "duplicate_unit_id"`.
  No implicit resurrection of `merged` units.

**Status transition rules (advisory; selector enforces buildable
filter on its own):**

* `not_started -> in_progress`
* `in_progress -> pr_open`
* `pr_open -> merged`
* `pr_open -> failed`
* `in_progress -> failed`
* `not_started -> blocked`
* `not_started -> skipped`
* `failed -> blocked`
* `blocked`, `skipped`, `merged` are terminal unless an explicit
  operator-override record is appended.

**Atomic write allowlist:** every write target must contain
`logs/roadmap_unit_status/`. Any other path (including frozen
contract paths and `docs/development_work_queue/*.jsonl`) is
refused with `ValueError`.

**Imports:** stdlib + `reporting.roadmap_task_units` (read-only,
for the cross-reference module version). Nothing else.

### 3.2 A20e selector overlay

[`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py)
now reads the A21a artefact in addition to the existing A20b /
A20c upstreams. When a valid dynamic record exists for a unit:

* `effective_status = dynamic.status` (the static A20b status is
  still emitted on `status` for traceability);
* `dynamic_status_source = dynamic.source`;
* terminal dynamic statuses (`merged` / `blocked` / `skipped`)
  surface as the new `dynamic_status_terminal` block reason;
* non-terminal non-buildable dynamic statuses (`in_progress` /
  `pr_open` / `failed`) surface as the existing
  `non_buildable_status` block reason on the candidate.

When the dynamic record is invalid:

* `invalid_dynamic_status` is appended to `block_reasons`;
* the selector falls back to fail-closed via
  `FAIL_CLOSED_INVARIANT`.

When the artefact is absent:

* every unit silently falls back to its A20b static status.

When the artefact is corrupt JSON:

* the selector fails closed with `UPSTREAM_UNAVAILABLE` and the
  reason `malformed_dynamic_status_artifact:<error>`.

**Prerequisite check** likewise consults the dynamic ledger: a
prerequisite whose effective status is `merged` (via either the
A20b static seed or a valid A21a record) satisfies the
prerequisite. This is what removes the need to edit the A20b seed
every time a unit lands.

## 4. The stop-condition matrix (future loop)

The Step 5 bounded loop, when its execution slice ships, MUST stop
and produce an operator-readable report if any of the following
fire. None of these checks are implemented today; this section is
the **contract** the future slice will inherit.

### 4.1 Selection-level stop conditions

* Selected unit is not `AUTO_ALLOWED`.
* `risk_class` is not `LOW`.
* `operator_gate` is not `none`.
* `expected_files` is missing or empty.
* `forbidden_files` is missing or empty.
* `required_tests` is missing or empty.
* Selector result is ambiguous
  (`selection_status != "OK_SELECTED"`).
* The same unit_id is selected twice in a single run (the loop
  re-runs the selector after each merge; a repeat selection means
  the ledger update did not land or the A20a/A20b artefact
  re-projected to a stale state).
* Unknown risk / authority / status appears on the candidate.

### 4.2 Implementation-level stop conditions

* Generated diff touches **any** file in `forbidden_files`.
* Generated diff exceeds `expected_files` (any unlisted modified
  path).
* Any `live/**`, `paper/**`, `shadow/**`, `broker/**`,
  `agent/risk/**`, `agent/execution/**`, `automation/live_gate.py`,
  `dashboard/dashboard.py`, `.claude/**`, `.github/**`,
  frozen-contract path, or canonical roadmap path appears in the
  diff.
* Local tests fail.
* `python scripts/governance_lint.py` fails.
* Any pre-commit / pre-push hook blocks commit or push.
* Merge conflict occurs.

### 4.3 CI-level stop conditions

* Any required check fails: `lint`, `secret-scan`, `typecheck`,
  `unit (smoke + unit)`, `regression-fast`, `hook-tests`,
  `frontend`, `governance-lint`.
* PR mergeability is not `CLEAN`.
* Post-merge gates fail: `Build & Push Docker Image`,
  `Deploy VPS Dashboard`.

### 4.4 Ledger-level stop conditions

* Dynamic status update fails to write (atomic-write allowlist
  rejects the path; only `logs/roadmap_unit_status/` is allowed).
* Status ledger is inconsistent (duplicate `unit_id` produces
  `valid = False` records on the affected ids).
* A21a snapshot reports `fail_closed = true`.

### 4.5 Bound stop conditions

* `max_units_per_run` reached (see §5).
* Wall-clock budget exceeded (loop-config knob; not yet defined).

When any of these fire, the loop must:

1. Stop immediately.
2. Emit a deterministic stop report under `logs/step5_loop/`.
3. Surface a non-zero exit code to whatever invoked it (cron,
   GitHub Actions, manual operator CLI).
4. Never escalate, never `--admin`, never force-push, never
   bypass hooks.

## 5. `max_units_per_run` design

The future loop slice must accept a `max_units_per_run` parameter
(default proposed: **1**) which bounds how many implementation
units it will attempt in a single invocation. The default of `1`
means the loop performs **exactly one** implementation + merge
cycle and stops, even if A20e still recommends more eligible
units after the ledger update.

Rationale:

* `1` keeps the early loop runs operator-observable.
* `1` keeps the blast radius of any new bug to a single PR.
* `1` aligns with the existing PR-lifecycle pattern that every
  v3.15.16 unit has followed (one PR, one merge, one queue update).

The loop slice may expose `max_units_per_run` as a CLI argument
later, but it MUST never default to anything higher than 1 without
an explicit operator-authored PR raising the ceiling, and MUST
never accept a value higher than a small cap (≤ 5) without
ADR-014 / ADR-015 amendment.

`max_units_per_run` is **not implemented in this PR**. The number
is documented here as a binding design choice the future slice
must honour.

## 6. What this PR does **not** implement

The following are out of scope for the foundation slice. Each
requires its own operator-approved PR (likely A21b, A21c, …):

* Actual branch creation by the loop. No call to
  `git checkout -b`, no use of `git` or `gh` in any A21 module.
* Actual code implementation by the loop. No edits to any
  `reporting/**`, `tests/**`, or `docs/**` file from inside the
  loop.
* Actual PR creation by the loop. No call to `gh pr create`.
* Actual CI watcher. No reading of GitHub Actions runs.
* Actual squash-merge. No call to `gh pr merge`.
* Actual deploy watcher. No reading of `Deploy VPS Dashboard`
  runs.
* Repeated autonomous loop execution. The loop is one-shot, even
  when its execution slice ships.

## 7. Bootstrap status records

The bootstrap A21a seed pins exactly three merged records — the
v3.15.16 routing-layer units already on `main`:

| unit_id | PR | merge_sha |
|---|---|---|
| `u_v3_15_16_diagnostic_routing_signals_schema_001` | [#250](https://github.com/roudjy/trading-agent/pull/250) | `fcb1abbea4bd2ca190fe6e807b3dacd184faa702` |
| `u_v3_15_16_routing_explanation_reporter_001` | [#252](https://github.com/roudjy/trading-agent/pull/252) | `6f588a89b43a2cfec40f92252bde530220877b37` |
| `u_v3_15_16_routing_governance_doc_001` | [#254](https://github.com/roudjy/trading-agent/pull/254) | `df7dc6562ec3cd3a9f87e83e758881bd6fdb16f8` |

This means PR #254 does **not** require a follow-up
`chore/a20-mark-routing-governance-doc-merged` PR. The A20e
selector advances past PR #254's unit through the dynamic ledger,
not through editing the A20b static seed. This eliminates the
manual queue-status PR overhead for all three already-merged units
and for every future merged unit (assuming a future operator PR
appends a record).

## 8. Authority posture

Every A21a / A20e artefact pins (verbatim from the projection's
`ledger_invariants` / `selector_invariants` blocks):

* `step5_implementation_allowed = false`
* `no_step5_runtime = true`
* `no_level6 = true`
* `no_production_merge_authority = true`
* `no_runtime_trading_authority = true`
* `no_work_execution = true`
* `no_branch_creation = true`
* `no_pr_creation = true`
* `no_merge_or_deploy = true`
* `no_mutation_routes = true`
* `no_approval_buttons = true`
* `calls_execution_authority_classifier = false` (A20c is the only
  call site)
* `calls_llm_or_external_api = false`
* `uses_subprocess_or_network = false`
* `mutates_a20b_artifact = false` (A21a never edits the A20b seed)
* `writes_only_roadmap_unit_status_log = true`
* `writes_to_seed_jsonl = false`
* `writes_to_delegation_seed_jsonl = false`
* `writes_to_generated_seed_jsonl = false`
* `writes_to_approval_inbox = false`
* `writes_to_work_queue_jsonl = false`
* `merged_status_requires_evidence = true`
* `duplicate_unit_id_fails_closed = true`
* `invalid_record_fails_closed = true`
* `no_implicit_merged_resurrection = true`
* `consumes_dynamic_status_ledger = true`
* `dynamic_status_overrides_static_when_valid = true`
* `fail_closed_on_invalid_dynamic_status = true`
* `fail_closed_on_duplicate_dynamic_status = true`
* `dynamic_status_absence_falls_back_to_static = true`
* `merged_units_never_reselected = true`

## 9. Test coverage

Pinned in
[`tests/unit/test_roadmap_unit_status.py`](../../tests/unit/test_roadmap_unit_status.py)
(A21a, 61 tests):

* closed `DYNAMIC_UNIT_STATUS` vocabulary;
* closed `DYNAMIC_STATUS_SOURCE` vocabulary;
* closed `DYNAMIC_STATUS_INVALID_REASON` vocabulary;
* record schema (10 ordered fields) and projection schema
  (10 ordered fields);
* deterministic output with injected `generated_at_utc`;
* byte-identical output for identical input;
* atomic write only under `logs/roadmap_unit_status/`;
  rejects frozen contract paths and work-queue paths;
* `--no-write` does not write; `--status` does not write;
  `--indent 0` emits compact output;
* `merged` validation: positive `pr_number`, hex `merge_sha`,
  non-empty `reason`;
* unknown status / source / empty unit_id / missing
  `updated_at_utc` / non-list `evidence` fail closed via a
  closed-vocab `validation_reason`;
* duplicate unit_id fails closed deterministically (all duplicate
  records become `valid = False`);
* no implicit `merged` resurrection;
* bootstrap seed pins exactly the three v3.15.16 routing-layer
  PR / SHA / merged-status records;
* every projection pins `step5_implementation_allowed = false`,
  `no_step5_runtime = true`, `no_level6 = true`,
  `no_production_merge_authority = true`,
  `no_runtime_trading_authority = true`,
  `no_work_execution = true`, `no_branch_creation = true`,
  `no_pr_creation = true`, `no_merge_or_deploy = true`,
  `no_mutation_routes = true`, `no_approval_buttons = true`,
  `mutates_a20b_artifact = false`,
  `calls_execution_authority_classifier = false`,
  `calls_llm_or_external_api = false`,
  `uses_subprocess_or_network = false`;
* module-source scan: stdlib only; no `subprocess`, no `socket`,
  no `urllib`, no `http`, no `requests`, no `gh`, no `git`, no
  `os.system`, no dynamic-eval, no dynamic-exec, no GitHub API
  host, no LLM endpoint, no dashboard / automation / broker /
  agent.risk / agent.execution / research / live / paper /
  shadow / trading / reporting.execution_authority /
  reporting.roadmap_next_unit / reporting.roadmap_unit_authority
  / reporting.roadmap_task_catalog import.

Pinned in
[`tests/unit/test_roadmap_next_unit.py`](../../tests/unit/test_roadmap_next_unit.py)
(A20e selector overlay, additions):

* widened `NEXT_UNIT_BLOCK_REASON` to include
  `invalid_dynamic_status` and `dynamic_status_terminal`;
* widened `NEXT_UNIT_SOURCE` to include
  `logs/roadmap_unit_status/latest.json`;
* new closed vocab
  `NEXT_UNIT_DYNAMIC_STATUS_SOURCE` (6 values, `""` + 5
  dynamic-source values);
* widened candidate schema to include `effective_status`,
  `dynamic_status_source`, `source_status_artifact`;
* widened projection schema to include
  `source_status_schema_version`;
* dynamic merged status excludes unit from selector;
* dynamic status absent => fall back to static A20b status;
* invalid dynamic status fails closed via
  `FAIL_CLOSED_INVARIANT`;
* unknown dynamic status value fails closed;
* dynamic `pr_open` / `in_progress` / `failed` block the
  candidate;
* dynamic `merged` satisfies a prerequisite even if the static
  A20b status is `not_started`;
* the three v3.15.16 routing-layer merged units in the bootstrap
  seed are never reselected;
* malformed dynamic status artefact fails closed with
  `UPSTREAM_UNAVAILABLE`;
* static `status` field is preserved verbatim alongside
  `effective_status`;
* `source_status_artifact` pinned at
  `logs/roadmap_unit_status/latest.json`;
* selector invariants pin every new dynamic-overlay invariant
  listed in §8.

## 10. Cross-references

* [`docs/governance/roadmap_task_catalog.md`](roadmap_task_catalog.md)
  — A20 roadmap-to-task pipeline (the upstream consumer surface).
* [`docs/governance/step5_design.md`](step5_design.md) — the
  earlier Step 5 design doc. Step 5 implementation remains
  BLOCKED there too.
* [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — canonical authority mapping.
* [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — autonomy ladder; Level 6 is permanently disabled.
* [`docs/governance/no_touch_paths.md`](no_touch_paths.md) — the
  forbidden-surface list every future Step 5 slice inherits.
* [`docs/governance/execution_authority.md`](execution_authority.md)
  — canonical execution-authority policy (untouched by this PR).
* [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md)
  — ADE remains development workflow automation only.

## 11. Next recommended PR

A21b — bounded **dry-run** autonomous loop slice that:

* invokes A20e to read the next selected unit;
* validates the eight selection-level stop conditions in §4.1;
* prints a deterministic dry-run plan to stdout naming the unit,
  the expected files, the forbidden files, and the required
  tests;
* writes a dry-run report under `logs/step5_loop/dry_run/`;
* **does not** create a branch, **does not** edit any file,
  **does not** open a PR, **does not** merge, **does not**
  deploy.

A21b is the next safe step toward bounded autonomy. Its merge
remains blocked behind operator-explicit authorisation and an
updated A20b seed entry that lists it as an eligible unit.
