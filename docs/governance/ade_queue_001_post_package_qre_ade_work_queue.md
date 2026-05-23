# ADE-QUEUE-001 - Post-Package QRE/ADE Work Queue

> Status: bounded queue proposal for operator review.
>
> Primary source: `docs/strategy/QRE_ADE_How_To_Target_State_Roadmap.md`.
> Supporting sources: `docs/roadmap/Roadmap v6.md`,
> `docs/governance/roadmap_scope_status.md`, and
> `docs/architecture/PACKAGE-MIGRATION-010-package-migration-closure-decision.md`.
>
> This document does not activate Addendum 1, Addendum 2, Addendum 3,
> Addendum 4,
> v4.x Shadow, v5.x Paper, v6.x Live, or any live/paper/shadow/risk/broker/
> execution behavior. It also does not update `docs/development_work_queue/seed.jsonl`.

## Queue Selection Rules

- Work starts from the post-package QRE Feature Build Track.
- `QRE_ADE_How_To_Target_State_Roadmap.md` is the queue's primary product/research source.
- The first executable item must improve research evidence or diagnostics before any strategy synthesis.
- Addendum 1, Addendum 2, Addendum 3, and Addendum 4 remain reference-only unless a future operator-approved ADR activates a specific subsection.
- Frozen contracts stay unchanged: `research/research_latest.json`, `research/strategy_matrix.csv`, frozen schemas, and regression pins.
- The architecture scanner must keep `forbidden_edge_count = 0`.
- Transcript and weekly files remain untracked and out of commits.

## Current Evidence Baseline

- `research/research_latest.json` currently reports 24 successful historical result rows, 0 failed rows, and 0 approved rows.
- `reporting.architecture_import_scan --format summary` reports 0 hard forbidden edges and existing legacy/report-only edges.
- `reporting.research_observability_minimal --status` reports no latest snapshot.
- `reporting.intelligent_routing_diagnostic_signals --status` reports schema-only routing signals; no routing mutation, campaign mutation, or trading authority.
- The failed Nightly slow suite on `main` is non-blocking and failed in the functional job because `pytest --run-functional` was not recognized by that workflow environment.

## Queue Items

### ADE-QRE-001 - Unknown Failure Reduction

- queue id: `ADE-QRE-001`
- status: `done`
- completion evidence: PR #309, merge SHA `d35e9d85f2ffccb102e4b3257cffd8b747283d51`; post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: reduceer `unknown_screening_failure` naar deterministische, evidence-backed subklassen.
- bron uit target-state roadmap: fase 1 "Unknown Failure Reduction Sprint"; prompt 12.1; trusted loop metrics `unknown_failure_rate`, `actionable_failure_rate`, `attribution_depth_score`.
- scope: inspecteer bestaande screening/no-candidate evidence, voeg alleen deterministische classificatie toe voor reeds observeerbare failure shapes, en rapporteer before/after unknown counts.
- verboden scope: strategiecode, registry-wijzigingen, campaign behavior, routing mutation, dashboard mutation routes, frozen contract changes, live/paper/shadow/risk/broker/execution paths.
- files likely touched: `research/screening_failure_attribution.py`, `research/screening_evidence.py`, `research/synthesis_gate.py` only if new classes affect existing gate allowlists, `tests/unit/test_screening_failure_attribution.py`, `tests/unit/test_synthesis_gate.py`, and a focused governance note if needed.
- tests/validation: `pytest tests/unit/test_screening_failure_attribution.py tests/unit/test_synthesis_gate.py -q`, `pytest tests/architecture -q`, `python -m reporting.architecture_import_scan --format summary`; optional artifact dry-run/status command if the module supports it.
- merge/deploy criteria: unknown classifications are lower or explicitly proven not reducible with current artifacts; no public output contract mutation; scanner has 0 forbidden edges; Fast pre-merge gate green.
- stop condition: new classification needs unavailable data, would require source-quality or data-foundation scope, or touches strategy/runtime execution.
- expected next queue item: `ADE-QRE-002`.

### ADE-QRE-002 - Screening Failure Attribution Depth

