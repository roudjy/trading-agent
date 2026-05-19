# Roadmap Task Catalog — A20a..A20e + A21a + A21c + A21d + A21e + A22

> **Status:** A20a implemented; A20b implemented; A20c implemented
> (extended by A22 with strategic-mandate post-process); A20d
> implemented; A20e implemented (deterministic next-buildable-unit
> selector, now accepts STRATEGICALLY_PREAPPROVED as eligible);
> A21a implemented (dynamic unit-status ledger); A21c implemented
> (bounded autonomous PR runner); A21d implemented (bounded
> auto-merge for runner-originated PRs); A21e implemented
> (continuous autonomous conveyor with no artificial cap); **A22
> implemented (Strategic Roadmap Execution Mandate + Catalog
> Expansion Policy — operator pre-approves automatic processing
> of mandate-eligible MEDIUM / NEEDS_HUMAN research-scaffold
> units via the new STRATEGICALLY_PREAPPROVED authority class,
> while keeping every hard runtime / trading / paper / shadow /
> broker / risk / live / frozen-contract / dashboard-mutation
> boundary intact).** No auto-merge for non-runner-originated PRs;
> no ``--admin``; no force-push; no hook bypass; no deploy
> invocation; post-merge gates remain read-only-observed.

## Current queue scope

The queue is **finite**. It encodes:

- Roadmap v6 phases v3.15.16 → v3.15.20;
- Addendum 1;
- 20 implementation units.

`addendum_2` and `addendum_3` slots exist in the strategic
mandate's phase list but are **not yet repo-resident**. Adding
units in those phases requires a separate operator-driven
catalog expansion PR. See
[`docs/governance/strategic_roadmap_execution_mandate.md`](strategic_roadmap_execution_mandate.md)
§5 for the catalog expansion policy.
>
> **A20a module:** [`reporting/roadmap_task_catalog.py`](../../reporting/roadmap_task_catalog.py)
> **A20a artefact:** `logs/roadmap_task_catalog/latest.json`
>
> **A20b module:** [`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py)
> **A20b artefact:** `logs/roadmap_task_units/latest.json`
>
> **A20c module:** [`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py)
> **A20c artefact:** `logs/roadmap_unit_authority/latest.json`
>
> **A20d module (extension):** [`reporting/development_agent_activity_timeline.py`](../../reporting/development_agent_activity_timeline.py)
> **A20d artefact:** existing `logs/development_agent_activity_timeline/latest.json` envelope; three new `source_kind` values inside `work_items[]`.
>
> **A20e module:** [`reporting/roadmap_next_unit.py`](../../reporting/roadmap_next_unit.py)
> **A20e artefact:** `logs/roadmap_next_unit/latest.json`
>
> **A21a module:** [`reporting/roadmap_unit_status.py`](../../reporting/roadmap_unit_status.py)
> **A21a artefact:** `logs/roadmap_unit_status/latest.json`
> **A21a governance:** [`docs/governance/step5_bounded_autonomous_loop.md`](step5_bounded_autonomous_loop.md)
>
> **A22 module:** [`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py) (strategic-mandate post-process)
> **A22 governance:** [`docs/governance/strategic_roadmap_execution_mandate.md`](strategic_roadmap_execution_mandate.md)
> A22 promotes mandate-eligible NEEDS_HUMAN units to ``STRATEGICALLY_PREAPPROVED`` so the conveyor processes them automatically. The mandate never overrides PERMANENTLY_DENIED, never accepts HIGH/CRITICAL/UNKNOWN risk, and never relaxes the always-blocked runtime / trading / paper / shadow / broker / risk / execution / frozen-contract / dashboard-mutation surfaces.
>
> **A21c + A21d + A21e module:** [`reporting/autonomous_pr_runner.py`](../../reporting/autonomous_pr_runner.py)
> **A21c..A21e primary artefact:** `logs/autonomous_pr_runner/latest.json`
> **A21d / A21e auxiliary artefact:** `logs/roadmap_unit_status/runner_merges.json`
> (evidence-backed merged records appended via
> [`reporting.roadmap_unit_status.append_runner_merge_record`](../../reporting/roadmap_unit_status.py))
> **A21e operator soft-stop sentinel:** `logs/autonomous_pr_runner/STOP_AFTER_CURRENT.signal`
> **A21c..A21e governance:** [`docs/governance/step5_bounded_autonomous_loop.md`](step5_bounded_autonomous_loop.md) §11 (A21c) + §12 (A21d) + §13 (A21e)
> A21c is the first real Step 5 execution slice — it creates a real branch + PR for ONE selected safe unit. A21d extends the same surface with an opt-in auto-merge phase (`--auto-merge-runner-pr`) for runner-originated PRs only, squash-merge only, no `--admin`, no force-push, no hook bypass, max 1 merge per run, with post-merge gate watch + evidence-backed ledger update. A21e wraps the A21d cycle in a continuous conveyor (`--run-continuous`) with no artificial unit-count cap and no wall-clock budget; the conveyor stops only on no-eligible-work, safety, technical, or explicit operator soft-stop conditions. No deploy invocation.
>
> **Authority:** development-governance read-only.
> The roadmap task catalog is **not** the canonical product roadmap.
> Roadmap v6 ([`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md))
> remains the canonical QRE product roadmap and the only source of
> truth for product phase order and intent. This catalog is a
> deterministic *seed* over that source plus the committed Addendum 1.
>
> The catalog grants **no** implementation, runtime, trading, paper,
> shadow, broker, risk, or live authority to any agent. ADE remains
> development workflow automation only per
> [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md).

---

## 1. Purpose

ADE's autonomous-development surface needs a deterministic,
repo-resident description of the upcoming QRE Feature Build Track
phases. The Roadmap Intake Bridge
([`reporting/development_roadmap_intake.py`](../../reporting/development_roadmap_intake.py))
already gives ADE a path to pick up explicit
`<!-- ade_roadmap_intake ... -->` markers, but the canonical roadmap
documents must remain human-readable; bulk decomposition does not
belong inline in those files.

A20a fills the gap by hand-encoding the v3.15.16 → v3.15.20 phase
tasks plus a cross-cutting Addendum 1 task and their normative
requirements into a deterministic Python literal inside
`reporting/roadmap_task_catalog.py`. The module emits a single
read-only projection at `logs/roadmap_task_catalog/latest.json`.

This is a **catalog**, not a queue:

- A20a hand-encodes phase tasks and Addendum 1 requirements.
- A20b (future) decomposes phases into PR-sized implementation
  units.
- A20c (future) attaches per-unit risk and authority classification
  via the existing [`reporting/execution_authority.py`](../../reporting/execution_authority.py)
  classifier.
- A20d (future) exposes read-only AAC / task-board visibility on
  top of A20a / A20b / A20c artefacts.
- A20e (future) selects a deterministic next-buildable unit. No
  hidden LLM judgment.

Each subsequent stage requires a separate operator-go PR. A20a does
not pre-authorize any of them.

---

## 2. Scope and non-scope

### 2.1 In scope

- Hand-encoded `RoadmapTask` records for Roadmap v6 phases
  v3.15.16, v3.15.17, v3.15.18, v3.15.19, v3.15.20, plus a
  cross-cutting `addendum_1` task.
- Hand-encoded `RoadmapRequirement` records covering the Addendum 1
  diagnostic families (tails, entropy, criticality, barrier,
  resonance, null-model, network, adversarial, control-stability,
  seismic, liquidity-turbulence, quorum, market-language), the
  external-intelligence intake section, the source-manifest fields,
  and the public-data quality gates.
- Closed vocabularies `PHASE`, `SOURCE_DOCUMENT`, `STATUS`,
  `ADDENDUM_LINK`, `TARGET_LAYER`. Widening any of them requires a
  code change pinned by an updated unit test.
- Deterministic, sorted-keys, bounded-scalar projection emitted
  under `logs/roadmap_task_catalog/latest.json` via an atomic write
  restricted to that directory.
- CLI (`--no-write`, `--status`, `--indent`).

### 2.2 Non-scope (hard constraints)

