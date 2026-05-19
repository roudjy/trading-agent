# Step 5 — Bounded Autonomous Implementation Loop

> **Status:** Step 5 broad implementation remains **BLOCKED**.
> Autonomy-ladder Level 6 remains **permanently disabled** per
> ADR-015 §Doctrine 1. N5b Phase 4 production-merge authority
> remains **permanently denied for ADE**. The A21c **bounded
> PR-creation slice** is the only carve-out, and is itself
> bounded (max 1 unit per run, no auto-merge, no deploy, no
> NEEDS_HUMAN, no MEDIUM/HIGH/CRITICAL risk).
>
> The Step 5 implementation surface today consists of:
>
> * **A21a** — dynamic unit-status ledger in
>   [`reporting/roadmap_unit_status.py`](../../reporting/roadmap_unit_status.py)
>   (foundation: replaces manual seed-edit PRs).
> * **A20e overlay** — selector consumes A21a in
>   [`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py)
>   (foundation: skips dynamically-merged units).
> * **A21c** — bounded autonomous PR runner in
>   [`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
>   (real branch + commit + push + PR creation for ONE safe unit;
>   no auto-merge, no deploy).
>
> **Phase:** Step 5 / A21 family. Each slice ships its own
> governance section in this doc plus its own implementation PR.
> **Authority class on every slice so far:** `AUTO_ALLOWED` (LOW
> risk, `operator_gate = none`, deterministic projections or
> bounded-execution code).

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

## 11. A21c — Bounded Autonomous PR Runner

[`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
is the **first real Step 5 execution surface**. It takes exactly
ONE A20e-selected unit, validates a closed set of safety gates,
creates one branch, invokes a pluggable implementation strategy,
verifies the resulting git diff is contained within the unit's
`expected_files`, runs required tests + smoke + governance lint,
commits, pushes, opens a PR, watches CI to first verdict, and
stops with a deterministic run report at
`logs/autonomous_pr_runner/latest.json`.

### 11.1 Hard boundaries (A21c)

A21c does **not**:

* squash-merge — the PR remains operator-driven to merge;
* use `--admin` — `--admin` does not appear in any shell-call
  argument list in the module code;
* force-push — `--force` does not appear in any shell-call
  argument list;
* bypass hooks — `--no-verify` / `--no-gpg-sign` do not appear;
* delete the branch after merge — the runner exits before merge;
* deploy anything — no `Build & Push Docker Image` invocation,
  no `Deploy VPS Dashboard` invocation, no `docker push`, no
  `ssh root@`;
* update the dynamic unit-status ledger to `merged` — A21a
  remains seed-driven; A21c emits its OWN report at
  `logs/autonomous_pr_runner/latest.json`;
* continue to a second unit — `max_units_per_run` is hard-capped
  at 1;
* touch any forbidden path — every safety gate refusal lists the
  full no-touch surface (see §11.4 below);
* mutate any approval inbox, mutation route, or approval button;
* grant runtime / trading / paper / shadow / live authority;
* call any LLM, external API, or hidden judgment on its own —
  the only LLM / external surface is opt-in through
  `--implementation-strategy external_command
  --implementation-command "<operator-supplied command>"`.

### 11.2 Import-safety contract

The module is **safe to import**. No subprocess is invoked on
import, no git / gh / network call is made on import, no file
write happens on import. The `subprocess` module is imported
**lazily** inside the real shell-runner factory so the top-level
`import reporting.autonomous_pr_runner` is fully side-effect free.
This is pinned by a module-source AST scan in
[`tests/unit/test_autonomous_pr_runner.py`](../../tests/unit/test_autonomous_pr_runner.py).

### 11.3 Closed vocabularies (pinned by tests)

* `RUN_STATUS` (13 values): `not_run`, `status_only`, `plan_only`,
  `refused_unsafe`, `executed_pr_opened`,
  `executed_blocked_at_implementation`,
  `executed_blocked_at_diff`, `executed_blocked_at_tests`,
  `executed_blocked_at_governance_lint`,
  `executed_blocked_at_commit`, `executed_blocked_at_push`,
  `executed_blocked_at_pr_create`, `executed_blocked_at_ci`.
* `SAFETY_GATE` (14 values): `selector_available`,
  `selection_status_ok`, `unit_present`,
  `auto_allowed_authority`, `low_risk`, `no_operator_gate`,
  `no_operator_go_required`, `expected_files_nonempty`,
  `forbidden_files_nonempty`, `required_tests_nonempty`,
  `no_forbidden_in_expected`, `not_terminal_status`,
  `max_units_per_run_one`, `implementation_strategy_configured`.
* `GATE_RESULT` (3 values): `PASS`, `FAIL`, `NOT_CHECKED`.
* `RUNNER_MODE` (3 values): `status_only`, `plan_only`, `run_one`.
* `IMPLEMENTATION_STRATEGY` (2 values): `none` (default,
  refuses), `external_command` (operator opts in).
* `STOP_REASON` (33 values): one closed-vocab reason per stop
  condition listed in §4.

### 11.4 Forbidden-path patterns (no-touch list)

Every entry of `FORBIDDEN_PATH_PATTERNS` is checked twice:

1. **Pre-execution:** the selected unit's `expected_files` is
   scanned. Any match refuses the run at the
   `no_forbidden_in_expected` gate with stop reason
   `forbidden_path_in_expected_files`.
2. **Post-implementation:** the git diff after the implementation
   strategy is scanned. Any match refuses the run at the
   diff-scope check with stop reason
   `diff_touches_forbidden_path`. The runner does NOT commit.

Pinned no-touch patterns: `.claude/`, `.github/`,
`dashboard/dashboard.py`, `automation/live_gate.py`, `broker/`,
`agent/risk/`, `agent/execution/`, `live/`, `paper/`, `shadow/`,
`trading/`, `docs/roadmap/Roadmap v6.md`,
`docs/roadmap/Roadmap v6 Addendum.md`,
`docs/roadmap/autonomous_development.txt`,
`docs/governance/execution_authority.md`,
`docs/governance/no_touch_paths.md`,
`reporting/execution_authority.py`,
`reporting/development_queue_admission_policy.py`,
`docs/development_work_queue/`, `tests/regression/`,
`research/research_latest.json`, `research/strategy_matrix.csv`,
`artifacts/`.

### 11.5 Implementation strategy injection

The runner exposes a `ImplementationStrategy` Protocol with one
method:

```python
def invoke(
    unit: dict[str, Any],
    *,
    repo_root: Path,
    shell: ShellRunner,
) -> ImplementationResult: ...
```

A21c ships **two** concrete strategies:

* **`none`** — the default. Refuses to run; the runner stops at
  the `implementation_strategy_configured` gate with stop reason
  `implementation_strategy_not_configured`. This is the safe
  default: bare `--run-one` does not act.
* **`external_command`** — the operator opts in via
  `--implementation-strategy external_command
  --implementation-command "<command>"`. The command is parsed
  via `shlex.split` and invoked through the injected shell
  runner. The command is expected to mutate the filesystem under
  the repo root in a way that satisfies the unit's
  `expected_files` contract. The runner does not interpret the
  command output; it only checks the exit code and the resulting
  diff.

Tests inject a `FakeImplementationStrategy` directly via the
`implementation_strategy=` keyword argument to `run_one(...)`. No
real shell command is invoked by unit tests.

### 11.6 CLI

```sh
# Safe default — status snapshot only:
python -m reporting.autonomous_pr_runner --status

# Plan-only — evaluate every safety gate against the current
# A20e recommendation but execute nothing:
python -m reporting.autonomous_pr_runner --plan-only

# Real execution (requires explicit operator strategy choice):
python -m reporting.autonomous_pr_runner \
    --run-one --max-units 1 \
    --implementation-strategy external_command \
    --implementation-command "<operator-supplied real command>"
```

The runner refuses `--max-units > 1` (A21c hard cap = 1) and
refuses `--implementation-strategy none` even when `--run-one` is
passed.

### 11.7 Authority pins (every emitted report)

Every report carries a `runner_invariants` block with these pins:

* `step5_implementation_allowed = false` (broad Step 5 stays
  BLOCKED; A21c carves out a bounded slice via
  `step5_enabled_substage = "a21c_bounded_pr_creation"`);
* `bounded_step5_pr_creation_only = true`;
* `max_units_per_run_hard_capped_at_one = true`;
* `import_is_side_effect_free = true`;
* `subprocess_module_used_only_inside_run_one = true`;
* `uses_subprocess_outside_run_one = false`;
* `uses_network = false`;
* `calls_llm_or_external_api = false`;
* `calls_execution_authority_classifier = false`;
* `no_runtime_trading_authority = true`;
* `no_step5_broad = true`;
* `no_level6 = true`;
* `no_production_merge_authority = true`;
* `no_auto_merge = true`;
* `no_admin_merge = true`;
* `no_force_push = true`;
* `no_hook_bypass = true`;
* `no_deploy = true`;
* `no_deploy_watcher = true`;
* `no_ledger_mutation = true`;
* `no_second_unit_continuation = true`;
* `no_branch_creation_outside_run_one = true`;
* `no_pr_creation_outside_run_one = true`;
* `no_mutation_routes = true`;
* `no_approval_buttons = true`;
* `no_approval_inbox_mutation = true`;
* `no_test_weakening = true`;
* `writes_only_autonomous_pr_runner_log = true`;
* `writes_to_dynamic_status_ledger = false`;
* `fail_closed_on_unsafe_unit = true`;
* `fail_closed_on_diff_outside_expected_files = true`;
* `fail_closed_on_forbidden_diff_path = true`;
* `fail_closed_on_test_failure = true`;
* `fail_closed_on_governance_lint_failure = true`;
* `fail_closed_on_ci_failure = true`.

### 11.8 Test coverage

Pinned in
[`tests/unit/test_autonomous_pr_runner.py`](../../tests/unit/test_autonomous_pr_runner.py)
(114 tests):

* import is side-effect free; `subprocess` is NOT at module top;
* closed vocabularies (5 of them) and schema field tuple are
  pinned exactly;
* every gate-failure path produces the correct closed-vocab stop
  reason;
* NEEDS_HUMAN / PERMANENTLY_DENIED authority refused;
* MEDIUM / HIGH / CRITICAL / UNKNOWN risk refused;
* non-`none` operator gate refused;
* `requires_operator_go = True` refused;
* missing `expected_files` / `forbidden_files` / `required_tests`
  refused;
* every no-touch path in `expected_files` refused (17
  parametrised cases);
* terminal static status (`merged` / `blocked` / `skipped` /
  `failed`) refused;
* `max_units > 1` refused (5 parametrised cases);
* default `implementation_strategy = "none"` refused;
* diff outside `expected_files` refused;
* diff touching a forbidden path refused;
* empty diff refused;
* required-tests failure surfaces `tests_failed`;
* governance-lint failure surfaces `governance_lint_failed`;
* implementation-strategy failure surfaces
  `implementation_strategy_failed`;
* branch-creation failure / branch-already-exists / push failure /
  PR-create failure / CI failure / CI timeout each surface the
  correct closed-vocab stop reason;
* no auto-merge invocation appears in module code (AST-stripped
  scan); no `--admin` argument list; no `--force` / `--no-verify`;
  no deploy invocation;
* injectable fakes for shell + implementation strategy; no real
  git / gh / subprocess invoked by unit tests;
* every `runner_invariants` pin asserted on every emitted report.

### 11.9 Bootstrap selection on merged main

When PR #255 (A21a / A20e overlay) merged, the A20e selector
recommended `u_v3_15_17_sampling_plan_reporter_001` as the next
eligible unit. The A21c runner, once merged and invoked with an
operator-supplied implementation command, will create branch
`step5-a21c/u_v3_15_17_sampling_plan_reporter_001` and attempt the
sampling-plan reporter unit. The runner does NOT pre-pick another
unit, does NOT escalate, and does NOT continue past one PR.

### 11.10 Future Step 5 slices

After A21c lands, the natural next slices are:

* **A21d** — bounded auto-merge for **PRs the runner itself
  opened**, plus a post-merge status-update step that appends a
  `merged` record to A21a's `_STATUS_LEDGER_SEED`. Hard-capped at
  PRs originated by the runner; never enabled for human-opened
  PRs. Squash-merge only; no `--admin`; no force-push; no hook
  bypass; CI-green required.
* **A21e** — bounded post-merge deploy watcher that observes
  `Build & Push Docker Image` + `Deploy VPS Dashboard` runs on
  the merge commit and reports their outcome. Read-only: never
  triggers a deploy, never re-runs a deploy, never modifies any
  deploy workflow.

Each future slice gets its own governance section in this doc and
its own operator-approved PR.

## 12. A21d — Bounded auto-merge for runner-originated PRs

[`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
now ships an **opt-in auto-merge phase** that runs only after the
PR-create + CI-watch phase has succeeded within the same
`run_one` invocation. The operator opts in via
`--auto-merge-runner-pr`. Without that flag the runner behaves
exactly as A21c did (stops at PR open + CI watch).

### 12.1 Auto-merge contract

When `--auto-merge-runner-pr` is passed and CI on the freshly
opened PR is green, the runner:

1. queries the PR metadata (`gh pr view --json title,body,mergeable,mergeStateStatus`);
2. queries the PR diff (`gh pr diff --name-only`);
3. evaluates ten auto-merge eligibility gates (§12.3);
4. squash-merges via `gh pr merge <N> --squash --delete-branch`
   (no admin override, no force-push, no hook bypass);
5. captures the merge SHA via `gh pr view --json mergeCommit`;
6. updates local main (`git checkout main && git pull --ff-only`);
7. watches the three post-merge workflows on the merge commit:
   Fast pre-merge gate, Build & Push Docker Image, Deploy VPS
   Dashboard;
8. on all-green: appends a single evidence-backed `merged`
   record to `logs/roadmap_unit_status/runner_merges.json` via
   `reporting.roadmap_unit_status.append_runner_merge_record`;
9. stops with `final_runner_status = "executed_pr_merged"`,
   `stop_reason = "ok_pr_merged"`.

### 12.2 What A21d does NOT do

- It does NOT auto-merge any PR that the runner did not open in
  the same `run_one` invocation.
- It does NOT auto-merge any PR whose branch does not start
  with `step5-a21c/`.
- It does NOT auto-merge any PR whose title does not contain the
  selected unit_id.
- It does NOT auto-merge any PR whose body does not contain the
  pinned runner-signature string.
- It does NOT pass `--admin` to any `gh pr merge` invocation.
- It does NOT force-push (`--force`, `--force-with-lease`).
- It does NOT bypass any hook (`--no-verify`, `--no-gpg-sign`).
- It does NOT continue to a second unit after merge.
- It does NOT trigger or rerun any deploy workflow; it observes
  the existing Deploy VPS Dashboard workflow read-only.
- It does NOT mutate the static A20b `_UNIT_SEED` or the static
  A21a `_STATUS_LEDGER_SEED`. The merged record lives in the
  auxiliary `runner_merges.json` artefact only.

### 12.3 Auto-merge eligibility gates

Ten closed-vocab gates, evaluated in defence-in-depth order:

| # | Gate | Refusal stop reason |
|---|---|---|
| 1 | `auto_merge_enabled` | `auto_merge_disabled` |
| 2 | `pr_runner_originated` | `not_runner_originated` |
| 3 | `pr_branch_matches_runner_convention` | `pr_branch_mismatch` |
| 4 | `pr_title_contains_unit_id` | `pr_title_missing_unit_id` |
| 5 | `pr_body_contains_runner_signature` | `pr_body_missing_runner_signature` |
| 6 | `pr_diff_no_forbidden_path` | `pr_diff_touches_forbidden_path` |
| 7 | `pr_diff_within_expected_files` | `pr_diff_outside_expected_files` |
| 8 | `ci_status_clean` | `ci_failed` |
| 9 | `no_admin_merge_required` | `branch_protection_requires_admin` |
| 10 | `mergeability_clean` | `mergeability_not_clean` |

The pre-flight gate `max_merges_per_run_one` is pinned at the
safety-gate evaluator and hard-caps merges at 1.

### 12.4 Evidence-backed ledger update

After post-merge gates are all green, the runner appends a
record to `logs/roadmap_unit_status/runner_merges.json` shaped
like:

```json
{
  "unit_id": "<selected unit id>",
  "status": "merged",
  "source": "runner_auto_merge",
  "updated_at_utc": "<UTC ISO-8601>",
  "pr_number": <int>,
  "merge_sha": "<hex SHA>",
  "reason": "auto-merged by A21d runner after CI green + post-merge gates green",
  "evidence": [
    "github_pr_number=<N>",
    "github_merge_sha=<sha>",
    "fast_pre_merge_gate=success",
    "build_and_push_docker_image=success",
    "deploy_vps_dashboard=success"
  ]
}
```

Validation rules on the append helper:

- pr_number > 0; merge_sha is hex (length 7..64); reason
  non-empty;
- source MUST be `"runner_auto_merge"`;
- status MUST be `"merged"`;
- unit_id MUST NOT already be present in the artefact (no
  implicit resurrection).

The artefact is local-only (`logs/` is gitignored). On the next
selector run with `repo_root` provided, A21a's `collect_snapshot`
overlays this artefact on top of the seed and the affected unit
becomes `effective_status = "merged"` in A20e. The static
`_UNIT_SEED` (A20b) and `_STATUS_LEDGER_SEED` (A21a) are
unchanged.

### 12.5 CLI

```sh
# Inspection (no execution; safe even with the flag):
python -m reporting.autonomous_pr_runner --status --auto-merge-runner-pr
python -m reporting.autonomous_pr_runner --plan-only --auto-merge-runner-pr

# Real execution: A21c PR creation, no auto-merge:
python -m reporting.autonomous_pr_runner \
    --run-one --max-units 1 \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"

# Real execution: A21d full pipeline (PR + CI watch + auto-merge):
python -m reporting.autonomous_pr_runner \
    --run-one --max-units 1 --max-merges 1 \
    --auto-merge-runner-pr \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"
```

The runner refuses `--max-merges > 1` (A21d hard cap = 1) at the
pre-flight safety gate.

### 12.6 New runner invariants (every emitted report)

A21d adds the following pins to `runner_invariants`:

- `bounded_step5_auto_merge_only_for_runner_pr = true`
- `auto_merge_requires_explicit_opt_in = true`
- `auto_merge_requires_ci_green = true`
- `auto_merge_requires_runner_origin = true`
- `auto_merge_squash_only_no_admin = true`
- `ledger_update_via_runner_merges_artifact_only = true`
- `max_merges_per_run_hard_capped_at_one = true`
- `no_arbitrary_pr_auto_merge = true`
- `no_non_runner_originated_pr_merge = true`
- `no_pr_merge_outside_auto_merge_phase = true`
- `no_deploy_invocation = true`
- `no_deploy_workflow_trigger = true`
- `no_static_seed_mutation = true`
- `no_a21a_seed_mutation = true`
- `no_a20b_seed_mutation = true`
- `fail_closed_on_non_runner_originated_pr = true`
- `fail_closed_on_dirty_mergeability = true`
- `fail_closed_on_post_merge_gate_failure = true`
- `fail_closed_on_ledger_write_failure = true`

### 12.7 Test coverage (35 new tests, 151 total)

Pinned in
[`tests/unit/test_autonomous_pr_runner.py`](../../tests/unit/test_autonomous_pr_runner.py):

- default `--run-one` (without the flag) never invokes
  `gh pr merge`;
- happy-path auto-merge: full pipeline through PR + CI + merge +
  post-merge gates + ledger write produces `executed_pr_merged`
  / `ok_pr_merged`;
- auto-merge writes the runner_merges artefact with the correct
  record shape, PR number, merge SHA, and three post-merge gate
  evidence entries;
- auto-merge command uses `--squash --delete-branch` only — no
  `--admin`, no `--force`, no `--no-verify`;
- gate-level refusal for: flag off, missing PR number, branch
  mismatch, title missing unit_id, body missing runner
  signature, diff outside expected_files, diff touches
  forbidden path, CI not green, dirty mergeability,
  branch-protection-requires-admin;
- pre-flight refusal for `max_merges > 1`;
- stop paths: merge command failed, merge SHA unknown,
  post-merge fast-gate failure, post-merge deploy failure
  (ledger NOT written on post-merge failure);
- runner-invariants block pins all A21d-specific posture flags.

### 12.8 What A21d still does NOT implement (future slices)

- **Multi-unit continuation** (A21e). After a successful merge,
  the runner stops. It does not re-run the selector and pick a
  second unit.
- **Promote runner_merges into the canonical seed.** The
  artefact remains local-only. A future operator-approved PR
  may promote runner_merges records into the pinned
  `_STATUS_LEDGER_SEED` to make merged status visible on CI.
- **Cross-invocation auto-merge.** A21d only merges PRs opened
  in the same `run_one` call.

## 13. A21e — Continuous autonomous conveyor

[`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
now ships an **opt-in continuous-conveyor mode** that wraps the
A21d cycle in a loop. The operator opts in via
`--run-continuous --auto-merge-runner-pr`. Without those flags
the runner behaves exactly as A21c / A21d.

### 13.1 Conveyor contract

The conveyor repeats the A21c → A21d cycle until ONE of the
following fires:

1. **No eligible unit** — A20e returns `NO_ELIGIBLE_UNITS`,
   `ALL_PERMANENTLY_DENIED`, or `ALL_BLOCKED_BY_PREREQUISITES`.
   Stops cleanly with
   `final_stop_reason = "ok_conveyor_completed_no_eligible_unit"`.
2. **Operator soft-stop** — `--stop-after-current` flag at
   start, or the runtime sentinel file
   `logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal` exists
   when the next iteration begins. The conveyor completes the
   current iteration (if any) and stops after its successful
   merge.
3. **Safety stop** — any A21c / A21d per-iteration safety stop
   reason (`unsafe_authority_class`, `tests_failed`,
   `governance_lint_failed`, `diff_outside_expected_files`,
   `mergeability_not_clean`, `branch_protection_requires_admin`,
   etc.).
4. **Technical stop** — selector unavailable, push failed, CI
   failed, post-merge gate failed, merge SHA unknown, selector
   re-selected an already-merged unit, selector re-selected the
   same unit twice without status change, status-artefact
   refresh failed.

There is **no artificial unit-count cap** and **no hard
wall-clock budget**. The conveyor runs until one of the four
conditions above fires.

### 13.2 What A21e does NOT do

- It does NOT impose a `max_units_per_run` budget on the
  conveyor. Per-iteration caps stay at 1 (each iteration creates
  1 PR + 1 merge), but the conveyor runs unbounded iterations
  until a real stop fires.
- It does NOT impose a wall-clock budget. The operator decides
  when to stop via `--stop-after-current`, the sentinel file, or
  Ctrl+C.
- It does NOT impose a per-unit timeout as a queue policy.
  Per-shell-command timeouts remain (CI watch defaults to
  1800s) but those are per-command, not per-unit-as-queue.
- It does NOT auto-merge any PR that the conveyor did not open
  in the current invocation. Each iteration opens a fresh PR and
  uses that PR's number directly for the auto-merge phase.
- It does NOT pass `--admin`, `--force`, or `--no-verify` to any
  shell call. Pinned by an AST-stripped module-source scan.
- It does NOT trigger any deploy workflow. The post-merge gate
  watch remains read-only (`gh run list` + `gh run watch
  --exit-status`).
- It does NOT mutate the static A20b `_UNIT_SEED` or A21a
  `_STATUS_LEDGER_SEED`. Each successful merge appends to
  `logs/roadmap_unit_status/runner_merges.json`; the conveyor
  also refreshes `logs/roadmap_unit_status/latest.json` between
  iterations so the selector picks up the overlay.

### 13.3 Operator soft-stop

Two equivalent mechanisms:

- **Pre-start flag:** `--stop-after-current` on the CLI. The
  conveyor completes one iteration and stops with
  `final_stop_reason = "conveyor_operator_stop_after_current"`.
- **Runtime sentinel file:** the operator creates
  `logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal` (any
  content) on the local filesystem. The conveyor checks this
  file at the start of every iteration. If present, the
  remainder of the run is treated as `stop_after_current = True`
  and the conveyor exits with
  `final_stop_reason = "conveyor_operator_stop_signal_file"`.

For harder stops, the operator sends SIGINT (Ctrl+C). The
process terminates without writing the final aggregate report.

### 13.4 Pre-flight: auto-merge required

The conveyor refuses to start without `--auto-merge-runner-pr`.
Without auto-merge, iteration 2's selector would re-pick the
same unit (status hasn't flipped to merged), the
same-unit-without-status-change guard would trip, and the
conveyor would stop. Refusing pre-flight is cleaner. Refusal
stop reason: `conveyor_requires_auto_merge`.

### 13.5 Status-artefact refresh between iterations

After each successful auto-merge, the conveyor calls
`reporting.roadmap_unit_status.collect_snapshot(repo_root=root)`
and writes the result to `logs/roadmap_unit_status/latest.json`.
This makes the next iteration's A20e selector see the freshly
merged unit as `effective_status = "merged"` and skip it.

If the refresh write fails, the conveyor stops with
`final_stop_reason = "conveyor_status_artifact_refresh_failed"`.

### 13.6 CLI

```sh
# Inspection (no execution, no writes):
python -m reporting.autonomous_pr_runner --status
python -m reporting.autonomous_pr_runner --plan-only

# A21c single-PR cycle (no auto-merge):
python -m reporting.autonomous_pr_runner \
    --run-one --max-units 1 \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"

# A21d single-PR cycle + bounded auto-merge:
python -m reporting.autonomous_pr_runner \
    --run-one --max-units 1 --max-merges 1 \
    --auto-merge-runner-pr \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"

# A21e continuous conveyor (run until queue empty or
# operator-stop):
python -m reporting.autonomous_pr_runner \
    --run-continuous --auto-merge-runner-pr \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"

# A21e continuous conveyor + soft-stop after current iteration:
python -m reporting.autonomous_pr_runner \
    --run-continuous --auto-merge-runner-pr --stop-after-current \
    --implementation-strategy external_command \
    --implementation-command "<cmd>"
```

The operator can also create the runtime sentinel file at any
time to stop a running conveyor cleanly:

```sh
mkdir -p logs/autonomous_pr_runner
touch logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal
```

### 13.7 Conveyor report shape

The conveyor's aggregate report is written to
`logs/autonomous_pr_runner/latest.json` with
`report_kind = "autonomous_pr_runner_conveyor"`. Fields are
pinned by `CONVEYOR_REPORT_FIELDS`: `mode = "run_continuous"`,
`started_at_utc`, `ended_at_utc`, `auto_merge_enabled`,
`stop_after_current_requested`, `units_attempted`,
`units_pr_opened`, `units_merged`, `units_blocked`,
`unit_ids_processed[]`, `pr_numbers_opened[]`, `merge_shas[]`,
`post_merge_gates_by_iteration[][]`,
`selector_results_by_iteration[]`, `iteration_summaries[]`,
`final_iteration_full_report`, `final_stop_reason`,
`final_selector_status`, `final_runner_status`,
`next_required_operator_action`, plus the standard
`step5_enabled_substage` / `step5_implementation_allowed` /
`runner_invariants`.

### 13.8 New runner invariants pinned by A21e

- `conveyor_has_no_artificial_max_units_cap = true`
- `conveyor_has_no_wall_clock_budget_stop = true`
- `conveyor_has_no_per_unit_timeout_as_queue_policy = true`
- `conveyor_stops_only_on_no_eligible_or_safety_or_operator_stop = true`
- `conveyor_re_runs_selector_between_iterations = true`
- `conveyor_refreshes_status_artifact_between_iterations = true`
- `conveyor_status_update_only_via_runner_merges_artifact = true`
- `conveyor_operator_soft_stop_supported = true`
- `conveyor_never_merges_arbitrary_prs = true`
- `conveyor_never_continues_past_same_unit_without_status_change = true`
- `conveyor_never_re_selects_already_merged_unit = true`

### 13.9 Test coverage (33 new conveyor tests, 186 total)

Pinned in
[`tests/unit/test_autonomous_pr_runner.py`](../../tests/unit/test_autonomous_pr_runner.py):

- conveyor report / iteration / selector schema field tuples
  exactly pinned;
- new vocab values pinned (RUN_STATUS, RUNNER_MODE, STOP_REASON
  conveyor extensions);
- `--status` with conveyor flags does NOT execute anything;
- conveyor refuses to start without auto-merge;
- happy-path: one eligible unit processed → next selector
  returns no_eligible → conveyor completes cleanly;
- happy-path: two eligible units processed sequentially in one
  invocation; runner_merges artefact carries both records;
- the conveyor's aggregate report is written with
  `report_kind = "autonomous_pr_runner_conveyor"`;
- `--stop-after-current` flag stops after one successful merge;
- runtime sentinel file `STOP_AFTER_CURRENT.signal` stops after
  the next successful merge;
- safety stops (NEEDS_HUMAN authority, non-LOW risk, forbidden
  diff, mergeability dirty, tests failed) refuse and surface the
  specific stop reason from the failing iteration;
- technical stops (CI failure, post-merge gate failure) surface
  the specific stop reason;
- empty selector at start completes with
  `ok_conveyor_completed_no_eligible_unit`;
- conveyor records selector results per iteration;
- runner_invariants pin all A21e-specific flags;
- AST-stripped module-source scan: no `--admin`, no `--force`,
  no `--no-verify`, no deploy invocation, no
  `workflow_dispatch` trigger;
- every `apr.run_continuous` call in the unit tests explicitly
  passes `shell=` and `implementation_strategy=` so the real
  shell factory is never reached.

### 13.10 What A21e still does NOT implement

- **Cross-invocation auto-merge** — the conveyor only merges
  PRs opened in the current invocation.
- **Promote `runner_merges.json` into the canonical seed** —
  the artefact remains local-only.
- **Signal-handler-based hard stop** — Ctrl+C kills the process
  uncleanly. A future slice may add a SIGINT handler.

## 14. A22 strategic mandate integration

[`docs/governance/strategic_roadmap_execution_mandate.md`](strategic_roadmap_execution_mandate.md)
adds the operator's strategic execution mandate. The A21 family
now accepts **STRATEGICALLY_PREAPPROVED** units (mandate-promoted
NEEDS_HUMAN units that satisfy every mandate criterion) as
eligible for the conveyor, alongside AUTO_ALLOWED units.

### 14.1 Runner safety-gate widening

A22 widens two A21c / A21d / A21e safety gates:

- `auto_allowed_authority` — accepts
  `AUTO_ALLOWED` OR `STRATEGICALLY_PREAPPROVED`.
- `low_risk` — accepts `LOW` always; accepts `MEDIUM` only when
  the unit's authority class is `STRATEGICALLY_PREAPPROVED`.

`HIGH` / `CRITICAL` / `UNKNOWN` risk is still refused everywhere.
`NEEDS_HUMAN` / `PERMANENTLY_DENIED` authority is still refused
for execution. Per-unit safety gates (`expected_files`,
`forbidden_files`, `required_tests`, diff-scope,
mergeability-clean, post-merge-gate-green) are unchanged.

### 14.2 New runner invariants pinned by A22

Every report (run-one, plan, status, conveyor) now pins:

- `accepts_strategically_preapproved_authority = true`
- `accepts_medium_risk_only_when_strategically_preapproved = true`
- `never_accepts_needs_human_authority_for_execution = true`
- `never_accepts_permanently_denied_authority_for_execution = true`
- `never_accepts_high_or_critical_risk = true`
- `elevated_exceptions_remain_operator_driven = true`

### 14.3 Elevated exceptions remain operator-driven

Two surfaces are NEVER processed by the conveyor:

- **Frozen contracts**: `research/research_latest.json`,
  `research/strategy_matrix.csv`.
- **Dashboard / UI mutation**: `dashboard/dashboard.py`, UI
  mutation buttons, approval buttons, mutation routes.

These remain PERMANENTLY_DENIED at the classifier level. Any
change to them requires an explicit operator-authored PR
outside the autonomous runner — see
[`strategic_roadmap_execution_mandate.md`](strategic_roadmap_execution_mandate.md)
§4 for the elevated-exception policy.

## 15. Next recommended operator action

After PR #258 (A21e) merges, the operator can — from their local
laptop — run the continuous conveyor against the live queue:

```sh
python -m reporting.autonomous_pr_runner \
    --run-continuous --auto-merge-runner-pr \
    --implementation-strategy external_command \
    --implementation-command "<operator-supplied real command>"
```

The conveyor will process every AUTO_ALLOWED / LOW / `gate=none`
unit in the A20e queue, stopping only when the queue is
exhausted, a safety or technical stop fires, or the operator
soft-stops via the flag or sentinel file. No `--admin`, no
force-push, no hook bypass, no deploy invocation. Post-merge
gates remain read-only-observed. Step 5 broad implementation
remains BLOCKED, Level 6 remains permanently disabled, N5b
Phase 4 production-merge authority remains permanently denied
for ADE.