- queue id: `ADE-QRE-002`
- status: `done`
- completion evidence: PR #310, merge SHA `d4fc1d35362262ab59f23a3734c4fe5ba2910f6d`; Fast pre-merge gate, Docker build/push, and VPS deploy post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: make screening failures more actionable after unknown reduction by mapping classes to stable failure-to-action recommendations.
- bron uit target-state roadmap: current weakness "Attribution depth"; fase 7 "Failure -> Action -> Reroute sluiten"; prompt 12.1 follow-up.
- scope: enrich existing attribution output with deterministic action hints for known non-strategy failure classes and keep them read-only.
- verboden scope: adaptive feedback loops, routing mutation, campaign enqueueing, strategy generation, frozen contract mutation, live/paper/shadow/risk/broker/execution paths.
- files likely touched: `research/screening_failure_attribution.py`, `research/synthesis_gate.py`, `reporting/failure_action_mapping_minimal.py`, `tests/unit/test_screening_failure_attribution.py`, `tests/unit/test_failure_action_mapping_minimal.py`.
- tests/validation: targeted unit tests for attribution/action mapping, `pytest tests/architecture -q`, `python -m reporting.architecture_import_scan --format summary`.
- merge/deploy criteria: every new action hint is explainable from existing artifact evidence and remains advisory/read-only.
- stop condition: the work requires actual rerouting, source activation, or strategy behavior changes.
- expected next queue item: `ADE-QRE-003`.

### ADE-QRE-003 - Data Foundation Manifest and Coverage

- queue id: `ADE-QRE-003`
- status: `done`
- completion evidence: PR #311, merge SHA `dabd393ad2297eb4b1833b2a2b42b2f77f6b6a8f`; Fast pre-merge gate, Docker build/push, and VPS deploy post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: introduce a read-only local research cache manifest and coverage reporter before data-aware routing or hypothesis discovery depends on data readiness.
- bron uit target-state roadmap: fase 2 "Data Foundation als productlaag"; prompt 12.2 "Data Foundation v3.data.1"; data-throughput sections 9.4-9.6.
- scope: manifest schema, coverage report by source/instrument/timeframe, row counts, min/max timestamps, schema version, content hash, and deterministic sidecar output.
- verboden scope: live fetching, paid data, source adapters beyond manifest representation, parquet backfill, source activation from Addendum 3, strategy changes, frozen contract mutation.
- files likely touched: `packages/qre_data/`, `research/diagnostics/`, `reporting/`, `tests/unit/`, `tests/architecture/`, and a narrow docs/governance runbook.
- tests/validation: manifest schema tests, deterministic output tests, architecture scanner summary, targeted package-boundary tests.
- merge/deploy criteria: read-only sidecar exists, missing manifest fails closed, scanner has 0 forbidden edges, no runtime research output format changes.
- stop condition: implementation needs new external data acquisition or Addendum 3 activation.
- expected next queue item: `ADE-QRE-004`.

### ADE-QRE-004 - Source Identity and Quality Readiness

- queue id: `ADE-QRE-004`
- status: `done`
- completion evidence: PR #312, merge SHA `a075dee1a1a8e7d5ae7a8101ffd45d6c6e6847e8`; Fast pre-merge gate, Docker build/push, and VPS deploy post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: make source identity and source quality visible enough to explain data-related research failures.
- bron uit target-state roadmap: fase 2 `v3.data.2` and `v3.data.3`; sections 9.5-9.7; lessons learned "Eerst data als productlaag".
- scope: deterministic source-quality checks over existing manifest data, identity confidence fields, fail-closed readiness statuses, and operator-readable sidecar summary.
- verboden scope: OpenFIGI/CFTC/EIA/OpenBB/CoinGecko/vendor source activation, live fetches, source-derived alpha, live/paper/shadow/risk/broker/execution paths.
- files likely touched: `packages/qre_data/`, `packages/qre_policy/`, `research/diagnostics/`, `tests/unit/`, `tests/architecture/`, docs runbook.
- tests/validation: quality-gate unit tests, fail-closed missing/unknown identity tests, architecture scanner summary.
- merge/deploy criteria: source quality can block research-ready status without changing strategy or campaign behavior.
- stop condition: existing manifest lacks enough fields, or implementation requires Addendum 3 active scope.
- expected next queue item: `ADE-QRE-005`.

### ADE-QRE-005 - Research Memory v1

