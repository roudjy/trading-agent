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
- status: `done`
- completion evidence: PR #321, merge SHA
  `25aaddbc48b50cac78797dac694ec7a777970606`; Fast pre-merge checks green
  on the PR; main post-merge Fast pre-merge gate, Docker build/push, and VPS
  deploy runs green for `25aaddb`; PR #322, merge SHA
  `ad0a54dc87096265511bd647e3b5cfd61837d271`, marked ADE-QRE-014B done and
  made ADE-QRE-014C the next eligible item; local validation passed
  `python -m pytest tests/unit/test_reason_record_evidence_density.py -q`,
  `python -m reporting.architecture_import_scan --format summary`, and
  `python -m reporting.reason_record_evidence_density --no-write --frozen-utc
  2026-05-24T00:00:00Z`; frozen contracts unchanged; protected/execution paths
  untouched; strategy synthesis remains blocked.
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
- implementation note:
  - 014A is done on `main`; 014B implementation shipped as read-only reporting
    sidecars, reason/evidence density inspection, focused tests, and this queue
    status update.
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
- status: `done`
- completion evidence: PR #327, merge SHA
  `9e7380451ea4866f10cba298e05e897e3a284a48`; Fast pre-merge gate
  run `26355563454`, Docker build/push run `26355688905`, and VPS
  deploy run `26355688895` completed/success; local post-merge
  targeted tests and architecture scanner passed; frozen contracts
  unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked.
- title: KPI Numeric Readiness Completion.
- purpose: make trusted-loop readiness KPIs numerically complete and
  fail-closed where values are missing, unknown, or not derivable from
  evidence.
- depends on: `ADE-QRE-014B done`.
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
- Addendum references allowed:
  - Addendum 1 diagnostic readiness labels.
  - Addendum 2 memory/retrieval coverage labels.
  - Addendum 3 data/source/identity readiness labels.
  - runtime activation is forbidden.
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
- status: `done`
- completion evidence: PR #329, merge SHA
  `586606d88e88373eb580d3b76ab48bd22c3cc3e6`; Fast pre-merge gate
  run `26356277317`, Docker build/push run `26356382172`, and VPS
  deploy run `26356382164` completed/success; local post-merge
  targeted tests and architecture scanner passed; frozen contracts
  unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked.
- title: Routing/Sampling Readiness Density.
- purpose: increase `routing_ready` and `sampling_ready` evidence density
  using existing artifacts and read-only readiness evaluation only.
- depends on: `ADE-QRE-014C done`.
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
- Addendum references allowed:
  - diagnostic-readiness reasons from Addendum 1.
  - memory/retrieval-readiness reasons from Addendum 2.
  - data/source-readiness reasons from Addendum 3.
  - runtime activation is forbidden.
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
- status: `done`
- completion evidence: PR #331, merge SHA
  `c413603a6b5f04888385b83c0d66607e932ffdfd`; Fast pre-merge gate
  run `26356885660`, Docker build/push run `26357012641`, and VPS
  deploy run `26357012575` completed/success; local post-merge
  governance lint and architecture scanner passed; Addendum 4 remained
  `DEFERRED / REFERENCE-ONLY`; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remained blocked.
- title: Trusted-Loop Maturity Follow-up.
- purpose: update the maturity matrix/status based on 014B-D evidence while
  keeping the result docs/reporting only.
- depends on: `ADE-QRE-014D done`.
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
  - 014G can become eligible for synthesis-blocker explanation work.
- stop conditions:
  - maturity promotion would require operator review, HIGH/UNKNOWN authority,
    protected paths, or runtime activation.
- next dependency: `ADE-QRE-014F`.

### ADE-QRE-014F - Addendum 4 Implementation Planning Docs Only

- queue id: `ADE-QRE-014F`
- status: `deferred unless ADE-QRE-014E done and no operator gate exists`
- title: Addendum 4 Implementation Planning Docs Only.
- purpose: document future implementation planning for Addendum 4 without
  activating it.
- depends on: `ADE-QRE-014E done`.
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
  - Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
  - no runtime implementation authorization is created.
- stop conditions:
  - any implementation detail requires protected paths, runtime authority,
    canonical roadmap edits, or operator approval.
- next dependency: none; ADE-QRE-014G is a separate read-only follow-up that
  depends on ADE-QRE-014E, not Addendum 4 planning completion.

### ADE-QRE-014G - Synthesis Blocker Explanation Density

- queue id: `ADE-QRE-014G`
- title: Synthesis Blocker Explanation Density.
- status: `done`
- completion evidence: PR #333, merge SHA
  `51c5c033e7339ebfd6bf23bd4fa8ef4894f8d63d`; Fast pre-merge gate
  run `26357671265`, Docker build/push run `26357791138`, and VPS
  deploy run `26357791137` completed/success; local post-merge targeted
  test and architecture scanner passed; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remained blocked.
- purpose: improve operator-readable explanation of why strategy synthesis
  remains blocked, using current readiness evidence only.
- depends on: `ADE-QRE-014E done`.
- risk class: LOW if read-only reporting/docs/tests only; escalate to
  UNKNOWN and stop if synthesis authority, strategy files, registry changes, or
  mutation paths are required.
- target layer: read-only reporting, governance docs, sidecar/reporting
  summaries, and tests.
- expected files or file families:
  - `reporting/**.py`, `packages/qre_diagnostics/**`,
    `packages/qre_policy/**`, `packages/qre_artifacts/**`, `tests/unit/**`,
    `tests/architecture/**`, and narrow `docs/governance/**` notes.
- forbidden files or file families:
  - `registry.py`, strategy implementations, campaign mutation paths,
    routing mutation paths, frozen contracts, frozen schemas, research output
    contracts, paper/shadow/live, broker/risk/execution, dashboard mutation
    routes, approval mutation paths, and Addendum runtime activation paths.
- allowed changes:
  - read-only reporting.
  - docs.
  - tests.
  - sidecar/reporting summaries.
  - blocker reason taxonomy using Addendum 1, Addendum 2, and Addendum 3
    reference labels only.
- forbidden changes:
  - enabling strategy synthesis.
  - executable strategy code.
  - `registry.py` edits.
  - campaign mutation.
  - routing mutation.
  - frozen contract mutation.
  - live/paper/shadow/risk/broker/execution paths.
  - Addendum runtime activation.
- tests required:
  - targeted blocker-explanation reporting tests.
  - missing-evidence fail-closed tests.
  - relevant architecture/package-boundary tests.
  - `git diff --check`.
- validation required:
  - blocker explanations are derived from current readiness evidence only.
  - missing evidence remains fail-closed.
  - strategy synthesis remains blocked.
  - protected, frozen, and execution paths are untouched.
  - `python -m reporting.architecture_import_scan --format summary` reports
    `forbidden_edge_count = 0`.
- merge criteria:
  - focused read-only reporting/docs/tests diff.
  - Fast pre-merge gate and relevant validation green.
  - no strategy, registry, frozen contract, mutation, or execution path
    changes.
