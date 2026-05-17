# Roadmap Task Catalog — A20a (read-only, deterministic seed)

> **Status:** Implemented (read-only, deterministic, dry-run by
> default).
>
> **Module:** [`reporting/roadmap_task_catalog.py`](../../reporting/roadmap_task_catalog.py)
> **Output artefact:** `logs/roadmap_task_catalog/latest.json`
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

## 7. Future stages (A20b–A20e)

The roadmap task catalog is the foundation of a staged sequence.
Each subsequent stage requires a separate operator-go PR. None of
them is pre-authorized by A20a.

- **A20b — Implementation Unit Decomposer.** Converts each
  `RoadmapTask` into one or more PR-sized `ImplementationUnit`
  records with explicit `expected_files[]`, `forbidden_files[]`,
  `required_tests[]`, `definition_of_done[]`, `stop_conditions[]`,
  and `prerequisites[]`. Deterministic data, no LLM, no fuzzy
  parsing. Forbidden files must always include the live / paper /
  shadow / risk / broker / execution globs and the frozen-contract
  paths, regardless of the unit's primary surface.
- **A20c — Authority / Risk Classifier Integration.** Annotates
  each `ImplementationUnit` with an aggregate
  `UnitAuthorityDecision` derived purely from
  [`reporting/execution_authority.py`](../../reporting/execution_authority.py).
  Aggregation is max-severity over per-file decisions. Fail-closed:
  unknown risk → `NEEDS_HUMAN`; any protected-path / frozen / live
  surface → `PERMANENTLY_DENIED` or `NEEDS_HUMAN` per the
  classifier's existing policy.
- **A20d — Read-only AAC / Task-Board Visibility.** Exposes the
  catalog + units + authority decisions to the operator through
  the existing read-only surfaces (`reporting/task_board.py`,
  `reporting/agent_flow.py`, AAC aggregator). No mutation routes,
  no approval buttons, no `dashboard/dashboard.py` edit unless a
  separate operator-authored governance-bootstrap PR enables it.
  Any AAC aggregator cardinality change requires its own
  operator-go PR.
- **A20e — Deterministic Next-Buildable-Unit Selector.**
  Pure-deterministic filter + sort over A20c output. Eligibility
  requires: `status ∈ {not_started, ready}`; all prerequisites in
  `status = merged`; `operator_gate = none`;
  `aggregate_decision = AUTO_ALLOWED`; no triggered
  forbidden-surface reasons. Fail-closed: zero eligible →
  `selected_unit_id = None` with `selection_reason =
  "no_eligible_units"`. No hidden LLM judgment.

A20a does not produce, imply, or depend on any of the above. Each
must justify its own scope on its own PR.

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