- **Roadmap v6 Addendum 2 and Roadmap v6 Addendum 3 are not
  present in the repo** at the time of this seed. They are
  represented **only** as the absence flags
  `discipline_invariants.addendum_2_not_present = true` and
  `discipline_invariants.addendum_3_not_present = true`. Their
  requirements must not be invented by this module and must not be
  added until the operator commits those source files.
- No phase-to-PR-unit decomposition. That is A20b scope.
- No per-unit `execution_authority.classify(...)` calls. That is
  A20c scope.
- No AAC / task-board / dashboard surface change. That is A20d
  scope.
- No next-buildable-unit selector. That is A20e scope.
- No mutation of any canonical roadmap document. The catalog does
  not touch [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md),
  [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md),
  [`docs/roadmap/qre_roadmap_v6_phase_prompts.md`](../roadmap/qre_roadmap_v6_phase_prompts.md),
  [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](../roadmap/qre_roadmap_v6_ade_operating_manual.md),
  or [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt).
- No mutation of frozen contracts
  (`research/research_latest.json`, `research/strategy_matrix.csv`).
- No mutation of `.claude/**`, `dashboard/dashboard.py`,
  `automation/live_gate.py`, `broker/**`, `agent/risk/**`,
  `agent/execution/**`, or any live / paper / shadow / trading
  path.
- No writes to `docs/development_work_queue/seed.jsonl`,
  `docs/development_work_queue/delegation_seed.jsonl`, or any
  `generated_seed.jsonl` file.
