# QRE Audit Gap Closure Plan

Generated at UTC: `2026-06-15T00:00:00Z`

## Summary

PR0 records the audit gap closure roadmap only. It keeps QRE in research-only planning mode and does not unlock strategy synthesis, paper, shadow, live, broker, risk, or execution behavior.

This artifact is PR0 of the roadmap. It is a deterministic, read-only planning surface and is not evidence that QRE is operator-trusted.

## Current-To-Target Matrix

| # | Audit item | Current maturity | Target maturity | Closure PRs | Target capability |
| --- | --- | --- | --- | --- | --- |
| 1 | PIT/report-lag/restatement | SCAFFOLD | OPERATOR_TRUSTED | PR2, PR8, PR18 | multi-source historical accounting engine |
| 2 | Factor field coverage | SCAFFOLD | OPERATOR_TRUSTED | PR4, PR5, PR8, PR18 | approved-provider factor coverage matrix |
| 3 | SEC Companyfacts manifest | SCAFFOLD | WORKING_CAPABILITY | PR1, PR5, PR7 | active read-only SEC source candidate with gates |
| 4 | OpenFIGI identity manifest | SCAFFOLD | WORKING_CAPABILITY | PR1, PR3, PR5, PR10 | production-grade symbology resolver input |
| 5 | Grid lineage bridge | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR8, PR9, PR17, PR18 | source to hypothesis to campaign to evidence graph |
| 6 | Source/cache sidecars | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR1, PR6, PR8, PR18 | deterministic sidecar materialization |
| 7 | Local grid refresh | WORKING_CAPABILITY | WORKING_CAPABILITY | PR6, PR8 | controlled refresh discipline |
| 8 | Targeted readiness rerun | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR8, PR15, PR16, PR18 | real-data readiness rerun gate |
| 9 | Candidate blockers | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR8, PR17, PR18 | high-density actionable blockers |
| 10 | Basket closure | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR8, PR17, PR18 | evidence-complete closure gate |
| 11 | Research memory | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR9, PR11, PR18 | graph-backed research memory |
| 12 | Ontology | SCAFFOLD | WORKING_CAPABILITY | PR9, PR10, PR11 | mature canonical ontology |
| 13 | Entity resolution | SCAFFOLD | OPERATOR_TRUSTED | PR3, PR9, PR10, PR18 | canonical identity resolution |
| 14 | Related failure retrieval | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR9, PR11, PR17, PR18 | deterministic RRF/hybrid retrieval |
| 15 | Null model baseline | SCAFFOLD | OPERATOR_TRUSTED | PR12, PR13, PR14, PR18 | broader no-edge baseline suite |
| 16 | State transitions | SCAFFOLD | WORKING_CAPABILITY | PR12, PR13 | state/sequence/regime-duration diagnostics |
| 17 | Tail/entropy | SCAFFOLD | WORKING_CAPABILITY | PR12, PR14 | evidence-dense tail/entropy diagnostics |
| 18 | Routing calibration | SCAFFOLD | OPERATOR_TRUSTED | PR8, PR12, PR13, PR14, PR15, PR18 | real-evidence routing calibration |
| 19 | Sampling calibration | SCAFFOLD | OPERATOR_TRUSTED | PR8, PR12, PR13, PR14, PR16, PR18 | real-evidence sampling calibration |
| 20 | Trusted-loop packet | WORKING_CAPABILITY | OPERATOR_TRUSTED | PR17, PR18 | evidence-backed operator-trust verdict |

## PR Sequence