- queue id: `ADE-QRE-005`
- status: `done`
- completion evidence: PR #313, merge SHA `47015313362a44d84e216da30181985cae1947f2`; Fast pre-merge gate, Docker build/push, and VPS deploy post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: make prior hypotheses, failures, campaigns, and policy actions retrievable before new research is proposed or routed.
- bron uit target-state roadmap: fase 3 "Research Memory en Retrieval"; prompt 12.4 "Research Memory v1"; section 10 "Research memory ontwerp".
- scope: deterministic artifact index, simple ontology, keyword/metadata retrieval over existing local artifacts, related-failure lookup, and read-only sidecar output.
- verboden scope: Addendum 2 activation, knowledge graph database, embeddings/rerankers, cross-encoder, state models, strategy generation, routing mutation, live/paper/shadow/risk/broker/execution paths.
- files likely touched: `packages/qre_research/`, `packages/qre_artifacts/`, `reporting/`, `tests/unit/`, `tests/architecture/`, docs runbook.
- tests/validation: deterministic retrieval tests, no-network/no-subprocess source scan, architecture scanner summary.
- merge/deploy criteria: a new hypothesis or failure can be linked to prior local evidence without granting authority.
- stop condition: retrieval requires non-local data, LLM inference as authority, or Addendum 2 scope activation.
- expected next queue item: `ADE-QRE-006`.

### ADE-QRE-006 - Research Diagnostics Loop

- queue id: `ADE-QRE-006`
- status: `done`
- completion evidence: PR #314, merge SHA `b772c0172d5786343a4c4bf45aae854c84726b62`; Fast pre-merge gate, Docker build/push, and VPS deploy post-merge gates green; frozen contracts unchanged; protected paths untouched; live/paper/shadow/risk/broker/execution inactive.
- doel: close the read-only loop from failure classification to next diagnostic recommendation without mutating campaigns.
- bron uit target-state roadmap: fase 5 "Observability operator-grade maken"; fase 7 "Failure -> Action -> Reroute sluiten"; trusted loop criteria.
- scope: aggregate current attribution, failure-action mapping, data readiness, and research memory evidence into a single deterministic diagnostics-loop digest.
- verboden scope: automatic rerouting, campaign queue mutation, strategy/preset changes, dashboard mutation routes, adaptive learning side effects, execution-sensitive paths.
- files likely touched: `reporting/`, `packages/qre_diagnostics/`, `research/diagnostics/`, `tests/unit/`, `docs/governance/`.
- tests/validation: digest schema tests, missing-source fail-closed tests, architecture scanner summary, targeted observability tests.
- merge/deploy criteria: operator can see failure -> evidence -> recommended next diagnostic or stop action from sidecar data only.
- stop condition: any recommendation would require automatic queue/campaign mutation.
- expected next queue item: `ADE-QRE-007`.

### ADE-QRE-007 - Operator-Grade Observability

- queue id: `ADE-QRE-007`
- status: `done`
- completion evidence: implemented read-only operator-grade observability summary over unknown failure rate, actionable failure rate, attribution depth, data readiness, prior similar failures, diagnostics-loop state, and queue-governance blockers; local targeted tests and architecture scanner passed in the implementation branch; PR/merge evidence to be recorded if a later operator-approved queue item continues from this gate.
- doel: make QRE/ADE state understandable to the operator without reading code.
- bron uit target-state roadmap: fase 5 "Observability operator-grade maken"; target operator state; research observability minimal runbook.
- scope: read-only operator summary over unknown failure rate, actionable failure rate, attribution depth, data readiness, prior similar failures, and governance blockers.
- verboden scope: dashboard mutation routes, approval buttons, auto-execute controls, live/paper/shadow/risk/broker/execution activation, frozen contract changes.
- files likely touched: `reporting/research_observability_minimal.py`, `docs/governance/research_observability_minimal.md`, `tests/unit/test_research_observability_minimal.py`, optional read-only control-plane adapter only if explicitly scoped later.
- tests/validation: targeted observability tests, no mutation-route source scan, architecture scanner summary.
- merge/deploy criteria: read-only digest is available and stale/missing upstream artifacts are explicit.
- stop condition: implementation needs dashboard route mutation or operator action controls.
- expected next queue item: `ADE-QRE-008`.

### ADE-QRE-008 - Strategy Synthesis Readiness Gate

- queue id: `ADE-QRE-008`
- status: `done`
- completion evidence: operator reviewed the ADE-QRE-008 reassessment and selected
  `PROMOTE_TO_BOUNDED_NEXT_QUEUE_ITEM`; see
  `docs/governance/ade_qre_011_bounded_strategy_synthesis_readiness_decision.md`.
  The decision promotes only a docs/governance readiness item and does not
  authorize strategy synthesis implementation.
