# ADE-QUEUE-001 - Post-Package QRE/ADE Work Queue

> Status: bounded queue proposal for operator review.
>
> Primary source: `docs/strategy/QRE_ADE_How_To_Target_State_Roadmap.md`.
> Supporting sources: `docs/roadmap/Roadmap v6.md`,
> `docs/governance/roadmap_scope_status.md`, and
> `docs/architecture/PACKAGE-MIGRATION-010-package-migration-closure-decision.md`.
>
> This document does not activate Addendum 1, Addendum 2, Addendum 3,
> v4.x Shadow, v5.x Paper, v6.x Live, or any live/paper/shadow/risk/broker/
> execution behavior. It also does not update `docs/development_work_queue/seed.jsonl`.

## Queue Selection Rules

- Work starts from the post-package QRE Feature Build Track.
- `QRE_ADE_How_To_Target_State_Roadmap.md` is the queue's primary product/research source.
- The first executable item must improve research evidence or diagnostics before any strategy synthesis.
- Addendum 1, Addendum 2, and Addendum 3 remain reference-only unless a future operator-approved ADR activates a specific subsection.
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
- completion evidence: implemented read-only local cache manifest schema and coverage reporter with row counts, min/max timestamps, content hashes, deterministic sidecar writer, and fail-closed missing-manifest status; local targeted tests and architecture scanner passed in the implementation branch; PR/merge evidence to be recorded by the next queue item after merge.
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
- status: `ready`
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
- status: `deferred`
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
- status: `deferred`
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
- status: `deferred`
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
- status: `operator_review`
- doel: decide whether strategy synthesis or new research capability is eligible after evidence, data, memory, diagnostics, and observability mature.
- bron uit target-state roadmap: phase order "Pas daarna"; lessons "Hypothesis first, strategy second"; section 18 "Wat voorlopig bewust niet doen".
- scope: operator review of KPIs and evidence only; define whether a future strategy/research capability queue item is allowed.
- verboden scope: writing new strategy code, inventing strategies, activating paper/shadow/live, changing registry, bypassing frozen contracts.
- files likely touched: docs-only decision record or ADR if the operator authorizes next capability.
- tests/validation: evidence pack references prior queue outputs and scanner summary; no code tests unless a later scoped implementation is approved.
- merge/deploy criteria: explicit operator decision with promote/retire criteria and bounded follow-up scope.
- stop condition: unknown failure/data/memory/observability evidence is still insufficient.
- expected next queue item: no eligible implementation item until operator approval.
