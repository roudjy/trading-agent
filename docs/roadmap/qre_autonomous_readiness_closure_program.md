# ADE-QRE-023 Autonomous Research Readiness Closure Loop

## Status

Active governed follow-on program after ADE-QRE-022.

ADE-QRE-023 admits a bounded deterministic closure loop that can rerun the
research-readiness pipeline, classify the next exact blocker, apply the
smallest governed remediation, replay downstream readiness, and continue until
at least one strategy becomes genuinely `READY_FOR_PREREGISTRATION` or a valid
terminal blocker is reached.

## Authority

ADE-QRE-023 may:

- diagnose exact campaign-readiness blockers for research-registered
  strategies;
- classify blockers through a closed taxonomy and dependency graph;
- create bounded remediation plans and route them to existing governed
  repository capabilities;
- resolve canonical universes, point-in-time membership, deterministic
  timeframes, bounded presets, source/dataset/snapshot bindings, window
  capacity, cost/slippage bindings, regime bindings, null-control readiness,
  campaign metadata, and campaign lineage when authoritative evidence exists;
- replay the affected downstream readiness chain automatically;
- continue through multiple remediation cycles without operator restarts;
- create a second-campaign preregistration manifest only when at least one cell
  is genuinely `READY_FOR_PREREGISTRATION`.

ADE-QRE-023 may not:

- invent identities, sources, datasets, snapshots, windows, OOS independence,
  costs, slippage, signal density, or empirical evidence;
- loosen readiness thresholds, reuse consumed OOS windows, or silently relabel
  a downstream blocker as solved;
- execute campaigns;
- grant paper, shadow, live, broker, risk, execution, or capital authority;
- write to protected `research/**` surfaces;
- modify `.claude/**`.

## Program Units

### ADE-QRE-023A - Autonomous Closure Governance
### ADE-QRE-023B - Blocker Taxonomy and Dependency Graph
### ADE-QRE-023C - Remediation Planner
### ADE-QRE-023D - Canonical Universe Authority
### ADE-QRE-023E - Historical Universe Membership
### ADE-QRE-023F - Timeframe Resolution
### ADE-QRE-023G - Preset Completion
### ADE-QRE-023H - Source, Dataset and Snapshot Binding
### ADE-QRE-023I - Window and Independent OOS Capacity
### ADE-QRE-023J - Null-Control Implementation Closure
### ADE-QRE-023K - Cost, Slippage and Regime Binding
### ADE-QRE-023L - Campaign Metadata and Lineage Closure
### ADE-QRE-023M - Autonomous Capability Generator Integration
### ADE-QRE-023N - Iterative Readiness Replay
### ADE-QRE-023O - Second-Campaign Preregistration
### ADE-QRE-023P - Integrated Closure Report

## Definition of Done

ADE-QRE-023 is complete only when:

- a deterministic blocker taxonomy, dependency graph, remediation planner, and
  iterative readiness replay engine exist outside `research/**`;
- the loop has executed against the resolver-visible generated strategies,
  including `qgs_e565b01bd0a162d0` and `qgs_5af8f605ba82ae53`;
- at least one readiness blocker has been causally resolved or irreducibly
  fail-closed with exact evidence;
- every loop iteration records before-state, selected blocker, remediation,
  generated or repaired capability, validation, after-state, and blocker delta;
- the loop stops only at a valid terminal outcome:
  `READY_FOR_PREREGISTRATION`,
  `READY_FOR_SECOND_CAMPAIGN`,
  `EXTERNALLY_BLOCKED`,
  `SCIENTIFICALLY_BLOCKED`,
  `NO_VALID_REMEDIATION_PATH`,
  `SAFETY_POLICY_BLOCKED`,
  `DATA_CAPACITY_BLOCKED`, or
  `INDEPENDENT_OOS_CAPACITY_BLOCKED`;
- any second-campaign manifest remains fail-closed unless a cell is genuinely
  `READY_FOR_PREREGISTRATION`;
- tests, governance lint, architecture tests, and architecture import scan are
  green;
- frozen contracts and protected execution surfaces remain unchanged.

## Permanent Restrictions

- no `.claude/**` edits;
- no `research/**` empirical writes;
- no edits to `research/research_latest.json`;
- no edits to `research/strategy_matrix.csv`;
- no invented identities, datasets, snapshots, windows, OOS independence, or
  empirical null results;
- no automatic threshold relaxation;
- no campaign execution;
- no paper, shadow, live, broker, risk, execution, or capital-allocation
  authority;
- no fabricated progress; repeated generation of equivalent artifacts is not
  counted as remediation progress.