- doel: decide whether strategy synthesis or new research capability is eligible after evidence, data, memory, diagnostics, and observability mature.
- bron uit target-state roadmap: phase order "Pas daarna"; lessons "Hypothesis first, strategy second"; section 18 "Wat voorlopig bewust niet doen".
- scope: operator review of KPIs and evidence only; define whether a future strategy/research capability queue item is allowed.
- verboden scope: writing new strategy code, inventing strategies, activating paper/shadow/live, changing registry, bypassing frozen contracts.
- files likely touched: docs-only decision record or ADR if the operator authorizes next capability.
- tests/validation: evidence pack references prior queue outputs and scanner summary; no code tests unless a later scoped implementation is approved.
- merge/deploy criteria: explicit operator decision with promote/retire criteria and bounded follow-up scope.
- stop condition: unknown failure/data/memory/observability evidence is still insufficient.
- expected next queue item: `ADE-QRE-011`.

### ADE-QRE-011 - Bounded Strategy Synthesis Readiness Item

- queue id: `ADE-QRE-011`
- status: `ready`
- goal: define minimum evidence-gated conditions for future strategy synthesis
  consideration without implementing strategy behavior.
- operator decision: approved as a docs/governance-only queue item. This approval
  does not authorize strategy synthesis implementation.
- decision record:
  `docs/governance/ade_qre_011_bounded_strategy_synthesis_readiness_decision.md`.
- current evidence state:
  - data cache manifest: ready; `research_ready=true`.
  - source quality readiness: ready; `research_ready=true`.
  - research memory: ready.
  - diagnostics loop: ready.
  - observability: `operator_review_available`.
  - `unknown_failure_rate=0.0`.
  - `attribution_depth_score=1.0`.
  - architecture scanner `forbidden_edge_count=0`.
- remaining gaps:
  - `failure_action_mapping.status=not_ready` because `total_failures=0` and
    there is nothing actionable to map.
  - reason-records manifest is not materialized.
  - `routing_minimal` latest snapshot is missing.
  - `sampling_minimal` latest snapshot is missing.
  - KPI numeric values are unavailable; only KPI doctrine identifiers exist.
- allowed scope: governance docs, queue entry, operator decision record, and
  read-only evidence references.
- forbidden scope: strategy implementations, `registry.py`, research output
  mutation, paper/shadow/live, broker/risk/execution, source adapter activation,
  dashboard mutation routes, Addendum activation, broad refactors, runtime logs,
  and frozen contract changes.
- likely files:
  - `docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md`
  - `docs/governance/ade_qre_011_bounded_strategy_synthesis_readiness_decision.md`
- tests/validation:
  - `git diff --check`
  - `python -m reporting.architecture_import_scan --format summary`
  - `python -m reporting.research_observability_minimal --status`
  - verify architecture scanner `forbidden_edge_count` remains `0`
  - verify no frozen contracts changed
- promote criteria for a later strategy synthesis implementation item:
  - reason-records manifest is materialized, or the operator explicitly declares
    it not required with rationale.
  - `routing_minimal` latest snapshot is materialized, or the operator explicitly
    declares it not required with rationale.
  - `sampling_minimal` latest snapshot is materialized, or the operator explicitly
    declares it not required with rationale.
  - KPI numeric values are available, or the operator approves substitute
    criteria in writing.
  - no frozen contract mutation is required.
  - no `registry.py` changes are included unless separately and explicitly
    approved by the operator.
  - no paper/shadow/live or execution behavior is included.
  - bounded hypothesis/research capability scope is documented before any
    executable strategy code is proposed.
- defer criteria:
  - required evidence is absent but can be materialized by a bounded read-only
    diagnostics, observability, or governance item.
  - KPI substitute criteria are plausible but not yet operator approved.
  - the proposed implementation scope is not narrow enough to review safely.
- block criteria:
  - the next item would introduce strategy code before evidence gates are met.
  - the next item would modify `registry.py` without separate explicit operator
    approval.
  - the next item would mutate frozen contracts or research outputs.
  - the next item would activate paper/shadow/live, broker/risk/execution,
    source adapters, dashboard mutation routes, or Addendum scope.
- stop conditions:
  - any implementation file outside docs/governance becomes necessary.
  - validation reports architecture scanner forbidden edges.
  - frozen contracts or protected research outputs appear in the diff.
  - the future strategy synthesis criteria cannot be stated without inventing
    strategy behavior.
- merge criteria:
  - docs/governance-only diff.
  - ADE-QRE-008 marked done/operator-reviewed.
  - ADE-QRE-011 defined with explicit allowed scope, forbidden scope,
    promote/defer/block criteria, stop conditions, tests, and merge criteria.
  - validation commands pass, with scanner `forbidden_edge_count=0`.