- done criteria:
  - synthesis blockers are more specific and operator-readable.
  - missing evidence remains fail-closed.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014H`.

### ADE-QRE-014H - Failure-to-Action Actionability Density

- queue id: `ADE-QRE-014H`
- title: Failure-to-Action Actionability Density.
- status: `done`
- completion evidence: PR #335, merge SHA
  `1be8bbcc9b3142e7d17f6f70b10f294391bad812`; Fast pre-merge gate
  run `26368474272`, Docker build/push run `26368596439`, and VPS
  deploy run `26368596459` completed/success; local targeted
  actionability tests, architecture tests, governance lint, ruff, mypy,
  regression-fast, hook tests, `git diff --check`, and architecture
  scanner passed; frozen contracts unchanged; protected/execution paths
  untouched; strategy synthesis remained blocked.
- purpose: improve measurable density of actionable failure-to-action mappings
  from existing evidence without inventing causes.
- depends on: `ADE-QRE-014G done`.
- risk class: LOW if deterministic classification/reporting remains
  read-only; escalate to UNKNOWN and stop if routing, campaign, synthesis, or
  execution authority is required.
- target layer: deterministic reporting, diagnostics summaries,
  sidecar/reporting artifacts, docs, and tests.
- expected files or file families:
  - `reporting/**.py`, `packages/qre_diagnostics/**`,
    `packages/qre_artifacts/**`, `tests/unit/**`, `tests/architecture/**`,
    and narrow `docs/governance/**` notes.
- forbidden files or file families:
  - strategy generation files, campaign mutation paths, routing mutation paths,
    live/paper/shadow/risk/broker/execution, frozen contracts, hidden ML/RL
    selector surfaces, stochastic mutation paths, dashboard mutation routes,
    and approval mutation paths.
- allowed changes:
  - deterministic classification/reporting.
  - docs.
  - tests.
  - sidecar/reporting summaries.
  - actionability metrics.
- forbidden changes:
  - strategy generation.
  - campaign mutation.
  - routing mutation.
  - live/paper/shadow/risk/broker/execution paths.
  - hidden ML/RL selector.
  - stochastic mutation.
  - frozen contract mutation.
- tests required:
  - targeted actionability metric tests.
  - no-invented-cause tests for missing/thin evidence.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - actionability density is deterministic and evidence-backed.
  - non-actionable failures remain explicit.
  - no causes are invented without evidence.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused read-only reporting/docs/tests diff.
  - tests and CI green.
  - no mutation, strategy, frozen contract, or execution path changes.
- done criteria:
  - actionability density is measured.
  - non-actionable failures remain explicit.
  - no causes are invented without evidence.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014I`.

### ADE-QRE-014I - Operator Decision Surface Readiness

- queue id: `ADE-QRE-014I`
- title: Operator Decision Surface Readiness.
- status: `done`
- completion evidence: PR #337, merge SHA
  `010d2ca652141bb4d304aad59820d51fdc5435ed`; post-merge Fast
  pre-merge gate run `26371365964`, Docker build/push run
  `26371490198`, and VPS deploy run `26371490206` completed/success;
  local targeted decision-surface tests, queue lifecycle tests,
  trusted-loop materialization tests, architecture tests, governance lint,
  ruff, mypy, regression-fast, hook tests, `git diff --check`, and
  architecture scanner passed; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remained blocked;
  Addendum runtime remained inactive.
- purpose: make operator-facing decision outputs clearer: why next, why
  blocked, why deferred, and why no synthesis.
- depends on: `ADE-QRE-014H done`.
- risk class: LOW if confined to read-only reporting/docs/tests and existing
  safe reporting surfaces; escalate to UNKNOWN and stop if mutation routes or
  approval behavior are required.
- target layer: operator-facing read-only reporting, governance docs, tests,
  and bounded existing safe reporting surfaces if already present.
- expected files or file families:
  - `reporting/**.py`, existing read-only control-plane adapter/reporting
    surfaces if already present, `packages/qre_diagnostics/**`,
    `packages/qre_policy/**`, `tests/unit/**`, `tests/architecture/**`, and
    narrow `docs/governance/**` notes.
- forbidden files or file families:
  - dashboard mutation routes, approval mutation paths, frontend business
    logic, strategy synthesis enablement paths, frozen contracts,
    live/paper/shadow/risk/broker/execution, registry, strategy
    implementations, campaign mutation paths, and routing mutation paths.
- allowed changes:
  - read-only reporting.
  - docs.
  - tests.
  - bounded existing safe reporting surfaces if already present.
- forbidden changes:
  - dashboard mutation routes.
  - approval mutation.
  - frontend business logic.
  - live/paper/shadow/risk/broker/execution paths.
  - strategy synthesis enablement.
  - frozen contract mutation.
- tests required:
  - targeted decision-surface reporting tests.
  - no-mutation-route source checks where applicable.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - operator-readable outputs explain next, blocked, deferred, and no-synthesis
    states.
  - no mutation routes are added.
  - protected, frozen, and execution paths are untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused read-only reporting/docs/tests diff.
  - tests and CI green.
  - no dashboard mutation, approval mutation, frontend business logic, frozen
    contract, or execution path changes.
- done criteria:
  - operator can read next/blocked/deferred/no-synthesis reasons.
  - no mutation routes added.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014J`.

### ADE-QRE-014J - Research Memory Retrieval Coverage

- queue id: `ADE-QRE-014J`
- title: Research Memory Retrieval Coverage.
- status: `done`
- completion evidence: PR #350, merge SHA
  `ec9509e17f87bf2fe377144e1d8fde6ee7436e1b`; post-merge Fast
  pre-merge gate run `26395054419`, Docker build/push run
  `26395274477`, and VPS deploy run `26395274476` completed/success;
  targeted retrieval coverage and research-memory tests, architecture tests,
  architecture scanner, ruff, mypy, regression-fast, hook tests, governance
  lint, `git diff --check`, and PR Fast pre-merge gate passed; frozen
  contracts unchanged; protected/execution paths untouched; retrieval remains
  context only, not authority; no vector database, hidden ML, strategy
  synthesis, Addendum runtime activation, routing/campaign mutation, dashboard
  mutation, approval mutation, paper/shadow/live/risk/broker/execution, or
  dependency PR changes.
- purpose: measure whether prior trusted-loop reasons, failures, blockers, and
  actions are retrievable and linked enough for later routing/sampling
  calibration.
- depends on: `ADE-QRE-014I done`.
- risk class: LOW if retrieval remains deterministic, local, and no-authority;
  escalate to UNKNOWN and stop if a vector database, hidden ML, or retrieval
  authority is required.
- target layer: deterministic retrieval coverage reporting, docs, tests,
  sidecar/reporting artifacts, and no-authority retrieval summaries.
- expected files or file families:
  - `packages/qre_research/**`, `packages/qre_artifacts/**`,
    `packages/qre_diagnostics/**`, `reporting/**.py`, `tests/unit/**`,
    `tests/architecture/**`, and narrow `docs/governance/**` notes.
- forbidden files or file families:
  - vector database integration, hidden ML or embedding/reranker authority,
    strategy synthesis, runtime Addendum activation paths, execution paths,
    frozen contracts, campaign mutation paths, routing mutation paths,
    approval mutation paths, and dashboard mutation routes.
- Addendum references allowed:
  - Addendum 2 may be used as the primary reference taxonomy only.
  - retrieval remains context, not authority.
  - runtime Addendum activation is forbidden.
- allowed changes:
  - deterministic retrieval coverage reporting.
  - docs.
  - tests.
  - sidecar/reporting artifacts.
  - no-authority retrieval summaries.
- forbidden changes:
  - vector database.
  - hidden ML.
  - retrieval as authority.
  - strategy synthesis.
  - runtime Addendum activation.
  - execution paths.
  - frozen contract mutation.
- tests required:
  - targeted retrieval coverage tests.
  - missing-link explicitness tests.
  - no-authority/no-network tests where applicable.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - retrieval coverage is measured deterministically.
  - missing retrieval links are explicit.
  - retrieval remains context, not authority.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused deterministic reporting/docs/tests diff.
  - tests and CI green.
  - no vector database, hidden ML, authority expansion, strategy, frozen
    contract, or execution path changes.
- done criteria:
  - retrieval coverage is measured.
  - missing retrieval links are explicit.
  - retrieval remains context, not authority.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014K`.

### ADE-QRE-014K - Trusted Loop Regression Fixtures

- queue id: `ADE-QRE-014K`
- title: Trusted Loop Regression Fixtures.
- status: `done`
- completion evidence: PR #352, merge SHA
  `5dd223249f8b5c9251c27e70a43a0521a966de54`; post-merge Fast
  pre-merge gate run `26407877873`, Docker build/push run `26408118046`,
  and VPS deploy run `26408118045` completed/success; fixture-backed tests
  cover complete, thin, missing, contradictory, blocked, and non-actionable
  trusted-loop evidence cases; targeted trusted-loop tests, architecture
  tests, architecture scanner, ruff, mypy, regression-fast, hook tests,
  governance lint, `git diff --check`, and PR Fast pre-merge gate passed;
  frozen contracts unchanged; protected/execution paths untouched; no
  production behavior, strategy, registry, research output, Addendum runtime,
  routing/campaign mutation, dashboard mutation, approval mutation,
  paper/shadow/live/risk/broker/execution, or dependency PR changes.
- purpose: add stable regression fixtures for complete, thin, missing,
  contradictory, blocked, and non-actionable trusted-loop evidence cases.
- depends on: `ADE-QRE-014J done`.
- risk class: LOW for tests/fixtures/deterministic reporting checks; escalate
  to UNKNOWN and stop if production behavior, mutation paths, execution paths,
  or frozen contracts are required.
- target layer: tests, fixtures, deterministic reporting checks, and minimal
  production changes only if directly required for testable reporting
  correctness.
- expected files or file families:
  - `tests/unit/**`, `tests/regression/**` only if existing patterns support
    it, `tests/fixtures/**` or existing fixture directories, `reporting/**.py`
    only for directly required reporting correctness, and narrow
    `docs/governance/**` notes.
- forbidden files or file families:
  - strategy generation, campaign mutation paths, routing mutation paths,
    runtime Addendum activation paths, execution paths, frozen contracts,
    registry, strategy implementations, live/paper/shadow/risk/broker, and
    generated runtime artifacts.
- allowed changes:
  - tests.
  - fixtures.
  - deterministic reporting checks.
  - minimal production changes only if directly required for testable reporting
    correctness.
- forbidden changes:
  - strategy generation.
  - campaign/routing mutation.
  - runtime Addendum activation.
  - execution paths.
  - frozen contract mutation.
- tests required:
  - fixture-backed tests covering complete, thin, missing, contradictory,
    blocked, and non-actionable evidence.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - fixtures are deterministic and stable.
  - fixture cases do not mutate research outputs or frozen contracts.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - tests/fixtures/reporting-correctness diff only.
  - tests and CI green.
  - no strategy, mutation, frozen contract, or execution path changes.
- done criteria:
  - fixtures cover complete/thin/missing/contradictory/blocked/non-actionable
    evidence.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014L`.

### ADE-QRE-014L - Data/Source Readiness Blocker Coverage

- queue id: `ADE-QRE-014L`
- title: Data/Source Readiness Blocker Coverage.
- status: `done`
- completion evidence: PR #355, merge SHA
  `c1aac7cda8874905d010c19dd635cf496a1e7b13`; post-merge Fast
  pre-merge gate run `26439212100`, Docker build/push run `26439500230`,
  and VPS deploy run `26439500103` completed/success; targeted
  data/source/identity blocker tests, fail-closed missing/unknown evidence
  tests, architecture tests, architecture scanner, ruff, mypy,
  regression-fast, hook tests, governance lint, `git diff --check`, and PR
  Fast pre-merge gate passed; frozen contracts unchanged;
  protected/execution paths untouched; no source runtime, external adapter,
  datafeed, data lake rollout, source-quality alpha/promotion authority,
  Addendum 3 runtime activation, strategy, registry, research output,
  campaign/routing mutation, dashboard mutation, approval mutation,
  paper/shadow/live/risk/broker/execution, or dependency PR changes.
- purpose: improve read-only coverage of data/source/identity readiness
  blockers using Addendum 3 as reference taxonomy only.
- depends on: `ADE-QRE-014K done`.
- risk class: LOW if confined to readiness blocker labels, docs, tests, and
  reporting summaries; escalate to UNKNOWN and stop if source runtime,
  external adapters, data lake rollout, promotion authority, or execution paths
  are required.
- target layer: readiness blocker labels, docs, tests, reporting/sidecar
  summaries.
- expected files or file families:
  - `packages/qre_data/**`, `packages/qre_policy/**`,
    `packages/qre_diagnostics/**`, `reporting/**.py`, `tests/unit/**`,
    `tests/architecture/**`, and narrow `docs/governance/**` notes.
- forbidden files or file families:
  - new external source adapters, new datafeeds, Parquet/DuckDB data lake
    rollout paths, source-quality alpha/promotion authority paths, runtime
    Addendum 3 activation paths, frozen contracts, execution paths,
    live/paper/shadow/risk/broker, campaign mutation paths, and routing
    mutation paths.
- Addendum references allowed:
  - Addendum 3 may be used as a reference taxonomy only.
  - runtime Addendum 3 activation is forbidden.
- allowed changes:
  - readiness blocker labels.
  - docs.
  - tests.
  - reporting/sidecar summaries.
- forbidden changes:
  - new external source adapters.
  - new datafeeds.
  - Parquet/DuckDB data lake rollout.
  - source quality as alpha.
  - source quality as promotion authority.
  - runtime Addendum 3 activation.
  - frozen contract mutation.
  - execution paths.
- tests required:
  - targeted data/source/identity blocker tests.
  - fail-closed missing/unknown evidence tests.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - data/source/identity blockers are explicit and fail-closed.
  - no new source runtime is activated.
  - protected, frozen, and execution paths are untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused readiness reporting/docs/tests diff.
  - tests and CI green.
  - no source runtime, external adapter, frozen contract, mutation, or
    execution path changes.
- done criteria:
  - data/source/identity readiness blockers are explicit and fail-closed.
  - no new source runtime is activated.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014M`.

### ADE-QRE-014M - Diagnostic Readiness Blocker Coverage

- queue id: `ADE-QRE-014M`
- title: Diagnostic Readiness Blocker Coverage.
- status: `done`
- completion evidence: PR #357, merge SHA
  `d459829fa988a47a19e6531814b68c05cfc8ff3a`; local `main` git log
  confirmed `d459829 test: add diagnostic readiness blocker coverage (#357)`.
  Targeted diagnostic readiness blocker tests passed; architecture scanner
  passed with `forbidden_edge_count = 0`; `git diff --check` validation
  passed; CI/checks green; main Fast pre-merge gate green; Docker build/push
  and VPS deploy green; frozen contracts unchanged; protected/execution paths
  untouched; strategy synthesis remained blocked; Addendum runtime remained
  inactive.
- purpose: improve read-only coverage of missing diagnostic/quorum/null-model
  blockers using Addendum 1 as reference taxonomy only.
- depends on: `ADE-QRE-014L done`.
- risk class: LOW if confined to diagnostic blocker labels, docs, tests, and
  reporting summaries; escalate to UNKNOWN and stop if diagnostics become a
  runtime layer, synthesis authority, routing/sampling controller, or
  execution path.
- target layer: diagnostic blocker labels, docs, tests, reporting/sidecar
  summaries.
- expected files or file families:
  - `packages/qre_diagnostics/**`, `packages/qre_policy/**`,
    `reporting/**.py`, `tests/unit/**`, `tests/architecture/**`, and narrow
    `docs/governance/**` notes.
- forbidden files or file families:
  - full Behavior Diagnostics Library implementation, diagnostics strategy-seed
    generation, routing/sampling runtime control paths, synthesis authority
    paths, execution paths, frozen contracts, live/paper/shadow/risk/broker,
    campaign mutation paths, and routing mutation paths.
- Addendum references allowed:
  - Addendum 1 may be used as a reference taxonomy only.
  - diagnostic runtime layer activation is forbidden.
- allowed changes:
  - diagnostic blocker labels.
  - docs.
  - tests.
  - reporting/sidecar summaries.
- forbidden changes:
  - full Behavior Diagnostics Library implementation.
  - diagnostics auto-generating strategy seeds.
  - diagnostics controlling routing/sampling runtime behavior.
  - diagnostics authorizing synthesis.
  - execution paths.
  - frozen contract mutation.
- tests required:
  - targeted diagnostic blocker tests.
  - fail-closed missing diagnostic/quorum/null-model evidence tests.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - diagnostic readiness blockers are explicit and fail-closed.
  - no diagnostic runtime layer is activated.
  - protected, frozen, and execution paths are untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused readiness reporting/docs/tests diff.
  - tests and CI green.
  - no diagnostics runtime, strategy seed, synthesis authority, frozen
    contract, mutation, or execution path changes.
- done criteria:
  - diagnostic readiness blockers are explicit and fail-closed.
  - no diagnostic runtime layer is activated.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014N`.

### ADE-QRE-014N - Queue/Status Self-Audit Coverage

- queue id: `ADE-QRE-014N`
- title: Queue/Status Self-Audit Coverage.
- status: `done`
- completion evidence: PR #360, merge SHA
  `4e3e48e0ce37029cfc5eeef04b88f22a97f24f8e`; Fast pre-merge gate,
  Docker build/push, and VPS deploy post-merge gates completed/success;
  targeted queue/status self-audit tests, queue lifecycle tests, architecture
  tests, architecture scanner, ruff, mypy, governance lint, and
  `git diff --check` passed; frozen contracts unchanged; protected/execution
  paths untouched; strategy synthesis remained blocked; Addendum runtime
  remained inactive.
- purpose: improve read-only self-audit of queue statuses, dependencies, done
  evidence, and blocked/deferred reasons.
- depends on: `ADE-QRE-014M done`.
- risk class: LOW if read-only queue/status validation only; escalate to
  UNKNOWN and stop if approval mutation, autonomous authority expansion,
  dashboard mutation, execution paths, or frozen contracts are required.
- target layer: docs, tests, read-only queue/status validation, and reporting
  summaries.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` for read-only status validation,
    `tests/unit/**`, `tests/architecture/**`, and existing queue/status
    validation docs.
- forbidden files or file families:
  - approval mutation paths, autonomous authority expansion paths, dashboard
    mutation routes, execution paths, frozen contracts, live/paper/shadow/risk/
    broker, strategy synthesis enablement, campaign mutation paths, routing
    mutation paths, and Addendum runtime activation paths.
- allowed changes:
  - docs.
  - tests.
  - read-only queue/status validation.
  - reporting summaries.
- forbidden changes:
  - approval mutation.
  - autonomous authority expansion.
  - dashboard mutation routes.
  - execution paths.
  - frozen contract mutation.
- tests required:
  - targeted queue/status consistency tests.
  - missing done-evidence tests.
  - blocked/deferred reason explicitness tests.
  - architecture scanner summary.
  - `git diff --check`.
- validation required:
  - queue status consistency is checkable.
  - missing done evidence is flagged.
  - blocked/deferred reasons are explicit.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused read-only docs/reporting/tests diff.
  - tests and CI green.
  - no approval mutation, authority expansion, dashboard mutation, frozen
    contract, or execution path changes.
- done criteria:
  - queue status consistency is checkable.
  - missing done evidence is flagged.
  - blocked/deferred reasons are explicit.
  - tests/validation green.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-014O`.

### ADE-QRE-014O - Final Trusted-Loop Queue Readiness Review

- queue id: `ADE-QRE-014O`
- title: Final Trusted-Loop Queue Readiness Review.
- status: `done`
- completion evidence: PR #362, merge SHA
  `8f614aed7c3502695d998a577ca9b826e5e4c375`; final read-only review
  selected exactly one allowed next direction, `continue trusted-loop maturity
  sprint`; post-merge Fast pre-merge gate run `26510874612`, Docker
  build/push run `26511164074`, and VPS deploy run `26511164073`
  completed/success; targeted queue lifecycle and queue self-audit tests,
  architecture scanner, `git diff --check`, and staged diff check passed;
  frozen contracts unchanged; protected/execution paths untouched; strategy
  synthesis remained blocked; Addendum runtime remained inactive.
- purpose: produce a final read-only review of ADE-QRE-014 maturity and
  recommend exactly one next queue direction.
- depends on: `ADE-QRE-014N done`.
- risk class: LOW if docs/reporting review only; escalate to UNKNOWN and stop
  if runtime activation, synthesis enablement, execution paths, or frozen
  contract mutation are required.
- target layer: read-only maturity review, governance docs, reporting summary,
  and applicable tests/validation.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only review
    summaries, `tests/unit/**` only if reporting code changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - Addendum 4 runtime activation paths, strategy synthesis enablement,
    shadow/paper/live, broker/risk/execution, frozen contracts, registry,
    strategy implementations, campaign mutation paths, routing mutation paths,
    approval mutation paths, and dashboard mutation routes.
- allowed next directions:
  - continue trusted-loop maturity sprint.
  - return to QRE Feature Build Track.
  - operator review required.
  - no eligible work remains.
- allowed changes:
  - read-only evidence-backed maturity review.
  - docs.
  - reporting summaries.
  - tests where applicable.
- forbidden changes:
  - activating Addendum 4 runtime.
  - enabling strategy synthesis.
  - starting shadow/paper/live.
  - execution paths.
  - frozen contract mutation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - targeted tests if reporting code changes.
- validation required:
  - final recommendation selects exactly one allowed next direction.
  - recommendation is evidence-backed.
  - unsupported trust claims are avoided.
  - protected, frozen, and execution paths are untouched.
  - Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
- merge criteria:
  - focused read-only docs/reporting/tests diff.
  - tests and CI green where applicable.
  - no synthesis, Addendum runtime, shadow/paper/live, execution, frozen
    contract, approval mutation, or dashboard mutation changes.
- done criteria:
  - final recommendation is evidence-backed.
  - unsupported trust claims are avoided.
  - tests/validation green where applicable.
  - PR merged.
  - queue status updated to done.
- stop conditions:
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015A`.

## ADE-QRE-015 - Post-Trusted-Loop-Maturity Transition Preparation Queue

Purpose: prepare the post-trusted-loop-maturity transition after
`ADE-QRE-014O`, so a later run can decide safely whether to continue the
trusted-loop maturity sprint, return to the QRE Feature Build Track, require
operator review, or stop because no eligible work remains.

Scope constraints:

- queue planning only until each item becomes eligible through its dependency.
- `ADE-QRE-015A` is ready after `ADE-QRE-014O done`.
- strategy synthesis remains blocked.
- Addendum 1, 2, 3, and 4 remain reference-only and not runtime activated.
- Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
- shadow, paper, live, broker, risk, and execution paths remain inactive.
- no dashboard mutation routes or approval mutation behavior may be added.

### ADE-QRE-015A - Post-014 Final Evidence Inventory

- queue id: `ADE-QRE-015A`
- title: Post-014 Final Evidence Inventory.
- status: `done`
- completion evidence: PR #364, merge SHA
  `5469d041e1e1f09648a125b681a73732505e1ef7`; evidence inventory added in
  `docs/governance/ade_qre_015a_post_014_final_evidence_inventory.md`;
  post-merge Fast pre-merge gate run `26532026262`, Docker build/push run
  `26532342682`, and VPS deploy run `26532342816` completed/success; local
  `git diff --check`, architecture scanner, and governance lint passed; frozen
  contracts unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked; Addendum runtime remained inactive.
- purpose: inventory all evidence produced by `ADE-QRE-014B` through
  `ADE-QRE-014O` and identify what is still scaffold, working capability, or
  operator-trusted capability.
- depends on: `ADE-QRE-014O done`.
- risk class: LOW.
- target layer: governance docs, read-only reporting, and tests if needed.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only evidence
    inventory or summaries, `tests/unit/**` only if reporting code changes,
    and `tests/architecture/**` where relevant.
- forbidden files or file families:
  - strategy synthesis enablement paths, runtime Addendum activation paths,
    strategy code, `registry.py`, campaign/routing mutation paths,
    live/paper/shadow/risk/broker/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - docs.
  - read-only evidence inventory.
  - reporting summaries.
  - tests if reporting code changes.
- forbidden changes:
  - strategy synthesis enablement.
  - runtime Addendum activation.
  - strategy code.
  - `registry.py`.
  - campaign/routing mutation.
  - live/paper/shadow/risk/broker/execution paths.
  - frozen contract mutation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - targeted tests if reporting code changes.
- validation required:
  - evidence inventory is deterministic and read-only.
  - unsupported trust claims are avoided.
  - gaps are explicit.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs/read-only reporting/tests diff.
  - tests and CI green where applicable.
  - no synthesis, Addendum runtime, strategy, registry, mutation, frozen
    contract, research output, or execution path changes.
- done criteria:
  - evidence inventory exists.
  - unsupported trust claims are avoided.
  - gaps are explicit.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-014O` is not done.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015B`.

### ADE-QRE-015B - Trusted-Loop Gap Prioritization

- queue id: `ADE-QRE-015B`
- title: Trusted-Loop Gap Prioritization.
- status: `done`
- completion evidence: PR #366, merge SHA
  `eca3666092d0cbe9681115c9180d91e6a0a8d8c6`; deterministic trusted-loop
  gap prioritization added in
  `docs/governance/ade_qre_015b_trusted_loop_gap_prioritization.md`;
  post-merge Fast pre-merge gate run `26533816388`, Docker build/push run
  `26534136899`, and VPS deploy run `26534140225` completed/success; local
  `git diff --check`, architecture scanner, and governance lint passed; frozen
  contracts unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked; Addendum runtime remained inactive.
- purpose: rank remaining trusted-loop gaps by operator value, safety,
  evidence impact, and implementation risk.
- depends on: `ADE-QRE-015A done`.
- risk class: LOW.
- target layer: governance docs and read-only scoring/reporting.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for deterministic read-only
    gap scoring or summaries, `tests/unit/**` only if scoring/reporting code
    changes, and `tests/architecture/**` where relevant.
- forbidden files or file families:
  - roadmap activation/mutation paths, strategy synthesis enablement paths,
    runtime behavior mutation paths, runtime Addendum activation paths,
    live/paper/shadow/risk/broker/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - deterministic gap prioritization.
  - docs.
  - read-only reporting.
  - tests if scoring/reporting code changes.
- forbidden changes:
  - automatic roadmap activation.
  - strategy synthesis.
  - runtime behavior mutation.
  - Addendum runtime activation.
  - execution paths.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - targeted scoring/reporting tests if code changes.
- validation required:
  - gaps are ranked deterministically.
  - ranking is evidence-backed.
  - operator can see why a gap is high/medium/low priority.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs/read-only scoring/reporting/tests diff.
  - tests and CI green where applicable.
  - no automatic activation, synthesis, runtime mutation, Addendum runtime,
    frozen contract, research output, or execution path changes.
- done criteria:
  - gaps are ranked deterministically.
  - ranking is evidence-backed.
  - operator can see why a gap is high/medium/low priority.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015A` is not done.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015C`.

### ADE-QRE-015C - QRE Feature Track Return Readiness Check

- queue id: `ADE-QRE-015C`
- title: QRE Feature Track Return Readiness Check.
- status: `done`
- completion evidence: PR #368, merge SHA
  `69df8aaaea07393f5a13c89e61c5b40910be3fc9`; read-only readiness check added
  in `docs/governance/ade_qre_015c_qre_feature_track_return_readiness_check.md`
  with explicit recommendation `continue_trusted_loop_maturity`; post-merge
  Fast pre-merge gate run `26535691624`, Docker build/push run `26535984857`,
  and VPS deploy run `26535985000` completed/success; local `git diff --check`,
  architecture scanner, and governance lint passed; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remained blocked;
  Addendum runtime remained inactive.
- purpose: determine whether the project is ready to return to the QRE
  Feature Build Track after the trusted-loop sprint.
- depends on: `ADE-QRE-015B done`.
- risk class: LOW.
- target layer: governance docs and read-only readiness report.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only readiness
    reporting if needed, `tests/unit/**` only if reporting code changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - Roadmap v6 v3.15.16 implementation paths, product roadmap mutation paths,
    strategy synthesis enablement paths, paper/shadow/live paths,
    broker/risk/execution paths, frozen contracts, dashboard mutation routes,
    approval mutation paths, `registry.py`, strategy implementations,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - docs.
  - read-only readiness checklist.
  - evidence-backed recommendation.
- forbidden changes:
  - starting v3.15.16 implementation.
  - changing product roadmap.
  - strategy synthesis.
  - paper/shadow/live.
  - execution paths.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - targeted tests if readiness reporting code changes.
- validation required:
  - readiness recommendation is explicit.
  - allowed outputs are exactly `return_to_qre_feature_track`,
    `continue_trusted_loop_maturity`, `operator_review_required`, and
    `no_eligible_work_remains`.
  - recommendation is evidence-backed.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs/read-only readiness diff.
  - tests and CI green where applicable.
  - no roadmap mutation, v3.15.16 implementation, synthesis, paper/shadow/live,
    frozen contract, research output, or execution path changes.
- done criteria:
  - readiness recommendation is explicit.
  - allowed outputs are exactly:
    1. `return_to_qre_feature_track`.
    2. `continue_trusted_loop_maturity`.
    3. `operator_review_required`.
    4. `no_eligible_work_remains`.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015B` is not done.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - product roadmap mutation required.
  - v3.15.16 implementation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015D`.

### ADE-QRE-015D - v3.15.16 Intelligent Routing Re-entry Planning Docs Only

- queue id: `ADE-QRE-015D`
- title: v3.15.16 Intelligent Routing Re-entry Planning Docs Only.
- status: `blocked until ADE-QRE-015C done and recommendation is return_to_qre_feature_track`
- purpose: prepare a docs-only re-entry plan for Roadmap v6 v3.15.16
  Intelligent Routing Layer without implementing it.
- depends on: `ADE-QRE-015C done`.
- risk class: LOW if docs-only; operator_review if canonical roadmap edits
  are needed.
- target layer: `docs/governance` planning.
- expected files or file families:
  - `docs/governance/**`, and narrow planning prompts or governance notes only.
- forbidden files or file families:
  - routing implementation paths, campaign mutation paths, strategy code,
    `registry.py`, shadow/paper/live paths, broker/risk/execution paths,
    runtime Addendum activation paths, frozen contracts, dashboard mutation
    routes, approval mutation paths, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only phase plan.
  - scope boundaries.
  - risk map.
  - validation expectations.
  - prompt draft for later implementation.
- forbidden changes:
  - implementation of routing.
  - campaign mutation.
  - strategy code.
  - `registry.py`.
  - shadow/paper/live.
  - execution paths.
  - Addendum runtime activation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - re-entry plan remains docs-only.
  - v3.15.16 implementation has not started.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs-only planning diff.
  - tests and CI green where applicable.
  - no routing implementation, campaign mutation, strategy, registry,
    Addendum runtime, frozen contract, research output, or execution path
    changes.
- done criteria:
  - v3.15.16 re-entry plan exists.
  - no implementation started.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015C` is not done.
  - `ADE-QRE-015C` recommendation is not `return_to_qre_feature_track`.
  - canonical roadmap edits are required without operator review.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - routing implementation required.
  - campaign mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015E`.

### ADE-QRE-015E - Trusted-Loop Continuation Planning Docs Only

- queue id: `ADE-QRE-015E`
- title: Trusted-Loop Continuation Planning Docs Only.
- status: `done`
- completion evidence: PR #370, merge SHA
  `31093867c481513cf90b81f40d38fe7685bcc83b`; docs-only trusted-loop
  continuation plan added in
  `docs/governance/ade_qre_015e_trusted_loop_continuation_plan.md`;
  `ADE-QRE-015C` recommendation `continue_trusted_loop_maturity` preserved;
  `ADE-QRE-015D`, `ADE-QRE-015F`, and `ADE-QRE-015G` remain blocked;
  checks green; post-merge Fast, Docker build/push, and VPS deploy gates green;
  frozen contracts unchanged; protected/execution paths untouched.
- purpose: prepare a docs-only next trusted-loop maturity sprint if returning
  to QRE Feature Track is not yet safe.
- depends on: `ADE-QRE-015C done`.
- risk class: LOW.
- target layer: governance docs.
- expected files or file families:
  - `docs/governance/**`, and narrow planning prompts or governance notes only.
- forbidden files or file families:
  - runtime behavior paths, strategy synthesis enablement paths, runtime
    Addendum activation paths, live/paper/shadow/risk/broker/execution paths,
    frozen contracts, dashboard mutation routes, approval mutation paths,
    `registry.py`, strategy implementations, `research/research_latest.json`,
    and `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only planning.
  - bounded next sprint candidates.
  - operator-review checklist.
- forbidden changes:
  - runtime changes.
  - strategy synthesis.
  - Addendum runtime activation.
  - execution paths.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - continuation plan remains docs-only.
  - items are bounded and dependency-gated.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs-only planning diff.
  - tests and CI green where applicable.
  - no runtime, synthesis, Addendum runtime, frozen contract, research output,
    or execution path changes.
- done criteria:
  - continuation plan exists.
  - items are bounded and dependency-gated.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015C` is not done.
  - `ADE-QRE-015C` recommendation is not `continue_trusted_loop_maturity`.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime changes required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015H`.

### ADE-QRE-015F - Operator Review Packet

- queue id: `ADE-QRE-015F`
- title: Operator Review Packet.
- status: `blocked until ADE-QRE-015C done and recommendation is operator_review_required`
- purpose: produce a concise operator review packet when the next direction
  cannot be selected safely by evidence alone.
- depends on: `ADE-QRE-015C done`.
- risk class: LOW.
- target layer: `docs/governance`.
- expected files or file families:
  - `docs/governance/**`, and narrow operator-review planning notes only.
- forbidden files or file families:
  - option implementation paths, approval mutation paths, dashboard mutation
    routes, runtime behavior paths, strategy synthesis enablement paths,
    runtime Addendum activation paths, live/paper/shadow/risk/broker/execution
    paths, frozen contracts, `registry.py`, strategy implementations,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only review packet.
  - explicit decision options.
  - evidence links.
  - risks and tradeoffs.
- forbidden changes:
  - implementing any reviewed option.
  - automatic approval.
  - approval mutation.
  - dashboard mutation routes.
  - runtime changes.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - operator decision options are clear.
  - no option is auto-executed.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs-only review-packet diff.
  - tests and CI green where applicable.
  - no option implementation, approval mutation, dashboard mutation, runtime,
    frozen contract, research output, or execution path changes.
- done criteria:
  - operator decision options are clear.
  - no option is auto-executed.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015C` is not done.
  - `ADE-QRE-015C` recommendation is not `operator_review_required`.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - implementation of any reviewed option required.
  - approval mutation required.
  - dashboard mutation route required.
  - live/paper/shadow/risk/broker/execution paths required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015G`.

### ADE-QRE-015G - No-Eligible-Work Closure Note

- queue id: `ADE-QRE-015G`
- title: No-Eligible-Work Closure Note.
- status: `blocked until ADE-QRE-015C done and recommendation is no_eligible_work_remains`
- purpose: document closure if no safe eligible work remains after
  `ADE-QRE-014O`.
- depends on: `ADE-QRE-015C done`.
- risk class: LOW.
- target layer: `docs/governance`.
- expected files or file families:
  - `docs/governance/**`, and narrow closure/status notes only.
- forbidden files or file families:
  - new-scope implementation paths, runtime behavior paths, strategy synthesis
    enablement paths, runtime Addendum activation paths,
    live/paper/shadow/risk/broker/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only closure note.
  - final status matrix.
  - next operator action.
- forbidden changes:
  - inventing new scope.
  - runtime changes.
  - strategy synthesis.
  - execution paths.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - closure note remains docs-only.
  - next operator action is explicit.
  - protected, frozen, and execution paths are untouched.
- merge criteria:
  - focused docs-only closure diff.
  - tests and CI green where applicable.
  - no invented scope, runtime, synthesis, frozen contract, research output, or
    execution path changes.
- done criteria:
  - closure note exists.
  - next operator action is explicit.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015C` is not done.
  - `ADE-QRE-015C` recommendation is not `no_eligible_work_remains`.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - invented new scope required.
  - runtime changes required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-015H`.

### ADE-QRE-015H - Queue Direction Finalization

- queue id: `ADE-QRE-015H`
- title: Queue Direction Finalization.
- status: `done`
- completion evidence: PR #372, merge SHA
  `be83e53fd1e577cd074895207d3f2879d8b5a445`; docs-only queue direction
  finalization added in
  `docs/governance/ade_qre_015h_queue_direction_finalization.md`; exactly one
  next direction selected, `start next trusted-loop maturity sprint`; selected
  direction not implemented; checks green; post-merge Fast, Docker build/push,
  and VPS deploy gates green; frozen contracts unchanged;
  protected/execution paths untouched.
- purpose: finalize exactly one next queue direction after the `ADE-QRE-015`
  branching decision.
- depends on: `ADE-QRE-015E done`.
- risk class: LOW.
- target layer: `docs/governance`.
- expected files or file families:
  - `docs/governance/**`, and narrow queue-direction finalization notes only.
- forbidden files or file families:
  - strategy synthesis enablement paths, runtime Addendum activation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, campaign mutation paths, routing mutation paths,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed next directions:
  1. start QRE Feature Build Track v3.15.16 implementation prompt.
  2. start next trusted-loop maturity sprint.
  3. wait for operator decision.
  4. stop because no eligible work remains.
- allowed changes:
  - docs-only queue direction finalization.
  - evidence-backed selection of exactly one allowed next direction.
  - blocked/deferred notes for unsupported directions.
- forbidden changes:
  - enabling strategy synthesis.
  - activating Addendum runtime.
  - starting shadow/paper/live.
  - touching broker/risk/execution.
  - frozen contract mutation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - exactly one next direction is selected.
  - unsupported directions remain blocked/deferred.
  - protected, frozen, and execution paths are untouched.
  - Addendum runtime remains inactive.
- merge criteria:
  - focused docs-only finalization diff.
  - tests and CI green where applicable.
  - no synthesis, Addendum runtime, shadow/paper/live, broker/risk/execution,
    frozen contract, research output, campaign mutation, or routing mutation
    changes.
- done criteria:
  - exactly one next direction is selected.
  - unsupported directions remain blocked/deferred.
  - PR merged and validated.
- stop conditions:
  - none of `ADE-QRE-015D`, `ADE-QRE-015E`, `ADE-QRE-015F`, or
    `ADE-QRE-015G` is done.
  - more than one branch path is selected.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - shadow/paper/live required.
  - broker/risk/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: none for this autonomous run; stop after `ADE-QRE-015H`.

## ADE-QRE-016 - Next Trusted-Loop Maturity Sprint

This sprint continues the trusted-loop maturity direction selected by
`ADE-QRE-015C` and finalized by `ADE-QRE-015H`. It is derived only from the
`ADE-QRE-015A` evidence inventory, `ADE-QRE-015B` gap prioritization,
`ADE-QRE-015C` readiness check, `ADE-QRE-015E` continuation plan, and
`ADE-QRE-015H` direction finalization.

The sprint is queue planning only until each dependency-gated item is executed
in a later PR. It does not start QRE Feature Build Track implementation, does
not implement v3.15.16 Intelligent Routing, does not enable strategy synthesis,
does not activate Addendum runtime behavior, and does not start shadow, paper,
live, broker, risk, or execution work.

### ADE-QRE-016A - Evidence Gap Closure Inventory

- queue id: `ADE-QRE-016A`
- title: Evidence Gap Closure Inventory.
- status: `done`
- completion evidence: PR #376, merge SHA
  `21ad5a26a496c6f1e185c2c64596a3ba3426c4cd`; read-only evidence gap
  closure inventory added in
  `docs/governance/ade_qre_016a_evidence_gap_closure_inventory.md`; post-merge
  Fast pre-merge gate run `26562379703`, Docker build/push run `26562640607`,
  and VPS deploy run `26562640663` completed/success; local
  `git diff --check`, architecture scanner, and governance lint passed; frozen
  contracts unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked; Addendum runtime remained inactive.
- purpose: turn the prioritized `ADE-QRE-015B` gap list into a concrete,
  evidence-backed closure inventory without claiming unsupported readiness.
- depends on: `ADE-QRE-015H done`.
- risk class: LOW.
- target layer: governance docs and read-only evidence/reporting surfaces.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for deterministic read-only
    evidence inventory/reporting, `tests/unit/**` only if reporting changes,
    and `tests/architecture/**` where relevant.
- forbidden files or file families:
  - `registry.py`, strategy implementations, frozen schemas/contracts,
    regression pins, runtime behavior paths, strategy synthesis enablement
    paths, runtime Addendum activation paths, shadow/paper/live paths,
    broker/risk/execution paths, dashboard mutation routes, approval mutation
    paths, `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - docs.
  - read-only reporting.
  - tests if reporting changes.
  - deterministic mapping from `GAP-015B-01` through `GAP-015B-07` to closure
    candidates, missing evidence, blocked claims, and validation needs.
- forbidden changes:
  - strategy synthesis.
  - runtime behavior.
  - execution paths.
  - Addendum runtime activation.
  - `registry.py`.
  - strategy code.
  - frozen contract mutation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
  - targeted reporting tests if reporting code changes.
- validation required:
  - every closure candidate cites an `ADE-QRE-015A`, `ADE-QRE-015B`,
    `ADE-QRE-015C`, `ADE-QRE-015E`, or `ADE-QRE-015H` evidence basis.
  - unsupported readiness claims are explicitly avoided.
  - protected, frozen, research-output, and execution paths are untouched.
  - strategy synthesis remains blocked.
  - Addendum runtime remains inactive.
- merge criteria:
  - focused docs/read-only reporting/tests diff.
  - tests and CI green where applicable.
  - no strategy synthesis, runtime behavior, Addendum runtime, frozen contract,
    research output, or execution path changes.
- done criteria:
  - prioritized gaps are mapped to closure candidates.
  - unsupported claims are avoided.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-015H` is not done.
  - closure candidates require invented evidence outside the 015 record.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016B`.

### ADE-QRE-016B - Operator Trust Criteria Tightening

- queue id: `ADE-QRE-016B`
- title: Operator Trust Criteria Tightening.
- status: `done`
- completion evidence: PR #378, merge SHA
  `0d114c003d0c3860db06ee4eea838f3c5534e1a0`; read-only operator trust
  criteria added in
  `docs/governance/ade_qre_016b_operator_trust_criteria.md`; post-merge Fast
  pre-merge gate run `26564059058`, Docker build/push run `26564340950`, and
  VPS deploy run `26564340949` completed/success; local `git diff --check`,
  architecture scanner, and governance lint passed; frozen contracts
  unchanged; protected/execution paths untouched; strategy synthesis remained
  blocked; Addendum runtime remained inactive.
- purpose: define stricter criteria for scaffold, working capability, and
  operator-trusted capability, using the 015 evidence and 016A closure
  inventory.
- depends on: `ADE-QRE-016A done`.
- risk class: LOW.
- target layer: governance docs and read-only validation/reporting.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only trust
    criteria summaries, `tests/unit/**` only if reporting changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - runtime gate authority paths, strategy synthesis enablement paths,
    runtime Addendum activation paths, roadmap activation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - docs.
  - read-only validation/reporting.
  - tests if needed for reporting.
  - explicit, measurable, fail-closed trust criteria tied to evidence.
- forbidden changes:
  - changing runtime gates into authority.
  - strategy synthesis.
  - Addendum runtime activation.
  - autonomous authority expansion.
  - runtime promotion logic.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
  - targeted reporting tests if reporting code changes.
- validation required:
  - trust criteria distinguish scaffold, working capability, and
    operator-trusted capability.
  - missing evidence fails closed.
  - protected, frozen, research-output, and execution paths are untouched.
- merge criteria:
  - focused docs/read-only validation/reporting/tests diff.
  - tests and CI green where applicable.
  - no runtime authority expansion, synthesis, Addendum runtime, frozen
    contract, research output, or execution path changes.
- done criteria:
  - trust criteria are explicit, measurable, fail-closed, and evidence-backed.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016A` is not done.
  - criteria require authority beyond read-only reporting.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016C`.

### ADE-QRE-016C - Missing Evidence Fail-Closed Coverage

- queue id: `ADE-QRE-016C`
- title: Missing Evidence Fail-Closed Coverage.
- status: `done`
- completion evidence: PR #380, merge SHA
  `5f56b67d6f730e0687976d801fe80fc4b046246b`; read-only missing-evidence
  fail-closed reporter added in
  `reporting/trusted_loop_missing_evidence_fail_closed.py`, with coverage note
  `docs/governance/ade_qre_016c_missing_evidence_fail_closed_coverage.md`;
  post-merge Fast pre-merge gate run `26566607659`, Docker build/push run
  `26566886782`, and VPS deploy run `26566886794` completed/success; local
  targeted fail-closed tests, reporter CLI, ruff, `git diff --check`,
  architecture scanner, and governance lint passed; frozen contracts
  unchanged; protected/execution paths untouched; strategy synthesis remained
  blocked; Addendum runtime remained inactive.
- purpose: improve tests/reporting that prove missing evidence cannot be
  interpreted as readiness across key trusted-loop surfaces.
- depends on: `ADE-QRE-016B done`.
- risk class: LOW.
- target layer: read-only reporting/tests and governance docs.
- expected files or file families:
  - `reporting/**.py` for read-only fail-closed reporting checks,
    `tests/unit/**`, `tests/architecture/**` where relevant, fixtures used by
    existing reporting tests, and `docs/governance/**`.
- forbidden files or file families:
  - runtime promotion logic, strategy synthesis enablement paths,
    strategy code, `registry.py`, runtime Addendum activation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - tests.
  - fixtures.
  - read-only reporting checks.
  - docs.
- forbidden changes:
  - runtime promotion logic.
  - synthesis enablement.
  - strategy code.
  - execution paths.
  - Addendum runtime activation.
- tests required:
  - targeted fail-closed reporting tests.
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - missing reason-record, KPI, routing, sampling, diagnostics, retrieval, and
    queue-status evidence cannot be treated as ready/trusted.
  - protected, frozen, research-output, and execution paths are untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused tests/read-only reporting/docs diff.
  - tests and CI green where applicable.
  - no runtime promotion, synthesis, Addendum runtime, frozen contract,
    research output, or execution path changes.
- done criteria:
  - missing evidence paths fail closed across key trusted-loop surfaces.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016B` is not done.
  - fail-closed coverage requires runtime promotion behavior.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016D`.

### ADE-QRE-016D - Cross-Surface Consistency Audit

- queue id: `ADE-QRE-016D`
- title: Cross-Surface Consistency Audit.
- status: `done`
- completion evidence: PR #382, merge SHA
  `c6ded3af85897fbe8e3888085d6934075bc8b473`; read-only cross-surface
  consistency audit added in
  `reporting/trusted_loop_consistency_audit.py`, with governance note
  `docs/governance/ade_qre_016d_cross_surface_consistency_audit.md`;
  post-merge Fast pre-merge gate run `26568549334`, Docker build/push run
  `26568813970`, and VPS deploy run `26568813985` completed/success; local
  targeted consistency and fail-closed tests, reporter CLI, ruff,
  `git diff --check`, architecture scanner, and governance lint passed; frozen
  contracts unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked; Addendum runtime remained inactive.
- purpose: verify consistency across reason records, KPI readiness,
  routing/sampling readiness, diagnostics blockers, retrieval coverage, and
  queue status.
- depends on: `ADE-QRE-016C done`.
- risk class: LOW.
- target layer: read-only audit/reporting, tests, and governance docs.
- expected files or file families:
  - `reporting/**.py` only for read-only audit/reporting, `tests/unit/**`,
    `tests/architecture/**` where relevant, and `docs/governance/**`.
- forbidden files or file families:
  - reason-record mutation paths, KPI authority mutation paths,
    routing/campaign behavior paths, sampling behavior paths, strategy
    synthesis enablement paths, runtime Addendum activation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - read-only audit/reporting.
  - tests.
  - docs.
- forbidden changes:
  - mutation of audited surfaces.
  - routing behavior.
  - campaign behavior.
  - strategy synthesis.
  - runtime Addendum activation.
- tests required:
  - targeted consistency audit/reporting tests if code changes.
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - inconsistencies are explicit and either resolved by docs/reporting
    clarification or blocked with evidence.
  - protected, frozen, research-output, and execution paths are untouched.
  - retrieval remains context, not authority.
  - diagnostics remain evidence surfaces only.
- merge criteria:
  - focused read-only audit/reporting/tests/docs diff.
  - tests and CI green where applicable.
  - no surface mutation, synthesis, Addendum runtime, frozen contract, research
    output, or execution path changes.
- done criteria:
  - inconsistencies are explicit and either resolved or blocked with evidence.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016C` is not done.
  - audit requires mutating audited surfaces.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016E`.

### ADE-QRE-016E - Trusted-Loop Operator Summary v2

- queue id: `ADE-QRE-016E`
- title: Trusted-Loop Operator Summary v2.
- status: `done`
- completion evidence: PR #384, merge SHA
  `bc8b13806589f7acc4213dd2d0c0a4ba12592c3f`; docs-only trusted-loop
  operator summary v2 added in
  `docs/governance/ade_qre_016e_trusted_loop_operator_summary_v2.md`;
  post-merge Fast pre-merge gate run `26570241313`, Docker build/push run
  `26570496441`, and VPS deploy run `26570496538` completed/success; local
  `git diff --check`, architecture scanner, governance lint, and queue
  self-audit passed; frozen contracts unchanged; protected/execution paths
  untouched; strategy synthesis remained blocked; Addendum runtime remained
  inactive.
- purpose: produce a clearer operator-facing summary of what the trusted loop
  can and cannot currently do.
- depends on: `ADE-QRE-016D done`.
- risk class: LOW.
- target layer: governance docs and read-only operator/reporting summary.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only summary
    output, `tests/unit/**` only if reporting changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - dashboard mutation routes, approval mutation paths, runtime authority
    expansion paths, strategy synthesis enablement paths, runtime Addendum
    activation paths, shadow/paper/live paths, broker/risk/execution paths,
    frozen contracts, `registry.py`, strategy implementations,
    `research/research_latest.json`, and `research/strategy_matrix.csv`.
- allowed changes:
  - docs.
  - read-only reporting summary.
  - tests if reporting changes.
- forbidden changes:
  - dashboard mutation routes.
  - approval mutation.
  - runtime authority expansion.
  - strategy synthesis.
  - Addendum runtime activation.
- tests required:
  - targeted operator summary tests if reporting changes.
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
- validation required:
  - operator can see ready, blocked, deferred, not-trusted, and no-synthesis
    reasons clearly.
  - protected, frozen, research-output, and execution paths are untouched.
  - no approval or dashboard mutation behavior is added.
- merge criteria:
  - focused docs/read-only reporting/tests diff.
  - tests and CI green where applicable.
  - no dashboard mutation, approval mutation, runtime authority expansion,
    synthesis, Addendum runtime, frozen contract, research output, or execution
    path changes.
- done criteria:
  - operator can see ready, blocked, deferred, not-trusted, and no-synthesis
    reasons clearly.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016D` is not done.
  - summary requires mutation routes or approval controls.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016F`.

### ADE-QRE-016F - Return-to-Feature-Track Criteria Refinement

- queue id: `ADE-QRE-016F`
- title: Return-to-Feature-Track Criteria Refinement.
- status: `done`
- completion evidence: PR #386, merge SHA
  `7b8d692f9377f147c606a665de4be1207828de26`; docs-only return-to-feature-track
  criteria added in
  `docs/governance/ade_qre_016f_return_to_feature_track_criteria.md`;
  post-merge Fast pre-merge gate run `26571922528`, Docker build/push run
  `26572222841`, and VPS deploy run `26572222812` completed/success; local
  `git diff --check`, architecture scanner, governance lint, and queue
  self-audit passed; frozen contracts unchanged; protected/execution paths
  untouched; strategy synthesis remained blocked; Addendum runtime remained
  inactive.
- purpose: refine exact evidence requirements for a future return to QRE
  Feature Build Track without starting it.
- depends on: `ADE-QRE-016E done`.
- risk class: LOW.
- target layer: governance docs and read-only criteria/checklist surfaces.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only checklist or
    criteria summary if needed, `tests/unit/**` only if reporting changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - Roadmap v6 v3.15.16 implementation paths, roadmap mutation paths,
    strategy synthesis enablement paths, routing implementation paths,
    campaign mutation paths, runtime Addendum activation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only criteria.
  - read-only checklist.
  - tests only if reporting changes.
- forbidden changes:
  - implementing v3.15.16.
  - roadmap mutation.
  - strategy synthesis.
  - routing implementation.
  - Addendum runtime activation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
  - targeted reporting tests if reporting code changes.
- validation required:
  - return criteria are explicit and evidence-backed.
  - no implementation starts.
  - protected, frozen, research-output, and execution paths are untouched.
  - strategy synthesis remains blocked.
- merge criteria:
  - focused docs/read-only checklist/tests diff.
  - tests and CI green where applicable.
  - no v3.15.16 implementation, roadmap mutation, synthesis, routing
    implementation, Addendum runtime, frozen contract, research output, or
    execution path changes.
- done criteria:
  - return criteria are explicit and evidence-backed.
  - no implementation starts.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016E` is not done.
  - criteria require feature-track implementation.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016G`.

### ADE-QRE-016G - Next Sprint Decision Check

- queue id: `ADE-QRE-016G`
- title: Next Sprint Decision Check.
- status: `done`
- completion evidence: PR #388, merge SHA
  `fa11434a2572ddf42e3f8ed0dce318783e158634`; docs-only next sprint
  decision check added in
  `docs/governance/ade_qre_016g_next_sprint_decision_check.md`, selecting
  exactly one allowed output, `continue_trusted_loop_maturity`; post-merge
  Fast pre-merge gate run `26573650469`, Docker build/push run `26573907736`,
  and VPS deploy run `26573907739` completed/success; local
  `git diff --check`, architecture scanner, governance lint, queue self-audit,
  and exactly-one-recommendation check passed; frozen contracts unchanged;
  protected/execution paths untouched; strategy synthesis remained blocked;
  Addendum runtime remained inactive.
- purpose: decide whether the next direction should be another maturity
  sprint, operator review, return-to-feature-track planning, or no eligible
  work.
- depends on: `ADE-QRE-016F done`.
- risk class: LOW.
- target layer: governance docs and read-only decision record.
- expected files or file families:
  - `docs/governance/**`, `reporting/**.py` only for read-only decision
    reporting if needed, `tests/unit/**` only if reporting changes, and
    `tests/architecture/**` where relevant.
- forbidden files or file families:
  - selected-direction implementation paths, strategy synthesis enablement
    paths, runtime Addendum activation paths, roadmap mutation paths,
    shadow/paper/live paths, broker/risk/execution paths, frozen contracts,
    dashboard mutation routes, approval mutation paths, `registry.py`,
    strategy implementations, `research/research_latest.json`, and
    `research/strategy_matrix.csv`.
- allowed outputs exactly:
  1. `continue_trusted_loop_maturity`.
  2. `return_to_qre_feature_track_planning`.
  3. `operator_review_required`.
  4. `no_eligible_work_remains`.
- allowed changes:
  - docs-only decision check.
  - read-only decision reporting if needed.
  - evidence-backed selection of exactly one allowed output.
- forbidden changes:
  - starting the selected direction implementation.
  - strategy synthesis.
  - Addendum runtime activation.
  - roadmap mutation.
  - execution paths.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
  - targeted reporting tests if reporting code changes.
- validation required:
  - exactly one recommendation is selected.
  - recommendation is evidence-backed.
  - unselected recommendations remain blocked/deferred.
  - protected, frozen, research-output, and execution paths are untouched.
- merge criteria:
  - focused docs/read-only reporting/tests diff.
  - tests and CI green where applicable.
  - no selected-direction implementation, synthesis, Addendum runtime, roadmap
    mutation, frozen contract, research output, or execution path changes.
- done criteria:
  - exactly one recommendation is selected and evidence-backed.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016F` is not done.
  - more than one recommendation would be selected.
  - evidence is insufficient and operator review is not selected.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - runtime behavior mutation required.
  - live/paper/shadow/risk/broker/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: `ADE-QRE-016H`.

### ADE-QRE-016H - Queue Direction Finalization

- queue id: `ADE-QRE-016H`
- title: Queue Direction Finalization.
- status: `done`
- completion evidence: PR #390, merge SHA
  `bdba23846c04f575015c1f29b56748e9feefc09c`; docs-only queue direction
  finalization added in
  `docs/governance/ade_qre_016h_queue_direction_finalization.md`, selecting
  exactly one next direction, `ADE-QRE-017 trusted-loop evidence closure
  maturity queue`, without starting that direction; post-merge Fast pre-merge
  gate run `26576056772`, Docker build/push run `26576372752`, and VPS deploy
  run `26576372754` completed/success; local `git diff --check`,
  architecture scanner, governance lint, protected/frozen diff check, queue
  self-audit, and exactly-one-finalized-direction check passed; frozen
  contracts unchanged; protected/execution paths untouched; strategy synthesis
  remained blocked; Addendum runtime remained inactive.
- purpose: finalize exactly one next queue direction after `ADE-QRE-016`.
- depends on: `ADE-QRE-016G done`.
- risk class: LOW.
- target layer: governance docs and docs-only queue-direction finalization.
- expected files or file families:
  - `docs/governance/**`, and `reporting/**.py` or `tests/unit/**` only if a
    read-only finalization report already exists and needs narrow validation.
- forbidden files or file families:
  - next-queue implementation paths, strategy synthesis enablement paths,
    runtime Addendum activation paths, shadow/paper/live paths,
    broker/risk/execution paths, routing/campaign mutation paths, frozen
    contracts, dashboard mutation routes, approval mutation paths,
    `registry.py`, strategy implementations, `research/research_latest.json`,
    and `research/strategy_matrix.csv`.
- allowed changes:
  - docs-only finalization.
  - evidence-backed next queue recommendation.
  - blocked/deferred notes for unsupported directions.
- forbidden changes:
  - implementing the next queue.
  - strategy synthesis.
  - Addendum runtime activation.
  - shadow/paper/live.
  - broker/risk/execution.
  - frozen contract mutation.
- tests required:
  - `git diff --check`.
  - architecture scanner summary.
  - governance lint if available.
  - targeted reporting tests if reporting code changes.
- validation required:
  - next direction is explicit.
  - unsupported directions remain blocked/deferred.
  - protected, frozen, research-output, and execution paths are untouched.
  - strategy synthesis remains blocked.
  - Addendum runtime remains inactive.
- merge criteria:
  - focused docs-only finalization diff.
  - tests and CI green where applicable.
  - no next-queue implementation, synthesis, Addendum runtime, shadow/paper/live,
    broker/risk/execution, frozen contract, research output, routing mutation,
    or campaign mutation changes.
- done criteria:
  - next direction is explicit.
  - unsupported directions remain blocked/deferred.
  - PR merged and validated.
- stop conditions:
  - `ADE-QRE-016G` is not done.
  - more than one next direction would be selected.
  - protected paths touched unexpectedly.
  - frozen contracts touched.
  - strategy synthesis would be enabled.
  - Addendum runtime activation required.
  - shadow/paper/live required.
  - broker/risk/execution paths required.
  - dashboard mutation route required.
  - approval mutation required.
  - HIGH/UNKNOWN authority required.
  - CI failure outside scope.
  - remote auth failure.
  - local git unsafe state.
- next dependency: none.

### ADE-QRE-017 - Trusted Research Intelligence Maturity Program

- queue id: `ADE-QRE-017`
- title: Trusted Research Intelligence Maturity Program.
- status: `blocked until ADE-QRE-017AD done`
- purpose: govern the full scaffold-to-trust maturity program selected by
  `ADE-QRE-016H` without collapsing the work into one giant implementation
  release.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-016H done`.
- risk class: MEDIUM.
- target layer: governance coordination, queue sequencing, documentation,
  reporting, package-boundary QRE maturity, and campaign-readiness control.
- expected files or file families:
  - `docs/governance/**`
  - `docs/roadmap/**`
  - `reporting/**.py`
  - `packages/qre_*/**`
  - `tests/unit/**`
  - `tests/integration/**`
  - `tests/architecture/**`
- forbidden files or file families:
  - `.claude/**`
  - `research/research_latest.json`
  - `research/strategy_matrix.csv`
  - `automation/live_gate.py`
  - `broker/**`
  - `agent/risk/**`
  - `agent/execution/**`
  - `live/**`
  - `paper/**`
  - `shadow/**`
  - `trading/**`
- completion rule:
  - parent stays non-executable and is completed only after `ADE-QRE-017A`
    through `ADE-QRE-017AD` are done with PR, merge, CI, and post-merge
    evidence recorded.
- next dependency: `ADE-QRE-017A`.

### ADE-QRE-017A - Baseline Reconciliation and Maturity Matrix

- queue id: `ADE-QRE-017A`
- title: Baseline Reconciliation and Maturity Matrix.
- status: `done`
- purpose: produce the repository-backed maturity matrix for all relevant
  trusted research intelligence surfaces.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-016H done`.
- risk class: LOW.
- target layer: governance docs, reporting, and read-only maturity
  classification.
- expected files or file families:
  - `docs/governance/**`
  - `docs/roadmap/**`
  - `reporting/**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - `.claude/**`
  - `research/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - capability classes are closed and repository-backed.
  - counts, blockers, and non-authoritative surfaces are explicit.
- completion evidence: PR #620, merge SHA `92e7ba900a451e924ae98dfe51e37a838de6a518`;
  PR checks green after the boundary/queue-test repair follow-up; post-merge
  `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q`,
  and `python -m reporting.architecture_import_scan --format summary` passed on
  `main`; `python -m reporting.roadmap_next_unit --status` selected
  `u_ade_qre_017b_evidence_density_inventory_001` / `ADE-QRE-017B`; frozen
  contracts unchanged; protected/execution paths untouched; paper/shadow/live,
  broker, risk, and execution behavior remained inactive.
- next dependency: `ADE-QRE-017B`.

### ADE-QRE-017B - Evidence-Density Population Plan

- queue id: `ADE-QRE-017B`
- title: Evidence-Density Population Plan.
- status: `done`
- purpose: inventory required evidence classes, producers, consumers,
  population state, and fail-closed blockers.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017A done`.
- risk class: LOW.
- target layer: governance docs, reporting, evidence planning.
- expected files or file families:
  - `docs/governance/**`
  - `reporting/**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - `.claude/**`
  - `research/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - every required evidence class has a producer, consumer, and state.
  - blockers fail closed instead of inferring completeness.
- completion evidence: PR #622, merge SHA `91566cf7ea1017283a41e48a4306f485df5d3565`;
  Fast pre-merge gate checks green on the PR; post-merge targeted tests,
  queue self-audit, roadmap task units, roadmap unit authority, and roadmap
  next-unit selection passed on `main`, selecting
  `u_ade_qre_017c_reason_record_maturity_reporter_001` / `ADE-QRE-017C`;
  frozen contracts unchanged; protected/execution paths untouched; strategy
  synthesis remained blocked.
- next dependency: `ADE-QRE-017C`.

### ADE-QRE-017C - Reason-Record Maturity

- queue id: `ADE-QRE-017C`
- title: Reason-Record Maturity.
- status: `done`
- purpose: make reason records non-empty, normalized, durable, and
  evidence-referenced when real evidence exists.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017B done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research` / `qre_artifacts`.
- expected files or file families:
  - `reporting/qre_reason_record_maturity.py`
  - `docs/governance/qre_reason_record_maturity.md`
  - `tests/unit/**`
- forbidden files or file families:
  - fake evidence producers
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - fake reasons are impossible.
  - evidence absence fails closed.
- completion evidence: PR #624, merge SHA `df3872297160ce946065eba7ad5ff9d85521cd34`;
  PR checks green including `unit (smoke + unit)`, governance lint, lint,
  typecheck, path-classifier, secret scan, architecture-boundary, hook-tests,
  regression-fast, and frontend checks; post-merge targeted tests and
  `python -m reporting.ade_queue_status_self_audit --no-write` passed; durable
  `qre_reason_records`, `qre_reason_record_audit`, and
  `qre_reason_record_normalization` artifacts were materialized through the
  repository-native writers; frozen contracts unchanged; protected paths
  untouched; live/paper/shadow/risk/broker/execution inactive.
- next dependency: `ADE-QRE-017D`.

### ADE-QRE-017D - Routing/Sampling Readiness Population

- queue id: `ADE-QRE-017D`
- status: `done`
- title: Routing/Sampling Readiness Population.
- purpose: populate routing-ready and sampling-ready artifacts from real
  repository evidence.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017C done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research`, packages `qre_artifacts`.
- expected files or file families:
  - `reporting/qre_routing_sampling_readiness.py`
  - `docs/governance/qre_routing_sampling_readiness.md`
  - `tests/unit/**`
- forbidden files or file families:
  - inferred readiness from scaffold presence alone
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - ready states must be evidence-derived and fail closed otherwise.
- completion evidence: PR #626, merge SHA `15842f6dd3f67ba8a8b94093bd1f0c2b027b8dd5`;
  CI checks green (`architecture-boundary`, `frontend (vitest)`,
  `governance-lint`, `hook-tests (governance hooks)`, `lint (ruff)`,
  `path-classifier`, `regression-fast (determinism pins)`,
  `secret-scan (gitleaks)`, `typecheck (mypy narrow)`, `unit (smoke +
  unit)`); post-merge focused validation passed
  `python -m pytest tests/unit/test_qre_routing_sampling_readiness.py
  tests/unit/test_roadmap_task_units.py tests/unit/test_roadmap_next_unit.py
  tests/unit/test_ade_qre_017_queue_admission.py
  tests/unit/test_ade_queue_status_self_audit.py
  tests/unit/test_ade_qre_014_queue_lifecycle.py -q`,
  `python -m reporting.ade_queue_status_self_audit --no-write`,
  `python -m reporting.roadmap_task_units`,
  `python -m reporting.roadmap_unit_authority`, and
  `python -m reporting.roadmap_next_unit --status`; the merged item
  materializes repository-native routing and sampling readiness artifacts from
  real basket evidence, records 2 shared ready candidates with 100% routing and
  sampling reason-record coverage across the 15-candidate basket, preserves
  explicit non-ready states for blocked/deferred candidates; frozen contracts
  unchanged; protected/execution paths untouched.
- next dependency: `ADE-QRE-017E`.

### ADE-QRE-017E - KPI Completeness and Historical Snapshots

- queue id: `ADE-QRE-017E`
- title: KPI Completeness and Historical Snapshots.
- status: `done`
- purpose: produce complete numeric or explicitly unavailable KPI states and
  repeatable historical snapshots.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017D done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_artifacts`, governance docs.
- expected files or file families:
  - `reporting/qre_kpi_snapshot_completeness.py`
  - `docs/governance/qre_kpi_snapshot_completeness.md`
  - `tests/unit/**`
- forbidden files or file families:
  - weakened KPI standards
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - unavailable KPIs are explicit.
  - snapshot generation is repeatable.
- completion evidence: PR #628, merge SHA
  `ac35e6d347de9464c0eb075ed69d1ac3855ad506`; read-only KPI completeness and
  historical snapshot reporter added in
  `reporting/qre_kpi_snapshot_completeness.py`, with governance note
  `docs/governance/qre_kpi_snapshot_completeness.md`; required CI checks green
  before squash-merge; post-merge governance lint, `tests/architecture`,
  architecture scanner summary, queue self-audit, next-unit status, and frozen
  contract diff checks passed on `main`; frozen contracts unchanged;
  protected/execution paths untouched.
- next dependency: `ADE-QRE-017F`.

### ADE-QRE-017F - Funnel Census and Threshold-Distance Audit

- queue id: `ADE-QRE-017F`
- title: Funnel Census and Threshold-Distance Audit.
- status: `done`
- purpose: materialize full funnel counts, threshold distances, and exactly-one
  recommendation per criterion without changing thresholds.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017E done`.
- risk class: MEDIUM.
- target layer: reporting, diagnostics, governance docs.
- expected files or file families:
  - `reporting/**funnel**.py`
  - `reporting/**diagnostic**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - threshold mutation
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - stage counts, actual values, thresholds, and distances are explicit.
  - each criterion has exactly one recommendation.
- completion evidence: PR #630, merge SHA
  `41a0dd2b7c111360facc9dfc866d17dc6b611e9e`; read-only funnel census and
  threshold-distance audit reporter added in
  `reporting/qre_funnel_threshold_audit.py`, with governance note
  `docs/governance/qre_funnel_threshold_audit.md`; required CI checks green
  before squash-merge; post-merge queue/governance validation pending in the
  follow-up queue-state PR; frozen contracts unchanged; protected/execution
  paths untouched.
- next dependency: `ADE-QRE-017G`.

### ADE-QRE-017G - Actionable Failure Taxonomy and Next Actions

- queue id: `ADE-QRE-017G`
- title: Actionable Failure Taxonomy and Next Actions.
- status: `done`
- purpose: expand evidence-backed failure attribution and bind each supported
  failure class to exactly one bounded advisory next action.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017F done`.
- risk class: MEDIUM.
- target layer: reporting, diagnostics, policy read surfaces.
- expected files or file families:
  - `reporting/failure_action_mapping_minimal.py`
  - `reporting/**failure**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - invented causes
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - insufficient evidence stays explicit.
  - exactly one next action per supported failure class.
- completion evidence: PR #632, merge SHA
  `709fe8bc7d04e4a8f785046ae164ee6d48e2ad32`; read-only actionable failure
  taxonomy reporter added in `reporting/qre_actionable_failure_taxonomy.py`,
  with governance summary `docs/governance/qre_actionable_failure_taxonomy.md`;
  required CI checks green before squash-merge; post-merge queue/governance
  validation pending in the follow-up queue-state PR; frozen contracts
  unchanged; protected/execution paths untouched.
- next dependency: `ADE-QRE-017H`.

### ADE-QRE-017H - Action Usefulness Tracking

- queue id: `ADE-QRE-017H`
- title: Action Usefulness Tracking.
- status: `done`
- purpose: track whether recommended actions were executed and whether they
  improved useful outcomes or repeated failure.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017G done`.
- risk class: MEDIUM.
- target layer: reporting, diagnostics, governance docs.
- expected files or file families:
  - `reporting/**action**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - unverifiable usefulness claims
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - executed, blocked, repeated-failure, compute-saved, and false-positive
    outcomes are explicit.
- completion evidence: PR #634, merge SHA
  `4774c56bae5ff7c814b8db917321e27f6c50af7d`; read-only action usefulness
  tracker added in `reporting/qre_action_usefulness_tracking.py`, with
  governance summary `docs/governance/qre_action_usefulness_tracking.md`;
  required CI checks green before squash-merge; post-merge queue/governance
  validation pending in the follow-up queue-state PR; frozen contracts
  unchanged; protected/execution paths untouched.
- next dependency: `ADE-QRE-017I`.

### ADE-QRE-017I - Quality-Gated OHLCV/Cache Foundation

- queue id: `ADE-QRE-017I`
- title: Quality-Gated OHLCV/Cache Foundation.
- status: `done`
- purpose: mature a reproducible, versioned, quality-gated OHLCV/cache
  foundation using existing packages and repository-local datasets first.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017H done`.
- risk class: MEDIUM.
- target layer: packages `qre_data`, reporting, tests.
- expected files or file families:
  - `packages/qre_data/cache_manifest.py`
  - `packages/qre_data/contracts.py`
  - `packages/qre_data/historical_accounting.py`
  - `tests/unit/**`
- forbidden files or file families:
  - invented external fetches
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - locally possible components complete before any external-source block is
    recorded.
- completion evidence: PR #636, merge SHA
  `23b9fdbbdbd5016640bf8cbe1bebc2442209643b`; read-only local cache
  foundation report added in `research/qre_ohlcv_cache_foundation.py`, with
  governance summary `docs/governance/qre_ohlcv_cache_foundation.md` and
  tracked artifact `artifacts/cache/cache_foundation_latest.v1.json`; required
  CI checks green before squash-merge; post-merge governance and architecture
  validation passed on `main`; frozen contracts unchanged; protected/execution
  paths untouched.
- next dependency: `ADE-QRE-017J`.

### ADE-QRE-017J - Source Quality, PIT, and Identity Readiness

- queue id: `ADE-QRE-017J`
- title: Source Quality, PIT, and Identity Readiness.
- status: `done`
- purpose: implement freshness, missing-data, duplicate, monotonicity,
  outlier, coverage, agreement, PIT, revision, identity, and allowed-use
  readiness.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017I done`.
- risk class: MEDIUM.
- target layer: packages `qre_data`, reporting, policy read surfaces.
- expected files or file families:
  - `packages/qre_data/source_quality_readiness.py`
  - `packages/qre_data/source_lifecycle.py`
  - `packages/qre_data/symbology_resolver.py`
  - `tests/unit/**`
- forbidden files or file families:
  - silent identity ambiguity acceptance
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - quality failures and identity ambiguity block rather than downgrade.
- completion evidence:
  - PR #638, merge SHA `5a1ae50a2c7a015d1e3a171f09ab80a54d83d17d`; checks green before squash-merge; implementation report:
    `research/qre_source_quality_pit_identity_readiness.py`; governance note:
    `docs/governance/qre_source_quality_pit_identity_readiness.md`; tracked artifact:
    `artifacts/data_readiness/source_quality_pit_identity_readiness_latest.v1.json`; focused validation:
    `python -m pytest tests/unit/test_qre_data_source_quality_readiness.py tests/unit/test_qre_data_source_lifecycle.py tests/unit/test_qre_data_symbology_resolver.py tests/unit/test_point_in_time_policy.py tests/unit/test_report_lag_policy.py tests/unit/test_qre_historical_accounting_foundation.py tests/unit/test_qre_symbology_resolver_foundation.py tests/unit/test_qre_source_lifecycle_quality_gate.py tests/unit/test_qre_source_quality_pit_identity_readiness.py -q`; post-merge governance and architecture validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched.
- next dependency: `ADE-QRE-017K`.

### ADE-QRE-017K - Source Usefulness Ledger

- queue id: `ADE-QRE-017K`
- title: Source Usefulness Ledger.
- status: `done`
- purpose: track actual source outcomes, usefulness, disagreements, savings,
  and operator value without treating source quality as alpha.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017J done`.
- risk class: MEDIUM.
- target layer: packages `qre_data`, reporting, tests.
- expected files or file families:
  - `packages/qre_data/**`
  - `reporting/**source**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - alpha-probability proxies
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - usefulness is tied to actual influenced outcomes.
- completion evidence:
  PR #640, merge SHA `4f66d632346d4bf9e4eb171f6e70bdc70ed3cb53`; checks green before
  squash-merge; implementation note:
  `docs/governance/qre_source_usefulness_ledger.md`; canonical artifact:
  `logs/qre_source_usefulness_ledger/latest.json`; operator summary:
  `logs/qre_source_usefulness_ledger/operator_summary.md`; validation:
  `python -m pytest tests/unit/test_qre_source_usefulness_ledger.py tests/unit/test_qre_lineage_graph_v1.py -q`,
  `python -m research.qre_source_usefulness_ledger --status`,
  `python scripts/governance_lint.py`, `git diff --check`; post-merge governance
  and architecture validation passed on `main`; frozen contracts unchanged;
  protected/execution paths untouched.
- next dependency: `ADE-QRE-017L`.

### ADE-QRE-017L - Behavior Thesis Registry

- queue id: `ADE-QRE-017L`
- title: Behavior Thesis Registry.
- status: `done`
- completion evidence: PR #643, merge SHA
  `029d6b2107175a5feb4cacda84ad46f3e1b15c97`; implementation added
  `research/qre_behavior_thesis_registry.py`, canonical doc
  `docs/governance/qre_behavior_thesis_registry.md`, and focused tests in
  `tests/unit/test_qre_behavior_thesis_registry.py`; canonical artifact:
  `logs/qre_behavior_thesis_registry/latest.json`; validation:
  `python -m pytest tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_research_memory.py tests/unit/test_qre_research_memory_retrieval.py tests/unit/test_qre_hypothesis_model.py -q`,
  `python -m research.qre_behavior_thesis_registry --write`,
  `python scripts/governance_lint.py`,
  `python -m pytest tests/architecture -q`,
  `python -m reporting.architecture_import_scan --format summary`,
  `git diff --check`; checks green; post-merge validation passed on `main`;
  frozen contracts unchanged; protected/execution paths untouched; no
  executable strategy generation, strategy registration, or campaign
  authority added.
- purpose: create a deterministic behavior-thesis registry with mechanism,
  falsification, sampling, validation, OOS, and data requirements.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017K done`.
- risk class: MEDIUM.
- target layer: packages `qre_research`, reporting, governance docs.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**thesis**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - executable strategy generation
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - every thesis has deterministic identity and falsification fields.
- next dependency: `ADE-QRE-017M`.

### ADE-QRE-017M - Supporting and Contradicting Evidence

- queue id: `ADE-QRE-017M`
- title: Supporting and Contradicting Evidence.
- status: `done`
- completion evidence: PR #645, merge SHA
  `c3ca9d04b76e5bbd9d0bb5ef2217267bab164136`; implementation added
  `research/qre_behavior_thesis_evidence.py`, canonical doc
  `docs/governance/qre_behavior_thesis_evidence.md`, and focused tests in
  `tests/unit/test_qre_behavior_thesis_evidence.py`; canonical artifact:
  `logs/qre_behavior_thesis_evidence/latest.json`; validation:
  `python -m pytest tests/unit/test_qre_behavior_thesis_evidence.py tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_research_memory.py tests/unit/test_qre_research_memory_retrieval.py tests/unit/test_hypothesis_discovery_minimal.py -q`,
  `python -m research.qre_behavior_thesis_evidence --write`,
  `python scripts/governance_lint.py`,
  `python -m pytest tests/architecture -q`,
  `python -m reporting.architecture_import_scan --format summary`,
  `git diff --check`; checks green; post-merge validation passed on `main`;
  frozen contracts unchanged; protected/execution paths untouched;
  contradictions, supporting evidence, and unresolved evidence remain explicit
  and context-only.
- purpose: attach supporting, contradicting, and unresolved evidence to each
  thesis with provenance.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017L done`.
- risk class: MEDIUM.
- target layer: packages `qre_research`, reporting, evidence surfaces.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**evidence**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - hidden contradictions
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - contradictions and unresolved evidence remain visible.
- next dependency: `ADE-QRE-017N`.

### ADE-QRE-017N - Prior-Failure Retrieval

- queue id: `ADE-QRE-017N`
- title: Prior-Failure Retrieval.
- status: `done`
- completion evidence: PR #647, merge SHA `5a8b51092cfb2acf4a6757030785473a6835cde8`;
  implementation added `research/qre_prior_failure_retrieval.py`, canonical
  doc `docs/governance/qre_prior_failure_retrieval.md`, and focused tests in
  `tests/unit/test_qre_prior_failure_retrieval.py`; canonical artifact:
  `logs/qre_prior_failure_retrieval/latest.json`; validation:
  `python -m pytest tests/unit/test_qre_prior_failure_retrieval.py tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_behavior_thesis_evidence.py tests/unit/test_qre_research_memory.py tests/unit/test_qre_research_memory_retrieval.py tests/unit/test_qre_retrieval_maturity.py -q`,
  `python -m research.qre_prior_failure_retrieval --write`,
  `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q`,
  `python -m reporting.architecture_import_scan --format summary`,
  `git diff --check`; checks green; post-merge validation passed on `main`;
  frozen contracts unchanged; protected/execution paths untouched; retrieval
  remained context only and did not become evidence authority.
- purpose: use existing retrieval and research memory to return related prior
  failures, dead zones, and actions as context only.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017M done`.
- risk class: MEDIUM.
- target layer: packages `qre_research`, reporting.
- expected files or file families:
  - `packages/qre_research/research_memory.py`
  - `packages/qre_research/retrieval_coverage.py`
  - `reporting/**retrieval**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - retrieval-as-authority promotion
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - retrieved results are clearly marked contextual and provenance-linked.
- next dependency: `ADE-QRE-017O`.

### ADE-QRE-017O - Opportunity Research Value

- queue id: `ADE-QRE-017O`
- title: Opportunity Research Value.
- status: `done`
- completion evidence: PR #649, merge SHA `7d317b64cd8df6a7fcb3af97054c1b42bd6a61c1`;
  implementation added `research/qre_opportunity_research_value.py`,
  `packages/qre_research/opportunity_value.py`, canonical doc
  `docs/governance/qre_opportunity_research_value.md`, and focused tests in
  `tests/unit/test_qre_opportunity_research_value.py`; canonical artifact:
  `logs/qre_opportunity_research_value/latest.json`; validation:
  `python -m pytest tests/unit/test_qre_opportunity_research_value.py tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_behavior_thesis_evidence.py tests/unit/test_qre_prior_failure_retrieval.py tests/unit/test_hypothesis_discovery_minimal.py -q`,
  `python -m research.qre_opportunity_research_value --write`,
  `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q`,
  `python -m reporting.architecture_import_scan --format summary`,
  `git diff --check`; checks green; post-merge validation passed on `main`;
  frozen contracts unchanged; protected/execution paths untouched; opportunity
  scoring remained expected research value only and did not become alpha,
  registration, or campaign authority.
- purpose: implement a deterministic research-value score for prioritization
  that is explicitly not alpha probability.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017N done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research`, tests.
- expected files or file families:
  - `reporting/**opportunity**.py`
  - `packages/qre_research/**`
  - `tests/unit/**`
- forbidden files or file families:
  - hidden model selectors
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - score factors are explainable and deterministic.
- next dependency: `ADE-QRE-017P`.

### ADE-QRE-017P - Routing Baseline Comparison

- queue id: `ADE-QRE-017P`
- title: Routing Baseline Comparison.
- status: `done`
- completion evidence: PR #651, merge SHA `ed0b9700106b23d18c14c9e9b06a5084e82f113d`; implementation added `research/qre_routing_baseline_comparison.py`, canonical doc `docs/governance/qre_routing_baseline_comparison.md`, and focused tests in `tests/unit/test_qre_routing_baseline_comparison.py`; validation: `python -m pytest tests/unit/test_qre_routing_baseline_comparison.py tests/unit/test_qre_opportunity_research_value.py tests/unit/test_qre_research_cycle_router.py tests/unit/test_qre_routing_score.py -q`, `python -m research.qre_routing_baseline_comparison --write`, `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q`, `python -m reporting.architecture_import_scan --format summary`, `git diff --check`; checks green; post-merge validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched; routing comparison remained deterministic, context-only, and non-authoritative.
- purpose: compare current routing against deterministic baselines and measure
  actual decision usefulness.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017O done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research`, tests.
- expected files or file families:
  - `reporting/intelligent_routing*.py`
  - `reporting/**routing**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - adaptive hidden routing
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - baseline comparisons are deterministic and evidence-backed.
- next dependency: `ADE-QRE-017Q`.

### ADE-QRE-017Q - Sampling Baseline Comparison

- queue id: `ADE-QRE-017Q`
- title: Sampling Baseline Comparison.
- status: `done`
- completion evidence: PR #653, merge SHA `11ae16354e32096a7746311d1e396fee14c4c1df`; implementation added `reporting/qre_sampling_baseline_comparison.py`, canonical doc `docs/governance/qre_sampling_baseline_comparison.md`, and focused tests in `tests/unit/test_qre_sampling_baseline_comparison.py`; validation: `python -m pytest tests/unit/test_qre_sampling_baseline_comparison.py tests/unit/test_qre_routing_sampling_readiness.py tests/unit/test_qre_sampling_readiness_from_basket.py tests/unit/test_qre_routing_baseline_comparison.py -q` (`21 passed`), `python -m reporting.qre_sampling_baseline_comparison --write`, `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q` (`157 passed`), `python -m reporting.architecture_import_scan --format summary` (`forbidden_edge_count: 0`), `git diff --check`; checks green; post-merge validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched; sampling comparison remained deterministic, context-only, and non-authoritative.
- purpose: compare sampling against deterministic baselines for signal density,
  adequacy, coverage, and compute efficiency.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017P done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research`, tests.
- expected files or file families:
  - `reporting/**sampling**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - hidden adaptive sampling selectors
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - sampling usefulness is compared against simple baselines.
- next dependency: `ADE-QRE-017R`.

### ADE-QRE-017R - Dead-Zone and Duplicate Suppression Efficacy

- queue id: `ADE-QRE-017R`
- title: Dead-Zone and Duplicate Suppression Efficacy.
- status: `done`
- completion evidence: PR #656, merge SHA `aad09dc59713f528f7d166decd6625a7f14adeab`; implementation added `reporting/qre_suppression_efficacy.py`, canonical doc `docs/governance/qre_suppression_efficacy.md`, and focused tests in `tests/unit/test_qre_suppression_efficacy.py`; validation: `python -m pytest tests/unit/test_qre_suppression_efficacy.py tests/unit/test_qre_routing_baseline_comparison.py tests/unit/test_qre_sampling_baseline_comparison.py tests/unit/test_qre_prior_failure_retrieval.py -q` (`26 passed`), `python -m reporting.qre_suppression_efficacy --write`, `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q` (`157 passed`), `python -m reporting.architecture_import_scan --format summary` (`forbidden_edge_count: 0`), `git diff --check`; checks green; post-merge validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched; suppression efficacy remained deterministic, read-only, context-only, and fail-closed where no same-population no-suppression baseline exists.
- purpose: prove whether suppression prevents repeated low-value research.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017Q done`.
- risk class: MEDIUM.
- target layer: reporting, diagnostics, tests.
- expected files or file families:
  - `reporting/**suppression**.py`
  - `reporting/**routing**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - efficacy claims without before/after evidence
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - before/after evidence is explicit.
- next dependency: `ADE-QRE-017S`.

### ADE-QRE-017S - Contradiction Graph and Hypothesis Lineage

- queue id: `ADE-QRE-017S`
- title: Contradiction Graph and Hypothesis Lineage.
- status: `done`
- completion evidence: PR #658, merge SHA `f2b28b44f3d73667792b6f0f1e5d0e226c100595`; implementation added `reporting/qre_contradiction_hypothesis_lineage.py`, canonical doc `docs/governance/qre_contradiction_hypothesis_lineage.md`, and focused tests in `tests/unit/test_qre_contradiction_hypothesis_lineage.py`; validation: `python -m pytest tests/unit/test_qre_contradiction_hypothesis_lineage.py tests/unit/test_qre_lineage_graph_v1.py tests/unit/test_qre_contradiction_staleness_intelligence.py tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_behavior_thesis_evidence.py -q` (`27 passed`), `python -m reporting.qre_contradiction_hypothesis_lineage --write`, `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q` (`157 passed`), `python -m reporting.architecture_import_scan --format summary` (`forbidden_edge_count: 0`), `git diff --check`; checks green; post-merge validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched; contradiction and hypothesis lineage remained deterministic, read-only, context-only, and explicit about orphan and missing-lineage states.
- purpose: produce a deterministic inspectable lineage from source through next
  action without introducing unnecessary graph infrastructure.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017R done`.
- risk class: MEDIUM.
- target layer: packages `qre_research`, reporting, artifacts.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**lineage**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - graph database introduction without repository-backed necessity
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - lineage edges are deterministic and inspectable.
- next dependency: `ADE-QRE-017T`.

### ADE-QRE-017T - Evidence Decay

- queue id: `ADE-QRE-017T`
- title: Evidence Decay.
- status: `done`
- completion evidence: PR #660, merge SHA `da72a1d7f9e86ad9d07455e1757679f27cb4039c`; implementation added `reporting/qre_evidence_decay.py`, canonical doc `docs/governance/qre_evidence_decay.md`, and focused tests in `tests/unit/test_qre_evidence_decay.py`; validation: `python -m pytest tests/unit/test_qre_evidence_decay.py tests/unit/test_qre_contradiction_hypothesis_lineage.py tests/unit/test_qre_contradiction_staleness_intelligence.py tests/unit/test_qre_behavior_thesis_evidence.py -q` (`18 passed`), `python -m reporting.qre_evidence_decay --write`, `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q` (`157 passed`), `python -m reporting.architecture_import_scan --format summary` (`forbidden_edge_count: 0`), `git diff --check`; checks green; post-merge validation passed on `main`; frozen contracts unchanged; protected/execution paths untouched; evidence decay remained deterministic, read-only, context-only, and fail-closed where freshness or lineage could not actually support readiness.
- purpose: implement freshness and decay semantics without rewriting history.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017S done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_research`, policy read surfaces.
- expected files or file families:
  - `reporting/**decay**.py`
  - `packages/qre_research/**`
  - `tests/unit/**`
- forbidden files or file families:
  - silent stale-evidence trust claims
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - stale, contradicted, and active evidence states are explicit.
- next dependency: `ADE-QRE-017U`.

### ADE-QRE-017U - Operator Decision Report

- queue id: `ADE-QRE-017U`
- title: Operator Decision Report.
- status: `done`
- purpose: produce one concise operator report per thesis with a closed final
  decision vocabulary and exactly one next action.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017T done`.
- risk class: MEDIUM.
- target layer: reporting, artifacts, governance docs.
- expected files or file families:
  - `reporting/operator_decision_surface.py`
  - `reporting/qre_operator_closed_loop_report.py`
  - `tests/unit/**`
- forbidden files or file families:
  - approval mutation routes
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - final decisions are one of `SUPPORTED_FOR_REVIEW`, `REJECTED`,
    `INSUFFICIENT_EVIDENCE`, or `BLOCKED`.
- completion evidence: PR #663, merge SHA
  `d04502c5c64d87de0f59bed1a64e5e39eff0e7de`; implementation added
  `reporting/qre_operator_decision_report.py`, canonical doc
  `docs/governance/qre_operator_decision_report.md`, and focused tests in
  `tests/unit/test_qre_operator_decision_report.py`; validation:
  `python -m pytest tests/unit/test_qre_operator_decision_report.py tests/unit/test_qre_operator_closed_loop_report.py tests/unit/test_operator_decision_surface.py tests/unit/test_qre_evidence_decay.py tests/unit/test_qre_contradiction_hypothesis_lineage.py tests/unit/test_qre_behavior_thesis_registry.py tests/unit/test_qre_behavior_thesis_evidence.py -q` (`48 passed`),
  `python -m reporting.qre_operator_decision_report --write`,
  `python scripts/governance_lint.py`, `python -m pytest tests/architecture -q`
  (`157 passed`), `python -m reporting.architecture_import_scan --format summary`
  (`forbidden_edge_count: 0`), `git diff --check`; checks green; post-merge
  validation passed on `main`; frozen contracts unchanged; protected/execution
  paths untouched; operator decision rows remained deterministic, read-only,
  context-only, and non-authoritative.
- next dependency: `ADE-QRE-017V`.

### ADE-QRE-017V - Why-Explored, Why-Failed, Why-Blocked Surfaces

- queue id: `ADE-QRE-017V`
- title: Why-Explored, Why-Failed, Why-Blocked Surfaces.
- status: `ready`
- purpose: consolidate explanation surfaces into consistent evidence-linked
  outputs without adding mutation routes.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017U done`.
- risk class: MEDIUM.
- target layer: reporting, governance docs.
- expected files or file families:
  - `reporting/**why**.py`
  - `reporting/operator_decision_surface.py`
  - `tests/unit/**`
- forbidden files or file families:
  - approval buttons or mutation controls
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - explanation outputs are consistent and provenance-linked.
- next dependency: `ADE-QRE-017W`.

### ADE-QRE-017W - Campaign Portfolio and Signal-Density Planning

- queue id: `ADE-QRE-017W`
- title: Campaign Portfolio and Signal-Density Planning.
- status: `blocked until ADE-QRE-017V done`
- purpose: construct a bounded multi-hypothesis campaign portfolio using
  mechanistically distinct existing capabilities.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017V done`.
- risk class: MEDIUM.
- target layer: packages `qre_research`, reporting, governance docs.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**campaign**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - indicator-family expansion for breadth alone
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - portfolio is bounded, preregistration-ready, and signal-density planned.
- next dependency: `ADE-QRE-017X`.

### ADE-QRE-017X - Preregistered Campaign Manifest

- queue id: `ADE-QRE-017X`
- title: Preregistered Campaign Manifest.
- status: `blocked until ADE-QRE-017W done`
- purpose: freeze hypotheses, data identities, windows, costs, criteria,
  controls, and vocabularies before campaign execution.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017W done`.
- risk class: MEDIUM.
- target layer: reporting, packages `qre_artifacts`, governance docs.
- expected files or file families:
  - `reporting/qre_research_run_manifest.py`
  - `packages/qre_artifacts/**`
  - `tests/unit/**`
- forbidden files or file families:
  - post-OOS tuning
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - campaign input identity is immutable or content-addressed where
    repository-native.
- next dependency: `ADE-QRE-017Y`.

### ADE-QRE-017Y - Broad Campaign Execution

- queue id: `ADE-QRE-017Y`
- title: Broad Campaign Execution.
- status: `blocked until ADE-QRE-017X done`
- purpose: execute the preregistered campaign through existing QRE research
  execution paths and persist full stage-level accounting.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017X done`.
- risk class: HIGH.
- target layer: package-boundary QRE research execution, reporting, artifacts.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**campaign**.py`
  - `tests/unit/**`
  - `tests/integration/**`
- forbidden files or file families:
  - paper, shadow, live, broker, risk, execution, or capital-allocation paths
  - `.claude/**`
  - frozen contracts listed under `ADE-QRE-017`.
- validation required:
  - campaign outputs distinguish completed, rejected, insufficient evidence,
    blocked, timed out, errored, and not executed.
  - negative campaigns remain valid when fully explained.
- next dependency: `ADE-QRE-017Z`.

### ADE-QRE-017Z - Funnel Diagnosis After Broad Campaign

- queue id: `ADE-QRE-017Z`
- title: Funnel Diagnosis After Broad Campaign.
- status: `blocked until ADE-QRE-017Y done`
- purpose: diagnose the primary bottleneck after broad execution without
  changing criteria.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017Y done`.
- risk class: MEDIUM.
- target layer: reporting, governance docs, diagnostics.
- expected files or file families:
  - `reporting/**diagnosis**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - criteria changes during diagnosis
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - exactly one primary bottleneck is selected from the allowed diagnosis set.
- next dependency: `ADE-QRE-017AA`.

### ADE-QRE-017AA - Single-Class Recalibration

- queue id: `ADE-QRE-017AA`
- title: Single-Class Recalibration.
- status: `blocked until ADE-QRE-017Z done`
- purpose: allow one evidence-justified criterion-class change with a
  preregistered expected effect and regression conditions.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017Z done`.
- risk class: HIGH.
- target layer: reporting, packages `qre_research`, governance docs.
- expected files or file families:
  - `reporting/**recalibration**.py`
  - `packages/qre_research/**`
  - `tests/unit/**`
- forbidden files or file families:
  - survivor-targeting
  - hypothesis, data, window, universe, or preset changes
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - if evidence does not justify recalibration, record rejection or
    insufficient evidence instead of fabricating a change.
- next dependency: `ADE-QRE-017AB`.

### ADE-QRE-017AB - Same-Input Replay

- queue id: `ADE-QRE-017AB`
- title: Same-Input Replay.
- status: `blocked until ADE-QRE-017AA done`
- purpose: replay the campaign with the exact same inputs, permitting only the
  approved single criterion-class change.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017AA done`.
- risk class: HIGH.
- target layer: packages `qre_research`, reporting, artifacts.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**replay**.py`
  - `tests/unit/**`
  - `tests/integration/**`
- forbidden files or file families:
  - hidden input drift
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - complete before/after funnel comparison is explicit.
- next dependency: `ADE-QRE-017AC`.

### ADE-QRE-017AC - Repeated Independent OOS Evidence

- queue id: `ADE-QRE-017AC`
- title: Repeated Independent OOS Evidence.
- status: `blocked until ADE-QRE-017AB done`
- purpose: run independent unseen OOS repetitions where existing data permits
  and record precise blockers otherwise.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017AB done`.
- risk class: HIGH.
- target layer: packages `qre_research`, reporting, artifacts.
- expected files or file families:
  - `packages/qre_research/**`
  - `reporting/**oos**.py`
  - `tests/unit/**`
  - `tests/integration/**`
- forbidden files or file families:
  - relabeling prior OOS as independent evidence
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - independent evidence or the exact blocker is explicit per hypothesis.
- next dependency: `ADE-QRE-017AD`.

### ADE-QRE-017AD - Synthesis-Readiness Review

- queue id: `ADE-QRE-017AD`
- title: Synthesis-Readiness Review.
- status: `blocked until ADE-QRE-017AC done`
- purpose: produce the review-only final synthesis-readiness outcome without
  implementing synthesis.
- source document:
  `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
- depends on: `ADE-QRE-017AC done`.
- risk class: MEDIUM.
- target layer: governance docs, reporting, operator decision surfaces.
- expected files or file families:
  - `docs/governance/**`
  - `reporting/**synthesis**.py`
  - `tests/unit/**`
- forbidden files or file families:
  - synthesis implementation
  - `.claude/**`
  - frozen contracts and runtime paths listed under `ADE-QRE-017`.
- validation required:
  - allowed outcomes are exactly `CONTINUE_BLOCKED`,
    `ELIGIBLE_FOR_SEPARATE_SYNTHESIS_DESIGN_REVIEW`, or
    `INSUFFICIENT_EVIDENCE`.
  - synthesis remains blocked unless a separate later design review is
    explicitly selected.
- next dependency: none.