| PR | Title | Objective | Depends on | Approval |
| --- | --- | --- | --- | --- |
| PR0 | Audit gap closure plan and maturity matrix | Add generated roadmap artifact aligned with repo inspection. | none | normal PR |
| PR1 | Source lifecycle and quality gate contract | Implement strict source lifecycle and transition gates. | PR0 | operator review for lifecycle semantics |
| PR2 | Historical accounting foundation | PIT/report-lag/restatement snapshot contracts. | PR1 | operator review |
| PR3 | Symbology resolver foundation | Canonical IDs, aliases, and ambiguity blocking. | PR1 | normal PR |
| PR4 | Factor coverage matrix | Provider to field to factor coverage and freshness. | PR1, PR2, PR3 | normal PR |
| PR5 | SEC/OpenFIGI manifest hardening | Promote manifests to quality-gated readiness inputs, not alpha. | PR1, PR2, PR3, PR4 | operator source review |
| PR6 | Cache and throughput manifests | Parquet snapshot contract, DuckDB catalog manifest, Polars-use policy. | PR1, PR2, PR3, PR4, PR5 | normal PR |
| PR7 | Source usefulness ledger | Track source usefulness, failures, and cost savings. | PR5, PR6 | normal PR |
| PR8 | Lineage graph v1 | Source to normalized data to factor to hypothesis to campaign to evidence lineage. | PR2, PR3, PR4, PR5, PR6, PR7 | normal PR |
| PR9 | Knowledge graph and contradiction visibility | Add research memory graph and contradiction edges. | PR8 | normal PR |
| PR10 | Entity resolution hardening | Canonical cross-artifact entity resolver. | PR3, PR9 | normal PR |
| PR11 | Retrieval maturity | Keyword plus metadata plus graph-neighbor retrieval with RRF scaffold. | PR9, PR10 | normal PR |
| PR12 | Null/no-edge baseline suite | Random walk, shuffled/surrogate, martingale-like baseline reports. | PR8, PR11 | normal PR |
| PR13 | State/sequence/regime duration | State transition and dwell-time diagnostics. | PR12 | normal PR |
| PR14 | Tail/entropy evidence density | Expand diagnostics with real evidence density and null challenges. | PR12, PR13 | normal PR |
| PR15 | Routing calibration on real evidence | Use source/data/readiness/diagnostic evidence for routing recommendations. | PR8, PR9, PR10, PR11, PR12, PR13, PR14 | normal PR |
| PR16 | Sampling calibration on real evidence | Coverage/source/null/regime-aware sampling recommendations. | PR8, PR9, PR10, PR11, PR12, PR13, PR14, PR15 | normal PR |
| PR17 | Evidence-complete basket closure | High-density blockers, reason records, and closure criteria. | PR8, PR9, PR10, PR11, PR12, PR13, PR14, PR15, PR16 | operator review |
| PR18 | Operator-trust review packet v3 | Evidence-backed Level 1/2/3 verdict and exact next action. | PR17 | operator trust decision |

## Dependency Graph

- source_lifecycle_before_active_sources: Source lifecycle and quality gates must pass before active read-only source usage.
- symbology_before_factor_agreement: Symbology resolver must exist before broad factor coverage and cross-source agreement.
- historical_accounting_before_pit_factors: Historical accounting must exist before PIT-aware factor evaluation.
- cache_manifest_before_throughput_metrics: Cache manifest must exist before throughput metrics.
- usefulness_after_quality_and_cache: Source usefulness ledger follows source quality and cache manifests.
- lineage_before_trust_packet: Lineage graph must precede contradiction visibility and operator-trust packet.
- entity_resolution_before_retrieval_confidence: Entity resolution must precede mature retrieval and lineage confidence.
- null_baselines_before_diagnostic_influence: Null baselines must precede state/tail/entropy influence on routing or sampling.
- real_evidence_before_operator_trusted_calibration: Real evidence runs must precede operator-trusted routing or sampling calibration.
- reason_density_before_final_verdict: Reason-record density and basket closure must precede final operator-trust verdict.

## Blocked Shortcuts

- source_to_alpha
- cache_to_trade
- diagnostic_to_trade
- retrieval_to_authority
- knowledge_graph_to_truth
- identity_ambiguity_to_escalation
- throughput_bypasses_source_quality
- null_baseline_promotes_candidate_alone
- routing_mutates_queue_or_campaign
- sampling_uses_stochastic_bruteforce

## Forbidden Paths

- strategy_synthesis
- shadow_activation
- paper_activation
- live_activation
- broker_integration
- risk_authority
- execution_behavior
- dashboard_mutation_routes
- hidden_ml_rl_selectors
- stochastic_mutation
- generated_strategy_code

## Safety Flags

- safe_to_strategy_synthesis: False
- safe_to_shadow: False
- safe_to_paper: False
- safe_to_live: False

## Recommended Next PR

After PR0, build PR1: `feat: add QRE source lifecycle and quality gate contract`.

Reason: source lifecycle and quality gates are the dependency root for approved providers, symbology, factor coverage, PIT accounting, cache trust, routing/sampling evidence, and final operator trust.