- expected next queue item: `ADE-QRE-013`.

### ADE-QRE-013 - Trusted Loop Maturity Matrix and Roadmap v6 Addendum 4

- queue id: `ADE-QRE-013`
- status: `done`
- completion evidence: PR #318, merge SHA
  `cd036fc194a39a631559bab66ffb1ddd690590ca`; Fast pre-merge gate
  succeeded on branch commit `e4ddf9cfb23948eda30819fa3d7f2548c1c1186d`;
  the branch commit was superseded by squash merge `cd036fc`; no Actions runs
  are attached directly to `cd036fc`, which is recorded as a non-blocking
  docs-only post-merge absence because the merge touched only this queue
  document and the Addendum 4 reference document; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remains blocked.
- goal: document that the trusted-loop foundation exists, but is still
  scaffold/readiness evidence rather than operator-trusted research capability.
- addendum record:
  `docs/roadmap/Roadmap v6 Addendum 4 - Trusted Loop Readiness and Operator Trust.md`.
- sequencing note: the local work queue has no committed `ADE-QRE-012` entry at
  the time this docs-only item is added. `ADE-QRE-013` is therefore appended as
  the next available queue entry without backfilling or inventing `ADE-QRE-012`
  scope.
- allowed scope: documentation only; maturity matrix; readiness taxonomy;
  operator-trust gates; missing-evidence inventory; safe next docs/readiness
  queue candidates.
- forbidden scope: runtime functionality, strategy synthesis, strategy
  implementations, `registry.py`, research output mutation, tests unless docs
  lint requires them, logs, generated artifacts, frozen contracts,
  paper/shadow/live, broker/risk/execution, Addendum runtime activation, and
  broad refactors.
- current maturity finding:
  - ADE-QRE-001 through ADE-QRE-007 established trusted-loop scaffolding and
    read-only diagnostics/observability surfaces.
  - ADE-QRE-008 and ADE-QRE-011 established readiness decisions and gates, not
    strategy authority.
  - ADE-QRE-012 has no committed queue record in this branch and contributes no
    maturity credit.
  - strategy synthesis remains blocked.
- missing evidence:
  - reason records are 0.
  - routing snapshot has 0 ready items.
  - sampling snapshot has 0 ready items.
  - KPI numeric values are incomplete.
  - `failure_action_mapping` has no actionable failures.
  - approved strategies are 0.
  - no paper-ready candidate exists.
- safe next queue candidates: docs/readiness-only evidence inventory,
  operator-trust checklist, KPI completeness decision record, and
  reason-record/routing/sampling readiness audit. None may implement runtime
  behavior or activate strategy synthesis.
- tests/validation:
  - `git diff --check`
  - `python -m reporting.architecture_import_scan --format summary`
  - `git status --short`
- merge criteria:
  - exactly docs-only diff for this item.
  - Addendum 4 is marked `DEFERRED / REFERENCE-ONLY`.
  - Addendum 1, Addendum 2, Addendum 3, and Addendum 4 remain inactive.
  - no strategy synthesis, registry, strategy, frozen contract, research output,
    paper/shadow/live, broker/risk/execution, log, or generated artifact file is
    changed.
  - validation commands pass, with scanner `forbidden_edge_count=0`.
- operator review required: yes. This item documents readiness limits and must
  not be used as implementation authorization.
- expected next queue item: none unless the operator explicitly approves a
  future docs/readiness-only item.

### ADE-QRE-014A - Main/PR/Run Reconciliation Preflight

- queue id: `ADE-QRE-014A`
- status: `done`
- title: Main/PR/Run Reconciliation Preflight.
- purpose: reconcile PR #318, branch commit `e4ddf9c`, squash merge
  `cd036fc`, origin/main, and GitHub Actions evidence before any new build
  work.
- risk class: LOW.
- target layer: governance queue / PR lifecycle evidence.
- expected files or file families:
  - `docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md`.
- forbidden files or file families:
  - `research/research_latest.json`, `research/strategy_matrix.csv`,
    `registry.py`, strategy implementations, paper/shadow/live, broker, risk,
    execution, runtime logs, generated artifacts, frozen contracts, and
    Addendum runtime activation paths.
- prerequisites:
  - clean working tree before branch creation.
  - origin/main fetched.
  - GitHub CLI auth and repo view succeed.