- No edits to the existing A17 admission-policy surface
  ([`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py)).
- A20a does not modify the AAC aggregator
  ([`reporting/development_agent_activity_timeline.py`](../../reporting/development_agent_activity_timeline.py))
  or its upstream catalog cardinality. That cardinality
  amendment landed under operator-approved A20d (catalog grew
  from 11 to 14 read-only entries).
- No flip of `step5_implementation_allowed` (stays `False`) or
  `STEP5_ENABLED_SUBSTAGE` (stays `"none"`).
- No relaxation of the autonomy-ladder ceiling. Level 6 stays
  permanently disabled per ADR-015 §Doctrine 1.
- No subprocess, no network, no `gh`, no `git`, no LLM, no fuzzy
  parsing.

---

## 3. Authority chain

This catalog is **not** an authority surface. It does not classify
implementation risk and does not grant any agent the right to
implement, branch, merge, deploy, trade, or move capital. Roadmap v6
remains canonical; per-action authority remains owned by
[`docs/governance/execution_authority.md`](execution_authority.md)
and [`reporting/execution_authority.py`](../../reporting/execution_authority.py).

| Concern | Owner |
|---|---|
| Canonical product roadmap | [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) |
| Diagnostic / external-intelligence extension | [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) |
| ADE governance roadmap | [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) |
| ADE development-lane doctrine | [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md) |
| Per-action authority classification | [`docs/governance/execution_authority.md`](execution_authority.md) + [`reporting/execution_authority.py`](../../reporting/execution_authority.py) |
| Step 5 sub-stage cap | [`docs/governance/step5_design.md`](step5_design.md) §12 + ADR-017 |
| Autonomy ladder (Level 6 permanently disabled) | [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md) + ADR-015 |

---

## 4. Schemas

### 4.1 `RoadmapTask`

Per-phase intent record. Field list is exact and ordered.

```
id                : str  (≤96 chars; stable opaque identifier)
title             : str  (≤200 chars)
phase             : str  ∈ PHASE
source_documents  : list[str]  (⊆ SOURCE_DOCUMENT; sorted)
purpose           : str  (≤1000 chars)
status            : str  ∈ STATUS
prerequisites     : list[str]  (other RoadmapTask.id values; sorted)
```

### 4.2 `RoadmapRequirement`

Per-requirement record. Field list is exact and ordered.

```
id              : str  (≤96 chars)
roadmap_task_id : str  (RoadmapTask.id this requirement belongs to)
source_document : str  ∈ SOURCE_DOCUMENT
source_anchor   : str  (≤200 chars; section/anchor in source doc)
phase           : str  ∈ PHASE
addendum_link   : str  ∈ ADDENDUM_LINK ("none" iff no addendum link)
statement       : str  (≤500 chars)
target_layer    : str  ∈ TARGET_LAYER
status          : str  ∈ STATUS
```

### 4.3 `TaskCatalogProjection`

Top-level artefact shape. Field list is exact and ordered.

```
generated_at_utc       : ISO8601 (sole non-deterministic field)
schema_version         : str
module_version         : str
roadmap_tasks          : list[RoadmapTask]
roadmap_requirements   : list[RoadmapRequirement]
discipline_invariants  : dict[str, bool]
```

The artefact also carries `report_kind`, `vocabularies`,
`step5_enabled_substage`, `step5_implementation_allowed`, and
`execution_authority_module_version` envelope fields for parity
with other ADE-core artefacts. These are emitted alongside the
field list above; the field-list tuple defines the closed set
that future projectors MUST preserve.

---

## 5. Closed vocabularies

| Vocabulary | Members |
|---|---|
| `PHASE` | `v3.15.16`, `v3.15.17`, `v3.15.18`, `v3.15.19`, `v3.15.20`, `addendum_1`, `addendum_2`, `addendum_3` |
| `SOURCE_DOCUMENT` | `docs/roadmap/Roadmap v6.md`, `docs/roadmap/Roadmap v6 Addendum.md`, `docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`, `docs/roadmap/qre_roadmap_v6_phase_prompts.md` |
| `STATUS` | `not_started`, `ready`, `in_flight`, `merged`, `blocked`, `human_needed`, `permanently_denied` |
| `ADDENDUM_LINK` | `addendum_1`, `addendum_2`, `addendum_3`, `none` |
| `TARGET_LAYER` | `external_intelligence`, `diagnostics`, `market_behavior`, `hypothesis_discovery`, `strategy_mapping`, `preset`, `campaign`, `funnel`, `evidence`, `policy`, `shadow`, `paper`, `live`, `reporting`, `governance`, `docs`, `test` |

`PHASE` deliberately lists `addendum_2` and `addendum_3` so future
projectors can carry their phase identity even before the source
documents land. `SOURCE_DOCUMENT` deliberately does **not** list the
Addendum 2 / Addendum 3 paths until those files are committed.

`ADDENDUM_LINK` uses an explicit `"none"` member so the field is
never silently missing on a non-addendum requirement.

---

## 6. Addendum 2 / Addendum 3 absence

Roadmap v6 Addendum 2 (State Sequential Knowledge Retrieval) and
Roadmap v6 Addendum 3 (Source Identity Data Quality and Throughput
Intelligence) are **not in the repo** at the time of this seed.

A20a represents both as absence flags only:

```
discipline_invariants.addendum_2_not_present = true
discipline_invariants.addendum_3_not_present = true
```

The catalog emits zero `RoadmapTask` records under
`phase = "addendum_2"` or `phase = "addendum_3"`, and zero
`RoadmapRequirement` records linked to those phases. Their
requirements must not be invented by this module. When the operator
commits the source files, a follow-up PR may:

1. add the path strings to `SOURCE_DOCUMENT`;
2. flip the corresponding absence flag to `false`;
3. add hand-encoded `RoadmapTask` + `RoadmapRequirement` records;
4. update the matching unit tests.

Until then the absence is explicit and asserted.

---

## 7. A20b — Implementation Unit Decomposer (implemented)

A20b consumes the A20a catalog and emits a deterministic
projection of **PR-sized implementation units** at
`logs/roadmap_task_units/latest.json`. Each unit records exactly
how a future PR may slice the work for one `RoadmapTask` — what it
expects to write, what it must never write, the tests it must run,
its definition of done, its stop conditions, and the units it
depends on.

A20b is **decomposition data**, not heuristics. The
unit→file mapping is hand-authored as a Python literal inside
[`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py)
and pinned by [`tests/unit/test_roadmap_task_units.py`](../../tests/unit/test_roadmap_task_units.py).
There is no LLM, no fuzzy parsing, and no runtime parsing of
canonical roadmap documents. The decomposer derives task identity
from the in-memory A20a catalog only.

### 7.1 PR-sized unit principle

Each `ImplementationUnit` represents one coherent, atomic, mergeable
slice of future work. Phases with multiple distinct concerns
(routing signals + routing explanation + governance doc) are
decomposed into multiple units rather than one giant unit. Each
unit's `prerequisites[]` records its dependency edges so a future
A20e selector can topologically order them.

### 7.2 `ImplementationUnit` schema

Per-unit field list is exact and ordered:

```
id                        : str  ≤128 chars; stable opaque identifier
roadmap_task_id           : str  RoadmapTask.id this unit belongs to
title                     : str  ≤200 chars
phase                     : str  ∈ roadmap_task_catalog.PHASE
unit_kind                 : str  ∈ UNIT_KIND
target_layer              : str  ∈ TARGET_LAYER (mirror of catalog)
source_requirement_ids    : list[str]  RoadmapRequirement.id values
expected_files            : list[str]  paths the unit may write to
forbidden_files           : list[str]  paths the unit must NOT touch
forbidden_surface_reasons : list[str]  ⊆ FORBIDDEN_SURFACE_REASON
required_tests            : list[str]  pytest selectors + governance lint
definition_of_done        : list[str]  bounded DoD bullets
stop_conditions           : list[str]  bounded STOP conditions
prerequisites             : list[str]  other ImplementationUnit.id values
risk_class                : str  ∈ {LOW, MEDIUM, HIGH, UNKNOWN}
authority_hint            : str  ∈ AUTHORITY_HINT (NOT final authority)
operator_gate             : str  ∈ OPERATOR_GATE
status                    : str  ∈ UNIT_STATUS (seed value: not_started)
```

### 7.3 `expected_files` / `forbidden_files` semantics

`expected_files[]` enumerates the **only** paths the future
implementation PR is permitted to touch. Anything outside this list
is forbidden by construction. The decomposer never emits a unit
whose `expected_files[]` overlaps a paper / shadow / live /
trading / broker / agent.risk / agent.execution surface, the
`.claude/` tree, `dashboard/dashboard.py`, or the frozen contracts.

`forbidden_files[]` enumerates additional paths the future PR must
explicitly **not** touch. Every unit's `forbidden_files[]` carries
the full baseline at minimum:

- `.claude/**`
- `dashboard/dashboard.py`
- `research/research_latest.json`, `research/strategy_matrix.csv`
- `automation/live_gate.py`, `broker/**`, `agent/risk/**`,
  `agent/execution/**`
- `live/**`, `paper/**`, `shadow/**`, `trading/**`
- `.github/branch_protection_main.yml`
- the canonical policy docs and the canonical roadmap docs
- the existing A17 admission-policy module and the AAC aggregator
- `tests/regression/**`
- frozen schemas under `artifacts/`

These paths appear in the unit records only as **forbidden-path
declarations**. The unit-decomposer module itself never imports
those packages and never touches those paths at runtime; the
strings are metadata.

### 7.4 `forbidden_surface_reasons` semantics

Each unit declares the closed-vocabulary reasons that justify its
baseline + extra `forbidden_files` entries. Every unit includes
`frozen_contract`, `live_path`, `claude_governance_hook`,
`dashboard_wiring`, and `branch_protection_config` at minimum.

### 7.5 `required_tests` / `definition_of_done` / `stop_conditions`

- `required_tests[]` lists pytest selectors (or `scripts/`
  invocations) the future PR must run green. Every unit inherits a
  baseline: smoke, governance_lint, and the actual frozen-contract
  / public-output / authority regression tests present in this
  repo.
- `definition_of_done[]` lists the observable conditions that must
  be true at PR-open time. The baseline includes: clean module
  import, atomic-write allowlist enforcement, deterministic output,
  frozen contracts unchanged, no live / paper / shadow / broker /
  risk / execution path changes, no `dashboard/dashboard.py` change,
  no `.claude/**` change, no canonical-roadmap or canonical-policy
  edit, PR opened via the standard `gh pr create` lifecycle (no
  `--admin`, no force push, no hook bypass).
- `stop_conditions[]` lists immediate-abort triggers. The baseline
  includes: forbidden import / token in source, forbidden path in
  diff, regression-test failure, hook failure, any attempt to
  grant runtime / trading authority.

### 7.6 `prerequisites` semantics

`prerequisites[]` lists other `ImplementationUnit.id` values that
must be `status = merged` before this unit becomes eligible to
implement. A20e (future) will use this for deterministic topological
ordering. A20b verifies that every prerequisite references a known
unit.

### 7.7 `authority_hint` is **not** final authority

`authority_hint ∈ {AUTO_ALLOWED_CANDIDATE, NEEDS_HUMAN_CANDIDATE,
PERMANENTLY_DENIED_SURFACE}`. The hint is a deterministic,
conservative classification produced by hand-authored seed data; it
is **not** a substitute for the real classifier output. A20c will
replace each hint with the actual `reporting.execution_authority`
verdict aggregated across per-file decisions. Until A20c lands, the
hint is informational only. Unknown inputs fail closed to
`NEEDS_HUMAN_CANDIDATE`.

### 7.8 What A20b explicitly does NOT do

- **No final authority classification.** A20b does not import or
  call `reporting.execution_authority`. A20c will integrate the
  real classifier and replace each unit's hint with the actual
  verdict.
- **No AAC / dashboard visibility.** A20b emits only
  `logs/roadmap_task_units/latest.json`. The AAC aggregator and
  `dashboard/dashboard.py` are untouched. A20d will (in a separate
  operator-go PR) extend the AAC aggregator's pinned upstream
  catalog to consume A20b's artefact.
- **No next-buildable-unit selector.** A20e will (in a separate
  operator-go PR) compute eligibility and emit a deterministic
  `selected_unit_id` over A20c output.
- **No unit grants runtime / trading / paper / shadow / live
  authority.** Each unit's `forbidden_files[]` blocks those
  surfaces and the projection's `decomposition_invariants` pin
  `grants_*_authority = false` across every authority lane.
- **No new units under `phase == "addendum_2"` or
  `phase == "addendum_3"`.** Catalog absence propagates: the
  decomposer reads the A20a catalog at runtime and skips any
  unit whose phase is not present in the catalog's task list.

## 8. A20c — Roadmap Unit Authority Classifier Integration (implemented)

A20c is a **pure consumer** of two read-only upstreams: the A20b
implementation-unit projection
([`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py))
and the canonical Execution Authority classifier
([`reporting/execution_authority.py`](../../reporting/execution_authority.py)).
The A20c module is
[`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py);
its artefact is `logs/roadmap_unit_authority/latest.json`.

A20c MUST NOT create a second source of truth for path-level
authority. Every per-file evidence record carries the verbatim
`decision` / `reason` returned by
`reporting.execution_authority.classify(...)`. Non-path evidence
kinds (`target_layer`, `risk_class`, `operator_gate`,
`authority_hint`, `unit_kind`, `stop_conditions`) have their own
deterministic, closed-vocab rules pinned by unit tests.

### 8.1 Purpose of `UnitAuthorityDecision`

For every A20b `ImplementationUnit`, A20c emits one
`UnitAuthorityDecision` recording the **final authority class** the
unit must satisfy before any future implementation PR may proceed.
The class is one of the canonical
`reporting.execution_authority.DECISIONS` values:

- `AUTO_ALLOWED` — the unit may proceed under normal squash-merge
  review (no extra operator gate).
- `NEEDS_HUMAN` — the unit may proceed only with explicit operator
  approval (operator-go required).
- `PERMANENTLY_DENIED` — the unit is impossible under current
  policy and may not be implemented at all without a future,
  explicitly authorising governance-bootstrap PR.

### 8.2 A20b `authority_hint` vs A20c `final_authority_class`

A20b emits a non-authoritative `authority_hint` per unit, drawn
from `{AUTO_ALLOWED_CANDIDATE, NEEDS_HUMAN_CANDIDATE,
PERMANENTLY_DENIED_SURFACE}`. The hint is a deterministic seed-data
value, not a classifier verdict.

A20c emits the authoritative `final_authority_class` per unit,
drawn from `{AUTO_ALLOWED, NEEDS_HUMAN, PERMANENTLY_DENIED}`. The
hint enters as one piece of evidence (kind `authority_hint`) and
contributes to aggregation alongside every other evidence kind —
but it never overrides the canonical classifier verdict on a
per-file path.

### 8.3 Evidence schema

Per-evidence record (`UnitAuthorityEvidence`):

```
kind     : str ∈ AUTHORITY_EVIDENCE_KIND
value    : str (≤300 chars; bounded scalar)
decision : str ∈ AUTHORITY_CLASS
reason   : str ∈ AUTHORITY_REASON
source   : str ("reporting.execution_authority" for path-based
           evidence; "reporting.roadmap_unit_authority" for A20c
           non-path rules)
```

Per-unit decision (`UnitAuthorityDecision`):

```
implementation_unit_id : str  A20b ImplementationUnit.id
roadmap_task_id        : str  A20b ImplementationUnit.roadmap_task_id
phase                  : str  A20b ImplementationUnit.phase
final_authority_class  : str  ∈ AUTHORITY_CLASS
max_severity           : int  0=AUTO_ALLOWED, 1=NEEDS_HUMAN, 2=PERMANENTLY_DENIED
evidence               : list[UnitAuthorityEvidence]
requires_operator_go   : bool true iff final_authority_class == NEEDS_HUMAN
permanently_denied     : bool true iff final_authority_class == PERMANENTLY_DENIED
deny_reasons           : list[str]  populated iff permanently_denied
classifier_used        : bool true if at least one evidence record sources
                              the canonical classifier
fail_closed            : bool true if any evidence triggered
                              fail_closed_unknown_* fallback
```

Top-level projection (`UnitAuthorityProjection`):

```
generated_at_utc            : ISO8601
schema_version              : str
module_version              : str
source_units_schema_version : str  matches A20b.SCHEMA_VERSION
authority_decisions         : list[UnitAuthorityDecision]
authority_invariants        : dict[str, bool]
```

### 8.4 Aggregation: max-severity over **aggregating** evidence kinds

A20c aggregates per-unit decisions over the canonical decision
ordering `AUTO_ALLOWED < NEEDS_HUMAN < PERMANENTLY_DENIED`. Only
the following evidence kinds contribute to the aggregate:

- `expected_file_classifier` — verbatim verdict from the canonical
  classifier for each `expected_files[]` entry;
- `target_layer` — `live` → `PERMANENTLY_DENIED`; `paper` / `shadow`
  → `NEEDS_HUMAN`; all other layers contribute the baseline;
- `risk_class` — `UNKNOWN` → `NEEDS_HUMAN` with reason
  `unknown_risk_or_target_fail_safe`;
- `operator_gate` — `operator_go_required` /
  `governance_bootstrap_pr_required` → `NEEDS_HUMAN`;
- `authority_hint` — the A20b hint contributes the corresponding
  class as a floor;
- `unit_kind` — `research_module` / `diagnostic_primitive` /
  `external_intelligence_source` → `NEEDS_HUMAN` (these surfaces
  require human review even when the path classifier is permissive).

The following evidence kinds are recorded for transparency but do
**not** elevate the aggregate:

- `forbidden_file_classifier` — canonical-classifier verdict for
  each `forbidden_files[]` entry. Every A20b unit's baseline
  forbidden list contains live / frozen / governance paths that
  the classifier rightly denies; including them in aggregation
  would force every unit to `PERMANENTLY_DENIED` and is therefore
  explicitly excluded.
- `stop_conditions` — descriptive STOP triggers from A20b. Recorded
  as informational evidence only.

This partition is pinned by
`test_aggregating_and_informational_partition_the_vocab`.

### 8.5 Fail-closed contract

A20c fails closed in every ambiguous case:

| Condition | Result |
|---|---|
| `risk_class == "UNKNOWN"` | `NEEDS_HUMAN` |
| Invalid `risk_class` string (not in `RISK_CLASSES`) | `NEEDS_HUMAN`; `fail_closed = true` |
| Invalid `target_layer` string | `NEEDS_HUMAN`; `fail_closed = true` |
| Invalid `operator_gate` string | `NEEDS_HUMAN`; `fail_closed = true` |
| Invalid `authority_hint` string | `NEEDS_HUMAN`; `fail_closed = true` |
| Invalid `unit_kind` string | `NEEDS_HUMAN`; `fail_closed = true` |
| No aggregating evidence at all (defence in depth) | `NEEDS_HUMAN`; deny_reasons `["fail_closed_unknown_evidence"]` |

### 8.6 AUTO_ALLOWED only when no protected/runtime surface present

A unit's `final_authority_class` is `AUTO_ALLOWED` if and only if
**every** aggregating-evidence record classifies as `AUTO_ALLOWED`.
Adding any `expected_files[]` entry whose canonical-classifier
verdict is `NEEDS_HUMAN` or `PERMANENTLY_DENIED` — for example a
`canonical_policy_doc`, `canonical_roadmap`, `claude_governance_hook`,
`dashboard_wiring`, `live_path`, or `frozen_contract` path —
immediately demotes the unit. Pinned by per-category tests in
`tests/unit/test_roadmap_unit_authority.py`.

### 8.7 Runtime / trading authority pinned **off**

A20c does not grant any QRE runtime, trading, paper, shadow,
broker, risk, or live authority. The projection's
`authority_invariants` block pins:

- `calls_execution_authority_classifier = true`
- `final_authority_classified = true`
- `no_runtime_trading_authority = true`
- `no_step5_runtime = true`
- `no_level6 = true`
- `no_production_merge_authority = true`
- `writes_only_roadmap_unit_authority_log = true`
- `step5_implementation_allowed = false`
- `aac_visibility_present = false`
- `next_buildable_selector_present = false`

A20d (read-only operator visibility) and A20e (next-buildable-unit
selector) remain unimplemented. Pinned by
`test_invariants_pin_aac_and_next_buildable_remain_false`.

### 8.8 What A20c does NOT do

- **No modification of the canonical classifier** or its doc.
  `reporting/execution_authority.py` and
  `docs/governance/execution_authority.md` are untouched.
- **No mutation of A20a or A20b artefacts.** Pinned by sha256
  before/after tests.
- **No AAC / dashboard visibility.** A20d scope; AAC aggregator
  cardinality pin is unchanged.
- **No next-buildable-unit selector.** A20e scope.
- **No edit to canonical roadmap docs or `autonomous_development.txt`.**
- **No Step 5 / Level 6 / N5b weakening.** Step 5 implementation
  remains BLOCKED; Level 6 remains permanently disabled; N5b
  Phase 4 production merge remains permanently denied for ADE.

## 9. A20d — Read-only Operator Visibility (implemented)

A20d extends the existing read-only Agent Activity Center
aggregator
([`reporting/development_agent_activity_timeline.py`](../../reporting/development_agent_activity_timeline.py))
to surface the A20a / A20b / A20c artefacts as **read-only**
work-item rows. The aggregator's pinned upstream-catalog
cardinality grew from 11 to 14 entries (the three new entries are
all projectable and live under the new `roadmap` group, with
TTL 1800 seconds matching the other loops/gates groups).

### 9.1 Purpose of read-only operator visibility

Before A20d, the operator had to read `logs/roadmap_*` JSON files
directly to see the catalog, decomposition, and authority verdict
for each Roadmap v6 implementation unit. A20d brings those rows
into the same envelope as the rest of the development pipeline so
the operator can scan them in one place. No new mutation route is
introduced; no approval button is rendered; no `dashboard.py` is
touched.

### 9.2 Where the projections are surfaced

A20d adds three new `source_kind` values to the AAC aggregator's
closed `SOURCE_KINDS` enum (post-A20d cardinality: 16):

| `source_kind` | Upstream artefact | Owner role | Notes |
|---|---|---|---|
| `roadmap_task_catalog` | `logs/roadmap_task_catalog/latest.json` | `product_owner` | One row per `RoadmapTask`; always `current_stage = "discovered"`, `human_needed = False`, `risk = "low"`. |
| `roadmap_implementation_unit` | `logs/roadmap_task_units/latest.json` | `planner` | One row per `ImplementationUnit`. `current_stage` derives from A20b's `authority_hint` and `operator_gate` (informational only). |
| `roadmap_unit_authority_decision` | `logs/roadmap_unit_authority/latest.json` | `architecture_guardian` | One row per `UnitAuthorityDecision`. `current_stage` derives from A20c's `permanently_denied` / `requires_operator_go` flags. |

The aggregator's `UPSTREAM_CATALOG` grows from 11 to 14 entries;
all three new entries are projectable. The `PROJECTABLE_UPSTREAM_LEN`
constant goes from 4 to 7; `HEALTH_ONLY_UPSTREAM_LEN` stays 7. A new
`TTL_BY_GROUP["roadmap"] = 1800` entry is added.

### 9.3 Read-only semantics

Every row emitted by an A20d projector carries two explicit
markers:

- `read_only = True`
- `mutation_allowed = False`

In addition, the broader AAC no-mutation doctrine continues to hold
(no POST / PUT / PATCH / DELETE routes, no approval-inbox mutation,
no `required_phrase` synthesis — the A20b / A20c rows that produce
a `human_action` set `required_phrase = None` and `copy_only = True`
as a defence-in-depth measure).

### 9.4 What A20d does NOT do

- **No mutation routes.** The aggregator is read-only by
  construction per
  [`docs/governance/agent_activity_center_no_mutation_doctrine.md`](agent_activity_center_no_mutation_doctrine.md).
- **No approval buttons.** Human-action rows from the A20b /
  A20c projections set `required_phrase = None`. The aggregator
  never synthesises an operator-go phrase.
- **No mutation of `docs/development_work_queue/*.jsonl`.** Those
  seed files remain operator-owned.
- **No mutation of `approval_inbox`.** A20d only reports.
- **No new ADE-executable work items.** A20d surfaces existing
  read-only rows; it does not create new authority surfaces.
- **No next-buildable-unit selection.** That is A20e scope.
- **No Step 5 / Level 6 / N5b weakening.** Step 5 implementation
  remains BLOCKED; Level 6 remains permanently disabled; N5b
  Phase 4 production merge remains permanently denied for ADE.
- **No `dashboard/dashboard.py` change.** Visibility is via the
  existing AAC artefact (`logs/development_agent_activity_timeline/latest.json`);
  the dashboard wiring is separately operator-owned.

### 9.5 Invariant flips landing under A20d

A20d flips two flags in the `_DECOMPOSITION_INVARIANTS`
(A20b) and `_BASE_AUTHORITY_INVARIANTS` (A20c) blocks from
`False` to `True`:

- `aac_visibility_present = True`

The following stay `False`:

- `next_buildable_selector_present = False` (A20e scope)

And the following stay `True` (no weakening):

- `no_runtime_trading_authority = True`
- `no_step5_runtime = True`
- `no_level6 = True`
- `no_production_merge_authority = True`

## 10. A20e — Deterministic Next-Buildable-Unit Selector (implemented)

A20e is a pure stdlib-only read-only consumer of the A20b
implementation-unit projection and the A20c unit-authority
projection. It emits a deterministic projection at
`logs/roadmap_next_unit/latest.json` that names at most one
`NextBuildableUnitSelection` plus the full filterable candidates
list.

### 10.1 Purpose of deterministic next-buildable-unit selection

Before A20e the operator had to scan the A20b and A20c artefacts
manually to identify which implementation unit should be the next
PR. A20e applies a closed deterministic filter + sort and surfaces
either the single recommended unit or the closed-vocab reason no
unit is eligible. The recommendation is **informational only**;
A20e never opens a branch / PR / merge / deploy.

### 10.2 Read-only by construction

- A20e never executes any unit's implementation.
- A20e never creates a branch.
- A20e never opens a PR.
- A20e never merges or deploys anything.
- A20e never mutates any approval inbox, seed JSONL, queue, or
  upstream artefact (pinned by sha256-before-vs-after tests on
  the A20b / A20c artefacts).
- A20e never calls the canonical Execution Authority classifier
  directly; A20c remains the only classifier call site.
- A20e never grants runtime / trading / paper / shadow / live
  authority.
- A20e never activates Step 5; never enables Level 6; never
  creates production-merge authority.

### 10.3 Deterministic selection rules

For each A20b implementation unit:

1. **A20b status check.** The unit's status must be in the closed
   buildable set `{"not_started", "ready"}`. Any other status
   (e.g. `in_flight`, `merged`, `blocked`, `human_needed`,
   `permanently_denied`) blocks the candidate with
   `non_buildable_status`. An unknown status string blocks with
   `unknown_unit_status`.
2. **A20c authority lookup.** Find the matching A20c
   `UnitAuthorityDecision` by `implementation_unit_id`:
   - zero matches → block with `missing_authority_decision`;
   - more than one match → block with
     `duplicate_authority_decision`;
   - `final_authority_class == "PERMANENTLY_DENIED"` → block with
     `permanently_denied_authority`;
   - `final_authority_class` outside `{AUTO_ALLOWED, NEEDS_HUMAN}`
     → block with `unknown_authority`.
3. **Prerequisite check.** Every entry in the unit's
   `prerequisites[]` must resolve to a known A20b unit with
   `status = "merged"`. Otherwise:
   - unknown target → block with `unknown_prerequisite_target`;
   - target not merged → block with `unsatisfied_prerequisite`.
4. **Eligibility classification.** If no block reasons accumulated:
   - `final_authority_class == "NEEDS_HUMAN"` OR
     `operator_gate != "none"` → `NEEDS_HUMAN_GATED`;
   - else → `ELIGIBLE`.

Sort key (tuple-as-list, fully deterministic, no timestamps):

1. Roadmap phase order: `v3.15.16`, `v3.15.17`, `v3.15.18`,
   `v3.15.19`, `v3.15.20`, `addendum_1`, `addendum_2`,
   `addendum_3`. Unknown phases sort last.
2. Authority order: `AUTO_ALLOWED` before `NEEDS_HUMAN`.
3. Risk order: `LOW` before `MEDIUM` before `HIGH` before
   `UNKNOWN`.
4. Operator-gate order: `none` before `operator_go_required`
   before `governance_bootstrap_pr_required`.
5. Implementation-unit id lex order.

Selection prefers `ELIGIBLE` over `NEEDS_HUMAN_GATED`. Ties within
a tier resolve by the sort key above.

### 10.4 Authority handling

- `AUTO_ALLOWED` units may be selected as the next buildable
  candidate. A20e records the recommendation; the operator
  decides whether to open a PR via the normal lifecycle. A20e
  itself never opens a branch.
- `NEEDS_HUMAN` units may be selected **only** as the operator-gated
  candidate. The selected row carries `requires_operator_go=True`
  and the projection's `selection_status` is
  `ALL_NEEDS_HUMAN_GATED`.
- `PERMANENTLY_DENIED` units are never selected. Pinned by
  `selector_invariants.permanently_denied_units_never_selected`.

### 10.5 Fail-closed behavior

A20e fails closed in every ambiguous case:

| Condition | Result |
|---|---|
| Either upstream artefact absent or malformed | `selection_status = "UPSTREAM_UNAVAILABLE"`, `fail_closed = true`, `selected_unit_id = ""` |
| Zero units in A20b | `NO_ELIGIBLE_UNITS`, `fail_closed = true` |
| Every candidate `PERMANENTLY_DENIED` | `ALL_PERMANENTLY_DENIED`, `fail_closed = true` |
| Every candidate blocked by unresolved prerequisites | `ALL_BLOCKED_BY_PREREQUISITES`, `fail_closed = true` |
| Unknown / duplicate authority on every candidate | `FAIL_CLOSED_INVARIANT`, `fail_closed = true` |
| Mixed blocking reasons with zero eligible | `NO_ELIGIBLE_UNITS`, `fail_closed = true` |
| Selection succeeds with at least one `ELIGIBLE` | `OK_SELECTED`, `fail_closed = false` |
| Selection succeeds but every eligible candidate is `NEEDS_HUMAN_GATED` | `ALL_NEEDS_HUMAN_GATED`, `fail_closed = false`, `requires_operator_go = true` |

### 10.6 A20e does NOT expose itself in AAC visibility yet

The smallest-safe A20e implementation keeps the AAC aggregator
unchanged. The operator can read the selector projection directly
via:

```sh
python -m reporting.roadmap_next_unit --status
```

or by reading `logs/roadmap_next_unit/latest.json`. A future
operator-go PR may extend the AAC aggregator's pinned upstream
catalog with a 15th `roadmap_next_unit` entry; that change would
require updating the B2.0b structural-pin test in the same PR. It
is not in A20e scope.

### 10.7 Invariant flips landing under A20e

A20e flips one flag in the A20b `_DECOMPOSITION_INVARIANTS` and
A20c `_BASE_AUTHORITY_INVARIANTS` blocks from `False` to `True`:

- `next_buildable_selector_present = True`

The following remain `True` (no weakening):

- `no_runtime_trading_authority = True`
- `no_step5_runtime = True`
- `no_level6 = True`
- `no_production_merge_authority = True`
- `aac_visibility_present = True`

## 11. A20 overall status after A20e

A20a → A20e form the read-only "roadmap-to-task pipeline":

1. **A20a** seeds the deterministic Roadmap v6 + Addendum 1 task
   catalog as in-source Python data.
2. **A20b** decomposes each task into PR-sized
   `ImplementationUnit` records.
3. **A20c** annotates each unit with the canonical Execution
   Authority verdict.
4. **A20d** surfaces all three projections as read-only AAC
   work-item rows.
5. **A20e** deterministically selects the next-buildable unit.

The next step after A20e is **operator review** of the selector
output, followed by the **first queue-driven Roadmap v6
implementation unit** opened as its own PR under normal ADE PR
lifecycle governance. A20e does not open that PR — the operator
does, using the selector's recommendation as input.

### 11.1 Queue progression log (legacy — A20b seed-edit path)

Until A21a shipped, the A20 projections did not auto-discover
merged PRs. Each queue-driven Roadmap v6 unit that landed on
`main` required a small follow-up `chore/a20-*` PR to advance its
status in A20b's `_UNIT_SEED` so A20e could recommend the next
eligible downstream unit. Two transitions were recorded by that
path before §11.2 superseded it:

| Date (UTC) | Unit id | A20b status | Implementing PR | Merge SHA |
|---|---|---|---|---|
| 2026-05-18 | `u_v3_15_16_diagnostic_routing_signals_schema_001` | `not_started` → `merged` | [#250](https://github.com/roudjy/trading-agent/pull/250) | `fcb1abbea4bd2ca190fe6e807b3dacd184faa702` |
| 2026-05-18 | `u_v3_15_16_routing_explanation_reporter_001` | `not_started` → `merged` | [#252](https://github.com/roudjy/trading-agent/pull/252) | `6f588a89b43a2cfec40f92252bde530220877b37` |

This table is informational and frozen. Future merged units are
recorded in §11.2 via the A21a dynamic ledger instead.

### 11.2 Queue progression log (A21a dynamic ledger path)

[`reporting/roadmap_unit_status.py`](../../reporting/roadmap_unit_status.py)
(Step 5 / A21a foundation) is now the authoritative source for
per-unit execution status. The static A20b seed remains the
authoritative source for **unit definitions** (id, expected
files, forbidden files, prerequisites, risk hint, authority
hint), but **execution status** is overlaid by the A21a ledger.

This means a merged unit no longer requires a
`chore/a20-mark-*-merged` follow-up PR. The bootstrap A21a seed
already pins the three v3.15.16 routing-layer units as merged
with their PR numbers and merge SHAs, and the A20e selector
treats them as `effective_status = "merged"` without any A20b
edit:

| Date (UTC) | Unit id | Effective status | Implementing PR | Merge SHA | Source |
|---|---|---|---|---|---|
| 2026-05-18 | `u_v3_15_16_diagnostic_routing_signals_schema_001` | `merged` | [#250](https://github.com/roudjy/trading-agent/pull/250) | `fcb1abbea4bd2ca190fe6e807b3dacd184faa702` | A21a ledger |
| 2026-05-18 | `u_v3_15_16_routing_explanation_reporter_001` | `merged` | [#252](https://github.com/roudjy/trading-agent/pull/252) | `6f588a89b43a2cfec40f92252bde530220877b37` | A21a ledger |
| 2026-05-18 | `u_v3_15_16_routing_governance_doc_001` | `merged` | [#254](https://github.com/roudjy/trading-agent/pull/254) | `df7dc6562ec3cd3a9f87e83e758881bd6fdb16f8` | A21a ledger |

Future merged units append a new record to the A21a seed in the
same shape. See
[`docs/governance/step5_bounded_autonomous_loop.md`](step5_bounded_autonomous_loop.md)
for the dynamic-ledger schema, the closed vocabularies, and the
validation / fail-closed contract.

<!-- A20e legacy future-stages section retained below for reference. -->
## 12. Future stages — A20 complete

The A20 series is complete. No further A20 stages are planned.
Future work continues under the QRE Feature Build Track on the
Roadmap v6 phase order (v3.15.16 → v3.15.17 → v3.15.18 →
v3.15.19 → v3.15.20 → v3.16.x → v4.x → v5.x → v6.x).

## 13. CLI

```sh
# Pure inspection — write the artefact and dump JSON to stdout:
python -m reporting.roadmap_task_catalog

# Pure inspection — do not write any artefact:
python -m reporting.roadmap_task_catalog --no-write

# Compact, human-readable status (no artefact write):
python -m reporting.roadmap_task_catalog --status

# Indented JSON to stdout:
python -m reporting.roadmap_task_catalog --indent 2
```

Stdlib + `reporting.execution_authority` (constants only) only. No
subprocess, no network, no `gh`, no `git`. The atomic write helper
refuses every path outside `logs/roadmap_task_catalog/`.

---

## 14. Determinism contract

- Tasks are sorted by `(phase, id)` ascending.
- Requirements are sorted by `(phase, id)` ascending.
- All free-text fields are bounded.
- Output is `json.dumps(..., sort_keys=True, indent=2) + "\n"`.
- `generated_at_utc` is the only non-deterministic field. Tests
  inject it for byte-identical fixtures.
- Atomic write via `os.replace(...)` from a same-directory
  `tempfile.mkstemp(...)`. No tmp files left behind on failure.

---

## 15. Test coverage

### 15.1 A20a

Pinned in [`tests/unit/test_roadmap_task_catalog.py`](../../tests/unit/test_roadmap_task_catalog.py):

- Closed vocabularies are exact and complete.
- Schema field tuples are exact and ordered.
- Every encoded task / requirement satisfies the closed vocab.
- Phase-task coverage: every v3.15.16..v3.15.20 phase has a task;
  the `addendum_1` cross-cutting task exists; `addendum_2` /
  `addendum_3` have **zero** encoded tasks.
- Addendum 1 diagnostic-family coverage spans tails, entropy,
  criticality, barrier, resonance, null-model, network,
  adversarial, control-stability, seismic, liquidity-turbulence,
  quorum, market-language, external-intelligence intake,
  source-manifest fields, and public-data quality gates.
- Step 5 invariants pinned: `step5_implementation_allowed is False`
  and `STEP5_ENABLED_SUBSTAGE == "none"`.
- Discipline invariants pinned for: no runtime / trading / paper /
  shadow / broker / risk / live authority; no frozen contract
  mutation; no seed-jsonl writes; diagnostics do not trade;
  external data is not alpha; Addendum 2 / 3 absence flags.
- Determinism: byte-identical output for identical input with
  injected `generated_at_utc`.
- Atomic-write allowlist refuses any path outside
  `logs/roadmap_task_catalog/`.
- CLI `--no-write` does not write; `--status` does not write and
  emits the expected invariant strings; default writes to the
  allowlisted path.
- Module-source scan for forbidden imports / tokens (subprocess,
  socket, urllib, http, requests, dashboard, automation, broker,
  agent.risk, agent.execution, live, paper, shadow, trading,
  research.run_research, research_latest.json, strategy_matrix.csv,
  `gh`, `git`).

### 15.2 A20b

Pinned in [`tests/unit/test_roadmap_task_units.py`](../../tests/unit/test_roadmap_task_units.py):

- Closed vocabularies (`UNIT_KIND`, `RISK_CLASS`, `AUTHORITY_HINT`,
  `OPERATOR_GATE`, `UNIT_STATUS`, `TARGET_LAYER`,
  `FORBIDDEN_SURFACE_REASON`) are exact.
- Schema field tuples (`IMPLEMENTATION_UNIT_FIELDS`,
  `UNIT_DECOMPOSITION_PROJECTION_FIELDS`) are exact and ordered.
- Every emitted unit satisfies the closed vocabularies on every
  closed-vocab field.
- Every emitted unit has non-empty `expected_files`,
  `forbidden_files`, `forbidden_surface_reasons`, `required_tests`,
  `definition_of_done`, `stop_conditions`.
- Every emitted unit has a `prerequisites` field (list, may be
  empty); every referenced prerequisite resolves to a known unit.
- Every A20a `RoadmapTask` is decomposed into at least one unit;
  v3.15.16, v3.15.17, v3.15.18, v3.15.19, v3.15.20 each have more
  than one unit; Addendum 1 has ≥3 units.
- No unit is emitted under `phase == "addendum_2"` or
  `phase == "addendum_3"`.
- No unit declares paper / shadow / live / trading / broker /
  agent.risk / agent.execution / `.claude/` / `dashboard.py` /
  frozen-contract surfaces as `expected_files` targets.
- Every unit's `forbidden_files` includes the full baseline list.
- Every unit's `forbidden_surface_reasons` includes the baseline
  reasons (`frozen_contract`, `live_path`,
  `claude_governance_hook`, `dashboard_wiring`,
  `branch_protection_config`).
- `authority_hint` fail-closed: unknown inputs resolve to
  `NEEDS_HUMAN_CANDIDATE`.
- Decomposition invariants pin: no runtime / trading / paper /
  shadow / broker / risk / live authority granted;
  `step5_implementation_allowed = false`;
  `STEP5_ENABLED_SUBSTAGE = "none"`; Addendum 2 / 3 absence flags;
  no execution_authority classifier called; no AAC visibility;
  no next-buildable-unit selector.
- Deterministic byte-identical output for identical input with
  injected `generated_at_utc`.
- Atomic-write allowlist refuses any path outside
  `logs/roadmap_task_units/` — frozen-contract paths in particular.
- CLI: `--no-write` writes nothing; `--status` writes nothing and
  emits invariant strings; default writes to the allowlisted path
  with correct schema; `--indent 0` produces compact output.
- Module source carries no forbidden imports (subprocess, socket,
  urllib, http, requests, dashboard, automation, broker,
  agent.risk, agent.execution, research.run_research,
  reporting.intelligent_routing, reporting.execution_authority,
  reporting.development_queue_admission_policy,
  reporting.development_agent_activity_timeline) and no forbidden
  runtime tokens (`subprocess.run`, `subprocess.Popen`,
  `os.system`, `os.popen`, `shell=True`, `gh pr`, `git push`,
  `git commit`, `eval(`, `exec(`, `anthropic`, `openai`).
- Module does NOT import or call `reporting.execution_authority`
  (the canonical classifier integration is A20c's job).
- Module does NOT reference canonical roadmap file paths as
  runtime read targets (no fuzzy parsing of the roadmap docs).

The strings `research/research_latest.json`,
`research/strategy_matrix.csv`, `live/**`, `paper/**`, `shadow/**`,
`broker/**`, `agent/risk/**`, and `agent/execution/**` are
intentionally allowed to appear inside the baseline `forbidden_files`
declarations and inside this governance doc. They are forbidden as
import targets, write targets, and runtime call surfaces; they are
**not** forbidden as forbidden-path declarations.

### 15.3 A20c

Pinned in [`tests/unit/test_roadmap_unit_authority.py`](../../tests/unit/test_roadmap_unit_authority.py):

- Closed vocabularies (`AUTHORITY_CLASS`, `AUTHORITY_REASON`,
  `AUTHORITY_EVIDENCE_KIND`, `AUTHORITY_PROJECTION_STATUS`) are
  exact; `AUTHORITY_CLASS` matches the canonical
  `reporting.execution_authority.DECISIONS` verbatim.
- Schema field tuples (`UNIT_AUTHORITY_EVIDENCE_FIELDS`,
  `UNIT_AUTHORITY_DECISION_FIELDS`,
  `UNIT_AUTHORITY_PROJECTION_FIELDS`) are exact and ordered.
- Every A20b `ImplementationUnit` receives exactly one
  `UnitAuthorityDecision`; phase + roadmap_task_id match upstream.
- `final_authority_class` is in the closed vocab;
  `max_severity` matches its severity index;
  `requires_operator_go` and `permanently_denied` flags are
  consistent.
- Synthetic-unit aggregation tests cover each tier:
  - all `AUTO_ALLOWED` evidence → `AUTO_ALLOWED`;
  - `canonical_policy_doc` / `canonical_roadmap` / `claude_governance_hook`
    / `dashboard_wiring` in `expected_files[]` → `NEEDS_HUMAN`;
  - `broker/**`, `agent/risk/**`, `agent/execution/**`,
    `automation/live_gate.py` in `expected_files[]` →
    `PERMANENTLY_DENIED`;
  - `research/research_latest.json` /
    `research/strategy_matrix.csv` in `expected_files[]` →
    `PERMANENTLY_DENIED`;
  - `target_layer == "live"` → `PERMANENTLY_DENIED`;
  - `target_layer == "paper"` / `"shadow"` → `NEEDS_HUMAN`
    (never `AUTO_ALLOWED`);
  - `operator_gate ∈ {"operator_go_required",
    "governance_bootstrap_pr_required"}` → `NEEDS_HUMAN`;
  - `unit_kind ∈ {"research_module", "diagnostic_primitive",
    "external_intelligence_source"}` → `NEEDS_HUMAN`.
- Fail-closed tests cover each non-path evidence kind:
  unknown / invalid `risk_class` / `target_layer` /
  `operator_gate` / `authority_hint` / `unit_kind` →
  `NEEDS_HUMAN`; `fail_closed = true`.
- `forbidden_file_classifier` evidence is recorded but is in
  `_INFORMATIONAL_EVIDENCE_KINDS`; the baseline synthetic unit
  proves its forbidden list does not elevate its aggregate.
- For every emitted decision on `main`,
  `classifier_used = true` (every unit has non-empty
  `expected_files`).
- No `AUTO_ALLOWED` aggregate on `main` rests on a `live_path` /
  `frozen_contract` / `branch_protection_config` per-file
  evidence record.
- Authority invariants pin: `calls_execution_authority_classifier
  = true`, `final_authority_classified = true`,
  `no_runtime_trading_authority = true`, `no_step5_runtime = true`,
  `no_level6 = true`, `no_production_merge_authority = true`,
  `writes_only_roadmap_unit_authority_log = true`,
  `aac_visibility_present = false`,
  `next_buildable_selector_present = false`,
  `mutates_a20a_artifact = false`, `mutates_a20b_artifact = false`.
- Deterministic byte-identical output for identical input with
  injected `generated_at_utc`.
- Sha256-before-vs-after confirms `collect_snapshot()` does not
  mutate the A20b in-memory artefact.
- Atomic-write allowlist refuses every path outside
  `logs/roadmap_unit_authority/`, including the frozen-contract
  paths.
- Module source carries no forbidden imports
  (subprocess, socket, urllib, http, requests, dashboard,
  automation, broker, agent.risk, agent.execution, research,
  live, paper, shadow, trading, reporting.intelligent_routing,
  reporting.development_queue_admission_policy,
  reporting.development_agent_activity_timeline) and no forbidden
  runtime tokens (`subprocess.run`, `subprocess.Popen`,
  `os.system(`, `os.popen(`, `shell=True`, `eval(`, `exec(`,
  `anthropic`, `openai`, GitHub API hosts).
- Module imports are restricted to stdlib +
  `reporting.execution_authority` + `reporting.roadmap_task_units`.

---

### 15.4 A20d

Pinned in [`tests/unit/test_development_agent_activity_timeline.py`](../../tests/unit/test_development_agent_activity_timeline.py):

- Catalog cardinality flip: `UPSTREAM_CATALOG_LEN == 14`,
  `PROJECTABLE_UPSTREAM_LEN == 7`, `HEALTH_ONLY_UPSTREAM_LEN == 7`;
  `len(SOURCE_KINDS) == 16`.
- Three new closed `source_kind` values:
  `roadmap_task_catalog`, `roadmap_implementation_unit`,
  `roadmap_unit_authority_decision`.
- Three new `UPSTREAM_CATALOG` entries, all projectable, all
  grouped under `roadmap`; each pointing at
  `logs/roadmap_*/latest.json`.
- `TTL_BY_GROUP["roadmap"] == 1800`.
- A20a catalog present → emits one `WorkItem` per `RoadmapTask`
  with `read_only=True`, `mutation_allowed=False`,
  `current_stage="discovered"`, `human_needed=False`,
  `owner_role="product_owner"`, `risk="low"`.
- A20b units present → emits one `WorkItem` per
  `ImplementationUnit`. `AUTO_ALLOWED_CANDIDATE` hint →
  `current_stage="discovered"`, `human_needed=False`.
  `NEEDS_HUMAN_CANDIDATE` hint or `operator_gate != "none"` →
  `current_stage="needs_human"`, `human_needed=True`.
  `PERMANENTLY_DENIED_SURFACE` hint →
  `current_stage="done_blocked"`.
- A20c decisions present → emits one `WorkItem` per
  `UnitAuthorityDecision`. `permanently_denied=True` →
  `current_stage="done_blocked"`, `risk="high"`.
  `requires_operator_go=True` →
  `current_stage="needs_human"`, `human_needed=True`.
  Otherwise → `current_stage="discovered"`.
- Missing roadmap artefacts → graceful absence (no work_items
  emitted, no crash; artefact-health rows still appear for the
  three new entries).
- Malformed roadmap artefact → `parse_ok=False` with bounded
  `parse_error`; no crash.
- A20b / A20c human_actions: `required_phrase=None`,
  `copy_only=True`. The aggregator MUST NOT synthesise an
  operator-go phrase for roadmap rows.
- No mutation verb appears in any roadmap-row `next_action`
  (`approve`, `reject`, `merge_now`, `deploy_now` all absent).
- AAC `invariant_status` continues to pin
  `level_6=permanently_disabled` / `danger_off`,
  `step5_implementation_allowed=False`, `step5_substage="none"`.
- A20d does NOT introduce a `next_buildable_unit` / `selected_next_unit`
  / `next_unit_selection` key into the envelope (A20e emits its own
  artefact at `logs/roadmap_next_unit/latest.json` instead of
  extending the AAC envelope).

### 15.5 A20e

Pinned in [`tests/unit/test_roadmap_next_unit.py`](../../tests/unit/test_roadmap_next_unit.py):

- Closed vocabularies (`NEXT_UNIT_SELECTION_STATUS`,
  `NEXT_UNIT_BLOCK_REASON`, `NEXT_UNIT_ELIGIBILITY`,
  `NEXT_UNIT_SOURCE`, `NEXT_UNIT_SELECTOR_MODE`) are exact.
- Schema field tuples (`NEXT_BUILDABLE_UNIT_CANDIDATE_FIELDS`,
  `NEXT_BUILDABLE_UNIT_SELECTION_FIELDS`,
  `NEXT_BUILDABLE_UNIT_PROJECTION_FIELDS`) are exact and ordered.
- Phase order matches A20a/A20b PHASE; authority order excludes
  `PERMANENTLY_DENIED`; risk order matches classifier enum;
  operator-gate order matches A20b enum; buildable-status set is
  a subset of A20b `UNIT_STATUS`.
- Happy path: an AUTO_ALLOWED unit is selected with
  `selection_status="OK_SELECTED"`, `requires_operator_go=False`,
  `fail_closed=False`.
- `PERMANENTLY_DENIED` units are blocked with
  `permanently_denied_authority`; the selector never selects
  them; a mixed pool prefers the AUTO_ALLOWED unit over the
  denied one.
- Unknown authority class blocks with `unknown_authority`;
  missing authority decision blocks with
  `missing_authority_decision`; duplicate authority decisions
  block with `duplicate_authority_decision`.
- Unknown prerequisite target blocks with
  `unknown_prerequisite_target`; unsatisfied prerequisite
  (status ≠ "merged") blocks with `unsatisfied_prerequisite`;
  satisfied prerequisite (all merged) allows the candidate.
- All-blocked-by-prerequisites case yields
  `selection_status="ALL_BLOCKED_BY_PREREQUISITES"`,
  `fail_closed=True`.
- NEEDS_HUMAN units may be selected only as
  `NEEDS_HUMAN_GATED`; selection_status is
  `ALL_NEEDS_HUMAN_GATED`; `requires_operator_go=True`.
- Operator_gate ≠ "none" promotes an AUTO_ALLOWED unit to
  `NEEDS_HUMAN_GATED`.
- ELIGIBLE candidates are preferred over NEEDS_HUMAN_GATED even
  when the gated candidate would otherwise sort earlier.
- Non-buildable A20b status (`in_flight`, `merged`, `blocked`,
  `human_needed`, `permanently_denied`) blocks the candidate
  with `non_buildable_status`. Unknown A20b status blocks with
  `unknown_unit_status` → `fail_closed=True`.
- Deterministic sort: phase order → authority order → risk order
  → operator-gate order → unit-id lex tie-break. No ISO 8601
  timestamps anywhere in any sort key.
- Selection is stable across two consecutive runs with the same
  injected `generated_at_utc`.
- Missing unit artefact / missing authority artefact / both
  missing / malformed unit artefact all yield
  `selection_status="UPSTREAM_UNAVAILABLE"` with
  `fail_closed=True`; the matching upstream identifier appears
  in `selection_reason`.
- Empty units list yields `NO_ELIGIBLE_UNITS` with
  `fail_closed=True`.
- Byte-identical output for identical input with injected
  `generated_at_utc`. Sha256-before-vs-after pins assert the
  upstream A20b and A20c artefacts are not mutated.
- Atomic-write allowlist refuses every path outside
  `logs/roadmap_next_unit/`, including the frozen-contract paths.
- CLI: `--no-write` writes nothing; `--status` writes nothing
  and emits the expected invariant strings; default writes to
  the allowlisted path; `--indent 0` produces compact output.
- Selector invariants pin: `no_work_execution=True`,
  `no_branch_creation=True`, `no_pr_creation=True`,
  `no_merge_or_deploy=True`, `no_mutation_routes=True`,
  `no_approval_buttons=True`, `no_runtime_trading_authority=True`,
  `no_step5_runtime=True`, `no_level6=True`,
  `no_production_merge_authority=True`,
  `mutates_a20b_artifact=False`, `mutates_a20c_artifact=False`,
  `writes_to_seed_jsonl=False`,
  `fail_closed_on_unknown_evidence=True`,
  `fail_closed_on_duplicate_authority=True`,
  `fail_closed_on_missing_artifact=True`,
  `permanently_denied_units_never_selected=True`,
  `needs_human_units_require_operator_go=True`,
  `calls_execution_authority_classifier=False` (A20c is the only
  classifier call site).
- Module-source scan: stdlib + `reporting.roadmap_task_units` +
  `reporting.roadmap_unit_authority` imports only; no
  subprocess, no network, no `gh`, no `git`, no GitHub API, no
  LLM, no `reporting.execution_authority` import.

## 16. Cross-references

- [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md)
- [`docs/governance/execution_authority.md`](execution_authority.md)
- [`docs/governance/no_touch_paths.md`](no_touch_paths.md)
- [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md)
- [`docs/governance/step5_design.md`](step5_design.md)
- [`docs/governance/development_roadmap_intake.md`](development_roadmap_intake.md)
- [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md)
- [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md)
- [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](../roadmap/qre_roadmap_v6_ade_operating_manual.md)
- [`docs/roadmap/qre_roadmap_v6_phase_prompts.md`](../roadmap/qre_roadmap_v6_phase_prompts.md)
