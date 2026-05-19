# Strategic Roadmap Execution Mandate (A22)

> **Status:** A22 — operator's pre-approval policy for the
> Roadmap v6 + Addendum 1/2/3 research-intelligence work-track.
> Encoded deterministically in
> [`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py)
> as a post-process that promotes eligible NEEDS_HUMAN units to a
> new authority class `STRATEGICALLY_PREAPPROVED`. The selector
> ([`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py))
> and the autonomous PR runner
> ([`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py))
> both accept STRATEGICALLY_PREAPPROVED units automatically (no
> per-unit operator-go required).
>
> Step 5 broad implementation remains **BLOCKED** outside the
> bounded A21 / A22 slices. Autonomy-ladder Level 6 remains
> **permanently disabled** per ADR-015. N5b Phase 4 production-
> merge authority remains **permanently denied for ADE**.
>
> **The strategic mandate NEVER overrides:**
>
> - any **PERMANENTLY_DENIED** authority class;
> - **HIGH / CRITICAL / UNKNOWN** risk class;
> - the always-forbidden runtime / trading / paper / shadow /
>   broker / risk / execution surfaces;
> - `--admin` restrictions, force-push restrictions, hook-bypass
>   restrictions, direct-deploy restrictions;
> - the runner's per-iteration safety gates (`expected_files`,
>   `forbidden_files`, `required_tests`, diff-scope, CI-green,
>   mergeability-clean, post-merge-gate-green, etc.).

---

## 1. Why the strategic mandate exists

The operator's goal is to execute the full Roadmap v6 +
Addendum 1/2/3 research-intelligence work-track as quickly as
possible while preserving hard safety boundaries. Before A22:

- Many MEDIUM / NEEDS_HUMAN research-scaffold units would block
  the conveyor (A21e). Each one would require an explicit
  operator decision, defeating the purpose of the conveyor.
- The operator does **not** want to babysit individual approvals
  on read-only scaffold / reporting / docs / tests units.
- The operator **does** want ADE to stop on real trading /
  runtime / broker / risk / live boundaries.

The mandate encodes the operator's pre-approval **once**, in
code, with explicit deterministic criteria. The conveyor then
applies that pre-approval to every matching unit automatically.

## 2. The hard permanent constraints

These hold for every conveyor iteration. The mandate never
relaxes any of them.

### 2.1 Always blocked (PERMANENTLY_DENIED — never auto-merged)

- `dashboard/dashboard.py` (unless an explicit elevated
  exception PR; see §4)
- `.claude/**`
- `.github/**`
- `research/research_latest.json` (frozen contract; §4)
- `research/strategy_matrix.csv` (frozen contract; §4)
- `automation/live_gate.py`
- `broker/**`
- `agent/risk/**`
- `agent/execution/**`
- `live/**`
- `paper/**`
- `shadow/**`
- `trading/**`
- `docs/roadmap/Roadmap v6.md`
- `docs/roadmap/Roadmap v6 Addendum.md`
- `docs/roadmap/autonomous_development.txt`
- `docs/governance/execution_authority.md`
- `docs/governance/no_touch_paths.md`
- `reporting/execution_authority.py`
- `reporting/development_queue_admission_policy.py`
- `docs/development_work_queue/*.jsonl`
- `tests/regression/**`
- any live / broker / risk / execution credential or endpoint
  path
- any frozen schema under `artifacts/`

A unit whose `expected_files` includes any of these surfaces is
classified `PERMANENTLY_DENIED` by the canonical
`reporting.execution_authority` classifier. The A22 post-process
**never** promotes `PERMANENTLY_DENIED` to anything else.

### 2.2 Always blocked — semantic surfaces

The mandate never promotes a unit that would introduce any of:

- order placement;
- broker calls;
- capital allocation;
- risk mutation;
- paper / shadow / live runtime activation;
- approval buttons;
- mutation routes;
- executable strategy generation;
- trading authority.

These map to path-level denials via the canonical classifier,
so the path scan in §2.1 already catches them at
classification time.

## 3. The strategic mandate criteria

A unit is **STRATEGICALLY_PREAPPROVED** if and only if EVERY
condition below is true.

### 3.1 Phase (operator-pre-approved roadmap track)

`phase` must be in
[`reporting.roadmap_unit_authority._MANDATE_PHASES`](../../reporting/roadmap_unit_authority.py):

- `v3.15.16`
- `v3.15.17`
- `v3.15.18`
- `v3.15.19`
- `v3.15.20`
- `addendum_1`
- `addendum_2`
- `addendum_3`

`addendum_2` and `addendum_3` are reserved but **not yet
repo-resident** — adding units in those phases requires a
catalog-expansion PR first (see §5).

### 3.2 Target layer (research / scaffold / docs / tests /
reporting)

`target_layer` must be in
`_MANDATE_TARGET_LAYERS`:

- `reporting`
- `research`
- `governance`
- `test`
- `diagnostic`
- `external_intelligence`
- `preset`
- `evidence`

Layers like `broker`, `agent.risk`, `agent.execution`, `live`,
`paper`, `shadow`, `trading`, `dashboard` are explicitly NOT in
this set. Even if a unit's `expected_files` didn't hit a
PERMANENTLY_DENIED path, a non-mandate target layer prevents
promotion.

### 3.3 Risk class

`risk_class` must be in `_MANDATE_RISK_CLASSES`:

- `LOW`
- `MEDIUM`

`HIGH`, `CRITICAL`, `UNKNOWN` are never promoted. Units at those
risk classes remain `NEEDS_HUMAN` (or `PERMANENTLY_DENIED` if
the classifier also denies them) and the conveyor stops on them.

### 3.4 Explicit scaffolding (every field non-empty)

The unit must declare ALL of:

- `expected_files` — non-empty list;
- `forbidden_files` — non-empty list;
- `required_tests` — non-empty list;
- `stop_conditions` — non-empty list;
- `definition_of_done` — non-empty list.

A unit missing any of these is left at NEEDS_HUMAN — the mandate
requires explicit definition of intent + tests + stop conditions
before automatic execution. Vague units stay operator-driven.

### 3.5 Path safety (already enforced upstream)

The canonical classifier scans every `expected_files` entry. If
ANY entry would touch a forbidden surface (per §2.1), the
aggregator returns `PERMANENTLY_DENIED` BEFORE the post-process
runs. The mandate never overrides PERMANENTLY_DENIED.

## 4. Elevated exception policy

Two surfaces are **not always-blocked** but **never** allowed
in the normal conveyor path. They require an **elevated
exception** — an operator-authored PR with explicit rationale:

### 4.1 Frozen contracts

- `research/research_latest.json`
- `research/strategy_matrix.csv`

Policy:

- Not allowed in normal conveyor path.
- May be considered only as an elevated exception.
- Requires explicit rationale that no smaller alternative
  exists.
- Must include frozen-contract regression tests.
- Must be reported as `elevated_exception_required`.
- Must NOT silently happen inside a generic unit.

The conveyor's classifier marks these surfaces as
PERMANENTLY_DENIED. Any change to them happens through an
operator-driven PR outside the autonomous runner.

### 4.2 Dashboard / UI mutation

- `dashboard/dashboard.py`
- UI mutation buttons
- approval buttons
- mutation routes

Policy:

- Not allowed in normal conveyor path.
- May be considered only as an elevated exception.
- Requires explicit rationale that no smaller read-only /
  reporting alternative exists.
- Mutation buttons / approval buttons remain blocked unless
  explicitly approved later in a separate governance-bootstrap
  PR.
- Must be reported as `elevated_exception_required`.

Like frozen contracts, the conveyor's classifier denies
`dashboard/dashboard.py`. Read-only dashboard *reads* (no
buttons, no mutation routes) may be permitted by separate
units when their `expected_files` stay inside the read-only
surface.

## 5. Catalog expansion policy

### 5.1 Current state (post A23)

The current A20a / A20b queue encodes:

- Roadmap v6 phases `v3.15.16` → `v3.15.20`;
- Addendum 1;
- Addendum 2 — repo-resident as of A23;
- Addendum 3 — repo-resident as of A23;
- 8 RoadmapTasks, 54 RoadmapRequirements, 37 ImplementationUnits.

A23 made Addendum 2 + 3 repo-resident by copying the
operator-provided canonical files verbatim into:

- `docs/roadmap/Roadmap v6 Addendum 2 - State Sequential Knowledge Retrieval.md`
- `docs/roadmap/Roadmap v6 Addendum 3 - Source Identity Data Quality and Throughput Intelligence.md`

Both absence flags now report **False** on every projection:

- `addendum_2_not_present = false`
- `addendum_3_not_present = false`

The 17 new Addendum 2 + 3 implementation units split into:

- Addendum 2 (8 units): 2 governance docs, 3 deterministic
  reporting modules (state-transition, null-process baseline,
  research throughput), 2 research scaffolds (knowledge graph,
  ontology + entity resolution), 1 hybrid retrieval reporter.
- Addendum 3 (9 units): 4 governance docs (source candidate
  registry, source identity / symbology, source manifest /
  quality gate, local data cache / throughput), 1 ledger
  reporter, 1 quality-gate reporter, 1 parquet/duckdb cache
  manifest, 2 external-intelligence registry scaffolds
  (OpenFIGI, Binance public bulk cache manifest).

LOW units stay AUTO_ALLOWED. MEDIUM units (knowledge graph +
ontology + OpenFIGI + Binance cache scaffolds) satisfy the A22
mandate (research-scaffold target layers, full
expected_files / forbidden_files / required_tests /
stop_conditions / definition_of_done scaffolding,
operator_gate = none) and get promoted to
**STRATEGICALLY_PREAPPROVED** by A20c's post-process.

### 5.2 Adding new units

The conveyor processes only units that exist in the A20a
catalog and the A20b decomposition. Adding new units requires a
**catalog expansion PR** that:

1. Adds new `RoadmapTask` entries (and their
   `RoadmapRequirement` entries) to
   `reporting/roadmap_task_catalog.py`.
2. Adds new `ImplementationUnit` entries to
   `reporting/roadmap_task_units.py`'s `_UNIT_SEED`.
3. Updates the matching test pins
   (`tests/unit/test_roadmap_task_catalog.py`,
   `tests/unit/test_roadmap_task_units.py`).
4. Ensures the new units satisfy the §3 mandate criteria if
   they should be auto-eligible, or marks them explicitly
   NEEDS_HUMAN if they should be operator-gated.
5. Stays inside the always-allowed surface (no live / paper /
   shadow / broker / risk / execution / dashboard mutation /
   frozen-contract mutation).

### 5.3 Addendum 2 / 3 specific path

`addendum_2` and `addendum_3` slots exist in
`_MANDATE_PHASES` but produce **no units** until their
canonical roadmap content is repo-resident. The catalog and
decomposition modules already pin the absence flags. When the
operator brings Addendum 2 or 3 content into the repo, a
catalog expansion PR:

- Removes the corresponding `addendum_*_not_present` absence
  flag from the catalog.
- Adds `RoadmapTask` + `RoadmapRequirement` entries for the
  addendum.
- Adds `ImplementationUnit` entries for each implementation
  surface.
- Updates the catalog and unit-decomposition test pins.

Once the addendum is repo-resident, the existing mandate rules
in §3 automatically apply — eligible units flow into the
selector and conveyor without further governance work.

### 5.4 The catalog is the only source of work

The autonomous PR runner reads ONLY from A20a / A20b. The
runner never invents work, never scans the canonical roadmap
documents at runtime, never derives work from external
artefacts. New work is added to the queue via the catalog
expansion PR pattern in §5.2.

## 6. CI / test / diff failures inside an iteration

Per operator policy, the conveyor should first attempt to fix
CI / test / diff failures **within the same unit and
expected_files**. It must NOT immediately stop and ask the
operator.

The conveyor stops only when:

- the fix requires editing files outside `expected_files`;
- the fix requires touching a forbidden surface;
- the fix requires an elevated exception (frozen contract /
  dashboard);
- the fix changes authority or risk class;
- repeated failure remains unresolved (per-iteration safety
  gates fire again);
- merge conflict cannot be safely resolved;
- the implementation would exceed `expected_files`.

This policy is enforced by the runner's existing per-iteration
safety gates. The pluggable
`ImplementationStrategy` interface lets a future slice add a
retry-within-unit loop. **This PR does not implement that
retry loop** — A22 is the policy + classification work; the
retry loop is a separate future slice.

### 6.1 How the conveyor implementation backend receives unit context

After A24, the operator's `--implementation-command` is a template
that the runner expands per iteration with the selected unit's
closed-vocab metadata (`{unit_id}`, `{phase}`, `{title}`,
`{risk_class}`, `{operator_gate}`, and the JSON-serialised lists
`{expected_files_json}`, `{forbidden_files_json}`,
`{required_tests_json}`, `{definition_of_done_json}`,
`{stop_conditions_json}`). See
[`step5_bounded_autonomous_loop.md`](step5_bounded_autonomous_loop.md)
§A24 for the full token table, fail-closed rules, and example
command. This is what makes the continuous conveyor practically
usable across the mandate-eligible queue — without templating, a
static command had no per-iteration unit context.

## 7. How the mandate is implemented

### 7.1 A20c post-process

[`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py)
adds:

- The new authority class `STRATEGICALLY_PREAPPROVED` in
  `AUTHORITY_CLASS` (severity 1, between AUTO_ALLOWED at 0 and
  NEEDS_HUMAN at 2).
- The new evidence kind `strategic_mandate` in
  `AUTHORITY_EVIDENCE_KIND`. Informational (not aggregating).
- The deterministic evaluator
  `_evaluate_strategic_mandate(unit)` that returns
  `(satisfied, reason)` against §3.
- The post-process `_apply_strategic_mandate(unit, decision)`
  that promotes NEEDS_HUMAN → STRATEGICALLY_PREAPPROVED when
  satisfied, and records mandate evidence on every decision.
- The new decision field `strategic_mandate_satisfied`.

### 7.2 A20e selector

[`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py)
adds `STRATEGICALLY_PREAPPROVED` to `_AUTHORITY_ORDER` (between
AUTO_ALLOWED and NEEDS_HUMAN). The eligibility logic in
`_build_candidate` treats STRATEGICALLY_PREAPPROVED units with
`operator_gate == "none"` as ELIGIBLE (not NEEDS_HUMAN_GATED).
The selector still prefers AUTO_ALLOWED via the deterministic
sort-key tie-breaking.

### 7.3 A21c / A21d / A21e runner

[`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
widens two safety gates:

- `auto_allowed_authority` — accepts
  `AUTO_ALLOWED` OR `STRATEGICALLY_PREAPPROVED`.
- `low_risk` — accepts `LOW` always; accepts `MEDIUM` only when
  the unit's authority is `STRATEGICALLY_PREAPPROVED`.

`HIGH` / `CRITICAL` / `UNKNOWN` risk is still refused even for
mandate-promoted units. `NEEDS_HUMAN` / `PERMANENTLY_DENIED`
authority is still refused.

The runner pins six new invariants:

- `accepts_strategically_preapproved_authority`
- `accepts_medium_risk_only_when_strategically_preapproved`
- `never_accepts_needs_human_authority_for_execution`
- `never_accepts_permanently_denied_authority_for_execution`
- `never_accepts_high_or_critical_risk`
- `elevated_exceptions_remain_operator_driven`

## 8. Test coverage

Pinned across the touched modules:

- [`tests/unit/test_roadmap_unit_authority.py`](../../tests/unit/test_roadmap_unit_authority.py)
  — 14 new tests covering vocab pins (AUTHORITY_CLASS extension,
  evidence kinds, severity ordering, decision field tuple),
  mandate-promotion happy path, no-promote-permanently-denied,
  no-promote-auto-allowed, no-promote-unsupported-phase,
  no-promote-unsupported-target-layer, no-promote-high-risk,
  no-promote-missing-scaffolding (parametrised over 5 fields),
  informational-evidence partition, severity-strictly-between.
- [`tests/unit/test_roadmap_next_unit.py`](../../tests/unit/test_roadmap_next_unit.py)
  — 4 new tests: STRATEGICALLY_PREAPPROVED is ELIGIBLE,
  AUTO_ALLOWED preferred over STRATEGICALLY_PREAPPROVED,
  STRATEGICALLY_PREAPPROVED picked over NEEDS_HUMAN-gated,
  PERMANENTLY_DENIED still blocks even alongside mandate
  candidates.
- [`tests/unit/test_autonomous_pr_runner.py`](../../tests/unit/test_autonomous_pr_runner.py)
  — 9 new tests covering the runner's two widened gates,
  HIGH/CRITICAL/UNKNOWN risk refusal even at
  STRATEGICALLY_PREAPPROVED, MEDIUM risk refusal without
  mandate, NEEDS_HUMAN refusal, PERMANENTLY_DENIED refusal,
  and the six new runner invariants.

## 9. What A22 does NOT do

- It does NOT add new units to the queue. The catalog and
  decomposition seeds are unchanged. Existing MEDIUM /
  NEEDS_HUMAN units in the seed become eligible **only** when
  they satisfy §3.
- It does NOT enable the conveyor to merge any new dangerous
  surface. Hard denials stay hard.
- It does NOT bring Addendum 2 / Addendum 3 content into the
  repo. Those addenda remain absence-flagged until a separate
  catalog expansion PR.
- It does NOT relax `--admin`, force-push, hook-bypass,
  deploy-invocation, or any A21c / A21d / A21e
  runner-invariant pin.
- It does NOT introduce a retry-within-unit loop for failing
  iterations. That is a future slice (see §6).

## 10. Cross-references

- [`docs/governance/step5_bounded_autonomous_loop.md`](step5_bounded_autonomous_loop.md)
  — Step 5 / A21 family governance.
- [`docs/governance/roadmap_task_catalog.md`](roadmap_task_catalog.md)
  — A20 / A21 catalog + queue documentation.
- [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — canonical authority mapping.
- [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — autonomy ladder; Level 6 is permanently disabled.
- [`docs/governance/no_touch_paths.md`](no_touch_paths.md) —
  forbidden-surface list (untouched by A22).
- [`docs/governance/execution_authority.md`](execution_authority.md)
  — canonical execution-authority policy (untouched by A22).
- [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md)
  — ADE remains development workflow automation only.

## 11. Next recommended operator action

After PR #260 (A22) merges:

1. If Addendum 2 / Addendum 3 content is ready to bring
   in-repo: open a catalog expansion PR per §5. The mandate
   criteria automatically apply to the new units.
2. Otherwise: run the existing conveyor against the existing
   queue. Mandate-promoted MEDIUM scaffolding units will now
   flow automatically:

   ```sh
   python -m reporting.autonomous_pr_runner \
       --run-continuous --auto-merge-runner-pr \
       --implementation-strategy external_command \
       --implementation-command "<operator-supplied real command>"
   ```

   The conveyor processes every AUTO_ALLOWED / LOW and
   STRATEGICALLY_PREAPPROVED unit, stopping only on no
   eligible work, safety / technical stop, or explicit
   operator soft-stop.