- allowed changes:
  - docs/governance queue update only.
  - reconciliation evidence and next queue decomposition only.
- forbidden changes:
  - implementation work.
  - strategy synthesis.
  - Addendum 1, Addendum 2, Addendum 3, or Addendum 4 runtime activation.
  - mutation of research outputs or protected/execution paths.
- reconciliation evidence:
  - local branch before queue work: `main`.
  - local HEAD before queue work:
    `cd036fc194a39a631559bab66ffb1ddd690590ca`.
  - `origin/main`:
    `cd036fc194a39a631559bab66ffb1ddd690590ca`.
  - PR #318 state: `MERGED`.
  - PR #318 merge commit:
    `cd036fc194a39a631559bab66ffb1ddd690590ca`.
  - PR #318 head branch: `docs/ade-qre-013-trusted-loop-maturity`.
  - Fast pre-merge run `26336444135`: `completed/success`, event `push`,
    branch `docs/ade-qre-013-trusted-loop-maturity`, head SHA
    `e4ddf9cfb23948eda30819fa3d7f2548c1c1186d`.
  - `e4ddf9c` is not an ancestor of `cd036fc` because PR #318 was
    squash-merged.
  - `e4ddf9c` remains the remote branch head at
    `origin/docs/ade-qre-013-trusted-loop-maturity`.
  - no Actions runs were listed directly for commit `cd036fc`.
  - latest main-branch Actions runs were earlier than PR #318 merge time.
  - `cd036fc` touched only this queue document and
    `docs/roadmap/Roadmap v6 Addendum 4 - Trusted Loop Readiness and Operator Trust.md`.
- tests required:
  - `git diff --check`.
  - `python -m reporting.architecture_import_scan --format summary`.
  - `python -m pytest tests/smoke -q`.
- validation required:
  - GitHub PR metadata confirms PR #318 is merged.
  - local main and origin/main agree on `cd036fc`.
  - docs-only post-merge Actions absence is recorded as non-blocking.
  - frozen contracts unchanged.
  - protected/execution paths untouched.
  - strategy synthesis remains blocked.
  - Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
- merge criteria:
  - docs/governance-only diff for the queue update.
  - Fast pre-merge gate green on the 014A PR.
  - no protected or frozen path diff.
  - squash merge only.
- done criteria:
  - queue decomposition is committed.
  - 014A reconciliation evidence is recorded.
  - 014B is the next eligible item only after 014A PR merge, green CI, and
    acceptable post-merge validation.
- stop conditions:
  - remote auth failure.
  - local git state is not clean or cannot be reconciled.
  - PR #318 is not merged.
  - `cd036fc` is not `origin/main`.
  - non-docs changes appear in PR #318 or the 014A diff.
  - protected/frozen/execution path changes are required.
- next dependency: `ADE-QRE-014B`.

### ADE-QRE-014B - Reason-Record Evidence Density

- queue id: `ADE-QRE-014B`
- status: `in_progress`
- title: Reason-Record Evidence Density.
- purpose: improve trusted-loop reason-record evidence density so ADE/QRE
  decisions are more inspectable, measurable, and operator-readable before
  routing, sampling, KPI maturity, or strategy synthesis work.
- risk class: LOW unless code discovery proves otherwise.
- target layer: read-only reporting, diagnostics, and QRE artifacts evidence.
- expected files or file families:
  - read-only `reporting/**.py`, `packages/qre_artifacts/**`,
    `packages/qre_diagnostics/**`, `packages/qre_research/**`,
    `tests/unit/**`, `tests/architecture/**`, and narrow docs/governance
    runbook updates.
- forbidden files or file families:
  - `research/research_latest.json`, `research/strategy_matrix.csv`,
    `registry.py`, strategy implementations, frozen schemas, regression pins,
    paper/shadow/live, broker, risk, execution, automation, orchestration,
    runtime logs, generated artifacts unless explicitly deterministic
    sidecars are already established.
- prerequisites:
  - 014A merged and post-merge validation acceptable.
  - existing reason-record producers and consumers inspected.
  - no implementation starts until the file-level authority remains LOW and
    auto-allowed.
- allowed changes:
  - deterministic read-only reason-record inventory, schema completion, density
    metrics, fail-closed missing evidence status, and focused tests.
- active implementation note:
  - 014A is done on `main`; 014B implementation is limited to read-only
    reporting sidecars, reason/evidence density inspection, focused tests, and
    this queue status update.
