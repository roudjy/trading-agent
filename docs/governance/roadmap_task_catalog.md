# Roadmap Task Catalog — A20a + A20b + A20c (read-only, deterministic)

> **Status:** A20a implemented; A20b implemented; A20c implemented
> (read-only, deterministic, dry-run by default). All three modules
> are projections; none surfaces to the AAC / dashboard, none
> selects a next-buildable unit.
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
- No edits to the AAC aggregator
  ([`reporting/development_agent_activity_timeline.py`](../../reporting/development_agent_activity_timeline.py))
  or its 11-entry upstream catalog cardinality. That cardinality
  amendment, if ever needed, is a separate operator-go PR.
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

## 9. Future stages (A20d–A20e)

The roadmap task catalog + unit decomposer + unit-authority
projection is the foundation of the remaining staged sequence.
Each subsequent stage requires a separate operator-go PR. None of
them is pre-authorized by A20a, A20b, or A20c.

- **A20d — Read-only AAC / Task-Board Visibility.** Exposes the
  catalog + units + authority decisions to the operator through
  the existing read-only surfaces (`reporting/task_board.py`,
  `reporting/agent_flow.py`, AAC aggregator). No mutation routes,
  no approval buttons, no `dashboard/dashboard.py` edit unless a
  separate operator-authored governance-bootstrap PR enables it.
  Any AAC aggregator cardinality change requires its own
  operator-go PR. A20d will flip `aac_visibility_present` to
  `true`.
- **A20e — Deterministic Next-Buildable-Unit Selector.**
  Pure-deterministic filter + sort over A20c output. Eligibility
  requires: `status ∈ {not_started, ready}`; all prerequisites in
  `status = merged`; `operator_gate = none`;
  `aggregate_decision = AUTO_ALLOWED`; no triggered
  forbidden-surface reasons. Fail-closed: zero eligible →
  `selected_unit_id = None` with `selection_reason =
  "no_eligible_units"`. No hidden LLM judgment. A20e will flip
  `next_buildable_selector_present` to `true`.

Neither A20a nor A20b produces, implies, or depends on any of the
above. Each must justify its own scope on its own PR.

---

## 8. CLI

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

## 9. Determinism contract

- Tasks are sorted by `(phase, id)` ascending.
- Requirements are sorted by `(phase, id)` ascending.
- All free-text fields are bounded.
- Output is `json.dumps(..., sort_keys=True, indent=2) + "\n"`.
- `generated_at_utc` is the only non-deterministic field. Tests
  inject it for byte-identical fixtures.
- Atomic write via `os.replace(...)` from a same-directory
  `tempfile.mkstemp(...)`. No tmp files left behind on failure.

---

## 10. Test coverage

### 10.1 A20a

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

### 10.2 A20b

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

### 10.3 A20c

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

## 11. Cross-references

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