- forbidden changes:
  - campaign mutation, routing mutation, strategy generation, registry edits,
    research output mutation, Addendum activation, dashboard mutation routes,
    and execution behavior.
- tests required:
  - targeted unit tests for changed reason-record/reporting modules.
  - relevant architecture/package-boundary tests.
  - `git diff --check`.
  - `python -m reporting.architecture_import_scan --format summary`.
- validation required:
  - reason records are countable and explainable from existing artifacts.
  - missing/empty evidence fails closed.
  - frozen contracts unchanged.
  - protected/execution paths untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused read-only/reporting diff.
  - tests and Fast pre-merge gate green.
  - no strategy, registry, frozen contract, or execution path changes.
- done criteria:
  - PR merged by squash.
  - CI green.
  - post-merge gates green or explicitly non-blocking.
  - queue status can advance 014C.
- stop conditions:
  - evidence density requires new research execution, artifact mutation outside
    scoped sidecars, protected paths, approval mutation, or HIGH/UNKNOWN
    authority.
- next dependency: `ADE-QRE-014C`.

### ADE-QRE-014C - KPI Numeric Readiness Completion

- queue id: `ADE-QRE-014C`
- status: `blocked until ADE-QRE-014B done`
- title: KPI Numeric Readiness Completion.
- purpose: make trusted-loop readiness KPIs numerically complete and
  fail-closed where values are missing, unknown, or not derivable from
  evidence.
- risk class: LOW unless code discovery proves otherwise.
- target layer: read-only reporting, diagnostics, policy/readiness surfaces,
  and tests.
- expected files or file families:
  - `reporting/**.py`, `packages/qre_diagnostics/**`,
    `packages/qre_policy/**`, `tests/unit/**`, `tests/architecture/**`, and
    narrow docs/governance notes.
- forbidden files or file families:
  - frozen contracts, `registry.py`, strategy implementations, research output
    artifacts, live/paper/shadow/risk/broker/execution, automation,
    orchestration, Addendum runtime activation paths, regression pins.
- prerequisites:
  - 014B evidence is merged and available.
  - KPI doctrine and current numeric gaps are mapped to existing evidence.
- allowed changes:
  - deterministic KPI calculations over existing evidence.
  - explicit unavailable/unknown handling that fails closed.
  - operator-readable missing-evidence reasons.
  - focused tests for numeric completeness and fail-closed behavior.
- forbidden changes:
  - substitute KPI thresholds without documented basis.
  - make unknown values pass.
  - strategy synthesis, routing mutation, campaign mutation, or runtime
    activation.
- tests required:
  - targeted KPI unit tests.
  - relevant observability/readiness tests.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - all reported readiness KPIs are numeric or explicitly fail-closed.
  - no hidden defaults convert unknown to ready.
  - frozen contracts unchanged.
  - protected/execution paths untouched.
- merge criteria:
  - tests and CI green.
  - KPI readiness remains read-only/reporting-oriented.
- done criteria:
  - PR merged by squash.
  - post-merge validation acceptable.
  - queue status can advance 014D.
- stop conditions:
  - KPI completion requires protected paths, source activation, research output
    mutation, or operator-defined thresholds not present in the repo.
- next dependency: `ADE-QRE-014D`.

### ADE-QRE-014D - Routing/Sampling Readiness Density

- queue id: `ADE-QRE-014D`
- status: `blocked until ADE-QRE-014C done`
- title: Routing/Sampling Readiness Density.
- purpose: increase `routing_ready` and `sampling_ready` evidence density
  using existing artifacts and read-only readiness evaluation only.
- risk class: LOW unless code discovery proves otherwise.
- target layer: read-only routing/sampling diagnostics and readiness reports.
- expected files or file families:
  - `reporting/**.py`, `packages/qre_diagnostics/**`,
    `packages/qre_policy/**`, `tests/unit/**`, `tests/architecture/**`, and
    narrow docs/governance notes.
- forbidden files or file families:
  - routing mutation queues, campaign mutation, source activation, strategies,
    `registry.py`, frozen contracts, live/paper/shadow/risk/broker/execution,
    automation, orchestration, generated runtime logs.
- prerequisites:
  - 014C KPI readiness is merged and fail-closed.
  - existing routing and sampling diagnostic artifacts are inspected.
- allowed changes:
  - read-only readiness derivation from existing artifacts.
  - deterministic density summaries and missing-evidence explanations.
  - tests for ready/not-ready/unknown paths.
- forbidden changes:
  - enqueueing, rerouting, sampling mutation, strategy selection, campaign
    mutation, execution behavior, or Addendum activation.
- tests required:
  - targeted routing/sampling readiness unit tests.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - ready counts are derived from existing evidence only.
  - missing evidence fails closed.
  - no runtime mutation path is introduced.
  - protected/frozen/execution paths untouched.
- merge criteria:
  - tests and CI green.
  - read-only/reporting diff only.
- done criteria:
  - PR merged by squash.
  - post-merge validation acceptable.
  - queue status can advance 014E.
- stop conditions:
  - required change mutates campaigns, routing state, sampling state,
    strategies, registry, frozen contracts, or execution paths.
- next dependency: `ADE-QRE-014E`.

### ADE-QRE-014E - Trusted-Loop Maturity Follow-up

- queue id: `ADE-QRE-014E`
- status: `blocked until ADE-QRE-014D done`
- title: Trusted-Loop Maturity Follow-up.
- purpose: update the maturity matrix/status based on 014B-D evidence while
  keeping the result docs/reporting only.
- risk class: LOW.
- target layer: governance docs and read-only reporting status.
- expected files or file families:
  - `docs/governance/**`, `docs/roadmap/*Addendum 4*` if needed only to
    preserve reference-only status, `reporting/**.py` only if a read-only
    status summary needs a narrow update, and focused tests if reporting code
    changes.
- forbidden files or file families:
  - canonical roadmap `docs/roadmap/Roadmap v6.md`, canonical policy docs,
    frozen contracts, strategy code, `registry.py`, paper/shadow/live,
    broker/risk/execution, automation, orchestration, generated artifacts.
- prerequisites:
  - 014B, 014C, and 014D merged with acceptable post-merge validation.
- allowed changes:
  - maturity matrix/status updates grounded in merged evidence.
  - operator-readable promote/defer/block status.
- forbidden changes:
  - runtime behavior, strategy synthesis, Addendum runtime activation, or
    readiness promotion without evidence.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - targeted tests only if reporting code changes.
- validation required:
  - maturity claims cite 014B-D evidence.
  - Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
  - strategy synthesis remains blocked.
- merge criteria:
  - docs/reporting-only diff.
  - CI green.
- done criteria:
  - PR merged by squash.
  - post-merge validation acceptable.
  - 014F remains deferred unless no operator gate exists.
- stop conditions:
  - maturity promotion would require operator review, HIGH/UNKNOWN authority,
    protected paths, or runtime activation.
- next dependency: `ADE-QRE-014F`.

### ADE-QRE-014F - Addendum 4 Implementation Planning Docs Only

- queue id: `ADE-QRE-014F`
- status: `deferred unless ADE-QRE-014B through ADE-QRE-014E are done and no operator gate exists`
- title: Addendum 4 Implementation Planning Docs Only.
- purpose: document future implementation planning for Addendum 4 without
  activating it.
- risk class: LOW if docs-only; escalate to operator gate if canonical roadmap,
  policy, runtime, or protected paths are needed.
- target layer: docs-only implementation planning reference.
- expected files or file families:
  - narrow docs/governance planning note, or the existing Addendum 4 reference
    document only if preserving `DEFERRED / REFERENCE-ONLY` status.
- forbidden files or file families:
  - `docs/roadmap/Roadmap v6.md` unless operator-approved, canonical policy
    docs, frozen contracts, strategy code, `registry.py`, paper/shadow/live,
    broker/risk/execution, automation, orchestration, source adapters, runtime
    behavior, generated artifacts.
- prerequisites:
  - 014B-E done.
  - no unresolved operator gate from maturity follow-up.
  - Addendum 4 remains deferred/reference-only.
- allowed changes:
  - future planning documentation, prerequisites, explicit non-activation
    language, operator-gate inventory.
- forbidden changes:
  - implementation, runtime activation, authority expansion, strategy
    synthesis, source activation, paper/shadow/live activation, registry edits.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - docs/status checks if available.
- validation required:
  - Addendum 4 runtime remains inactive.
  - no protected/frozen/execution paths touched.
  - strategy synthesis remains blocked.
- merge criteria:
  - docs-only diff.
  - CI green.
  - no operator-gated path modified.
- done criteria:
  - PR merged by squash.
  - post-merge validation acceptable.
  - no further eligible queue item remains unless operator authorizes one.
- stop conditions:
  - any implementation detail requires protected paths, runtime authority,
    canonical roadmap edits, or operator approval.
- next dependency: none.
