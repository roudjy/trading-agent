# QRE Trusted Research Maturity Matrix

## 1. Summary
- Current QRE maturity is uneven: the repo already has integrated and decision-useful read-only surfaces for basket diagnosis, readiness, failure actions, explanations, memory, and KPI summaries, but behavior-thesis discipline, contradiction/decay visibility, broad preregistered campaign evidence, and repeated independent OOS closure remain below operator-trusted maturity.
- overall_baseline: `mixed_decision_useful_pockets_not_operator_trusted`
- highest_level_present: `decision_useful_capability`
- operator_trusted_surface_count: `0`
- evidence_authoritative_surface_count: `0`
- planning_gap_scaffold_count: `11`
- planning_gap_working_count: `9`

## 2. Level counts
| Level | Count |
| --- | --- |
| scaffold | 3 |
| populated_working_capability | 2 |
| integrated_capability | 2 |
| repeatable_evidence_capability | 2 |
| decision_useful_capability | 5 |
| operator_trusted_capability | 0 |
| evidence_authoritative_capability | 0 |

## 3. Top blockers
| Blocker | Count |
| --- | --- |
| source_identity_blocked | 4 |
| campaign_lineage_missing | 3 |
| oos_evidence_missing | 3 |
| source_or_cache_coverage_missing | 3 |
| cache_coverage_missing | 1 |
| campaign_execution_not_completed | 1 |
| candidate_lineage_missing | 1 |
| context_only_memory_not_authority | 1 |

## 4. Surface matrix
| Surface | Level | Workstream | Phase | Key metrics | Why not higher |
| --- | --- | --- | --- | --- | --- |
| Audit gap closure planning surface | populated_working_capability | A. Research Loop Maturity and Evidence Density | Phase 0 - Baseline Reconciliation | audit_item_count=20, gap_closure_pr_count=19 | The surface records a deterministic closure plan, but it is explicitly planning-only and does not itself materialize mature research evidence. |
| Real basket evidence coverage | repeatable_evidence_capability | A. Research Loop Maturity and Evidence Density | Phase 0 - Baseline Reconciliation | basket_inventory_count=15, complete_count=2, partial_count=4, thin_count=8 | Coverage is real and repeatable, but most baskets remain partial or thin and the dominant blockers are still source/cache breadth, lineage, and OOS completeness. |
| Durable reason records | repeatable_evidence_capability | A. Research Loop Maturity and Evidence Density | Phase 0 - Baseline Reconciliation | record_count=45, basket_records=15, routing_records=15, sampling_records=15 | Reason records are already deterministic and evidence-linked, but the broader producer estate is not yet uniformly normalized or promoted into a complete authority-settled manifest. |
| Reason-record producer audit | integrated_capability | A. Research Loop Maturity and Evidence Density | Phase 0 - Baseline Reconciliation | producer_count=6, expected_subject_count=4240, subjects_with_evidence_refs=4195, reason_record_coverage_pct=98.94 | The audit integrates multiple producers and quantifies gaps, but the repo still reports an empty manifest total and incomplete producer-level evidence references. |
| Routing readiness from real basket evidence | decision_useful_capability | F. Routing and Sampling Calibration | Phase 0 - Baseline Reconciliation | basket_inventory_count=15, ready_count=2, blocked_count=1, deferred_count=12 | The surface already makes bounded routing decisions, but only two baskets are ready and the broader basket population is still dominated by deferred or blocked evidence states. |
| Sampling readiness from routing-ready evidence | decision_useful_capability | F. Routing and Sampling Calibration | Phase 0 - Baseline Reconciliation | basket_inventory_count=15, ready_count=2, blocked_count=1, deferred_count=12 | Sampling recommendations are deterministic and bounded, but they currently inherit the same coverage and OOS gaps that keep most baskets out of the ready state. |
| Failure-to-action mapping | decision_useful_capability | E. Actionable Failure Intelligence | Phase 2 - Failure and Funnel Understanding | actionable_count=15, non_actionable_count=0, distinct_action_count=4, distinct_blocker_count=4 | The mapping already yields one bounded next action per current blocker class, but it remains read-only advisory evidence and is not yet backed by broad campaign, replay, or repeated OOS results. |
| Candidate explanation rows | decision_useful_capability | H. Operator-Trusted Research Observability | Phase 7 - Operator Trust | candidate_count=15, safe_next_action_count=4, paper_blocked_count=0, synthesis_blocked_count=0 | Operator explanations are readable and deterministic, but paper/synthesis remain fail-closed and the current surfaces stop at research context rather than operator-trusted final decisions. |
| Research memory coverage | integrated_capability | G. Epistemological Research Memory | Phase 6 - Research Memory Maturity | indexed_entry_count=75, indexed_basket_count=15, indexed_reason_record_count=45, ready_ontology_count=6 | The repo already indexes memory across baskets, failures, and reason records, but most ontology classifications still resolve to unknown and the memory layer explicitly remains context-only. |
| Trusted-loop operator KPI projection | decision_useful_capability | H. Operator-Trusted Research Observability | Phase 7 - Operator Trust | basket_inventory_count=15, routing_ready_count=2, sampling_ready_count=2, reason_record_count=45 | The KPI layer is decision-useful and already surfaces a trust candidate state, but it still aggregates a mostly thin basket population and does not yet meet the program's operator-trusted bar. |
| Behavior thesis registry | scaffold | D. Behavior Thesis Engine | Phase 4 - Behavior Thesis Maturity | preset_hypothesis_pairs_present=1 | The production discovery catalog already names hypotheses and behavior families, but the repo does not yet have a dedicated thesis registry with explicit mechanism, falsification, and preregistered test plans. |
| Preregistered campaign and replay closure | populated_working_capability | I. Broad Preregistered Campaign | Phase 8 - Broad Campaign Execution | working_closure_engine_present=1 | The repository already contains deterministic closure and disposition-memory scaffolds for preregistered campaign evidence, but no current broad campaign artifact has been executed through them. |
| Contradiction visibility and evidence decay | scaffold | G. Epistemological Research Memory | Phase 6 - Research Memory Maturity | current_repo_backed_operator_surface_count=0 | The repo contains relevant scaffolds, but the current state inspection does not yet expose a mature operator-facing contradiction graph or explicit evidence-decay decision surface. |
| Repeated independent OOS closure | scaffold | J. Controlled Learning and Replay | Phase 9 - Controlled Recalibration and Replay | independent_oos_runs_materialized=0 | The doctrine and closure scaffolds are present, but no current repository artifact demonstrates repeated independent OOS evidence under the ADE-QRE-017 program. |

## 5. Evidence refs
- `audit_gap_closure_plan`: `research/qre_audit_gap_closure_plan.py`, `docs/roadmap/qre_audit_gap_closure_plan.md`
- `real_basket_evidence_coverage`: `research/qre_real_basket_evidence_coverage.py`, `logs/qre_data_source_quality_readiness/latest.json`, `logs/qre_data_cache_manifest/latest.json`, `research/screening_evidence_latest.v1.json`, `research/campaign_registry_latest.v1.json`, `research/candidate_registry_latest.v1.json`
- `reason_records_v1`: `research/qre_reason_records_v1.py`, `research/qre_real_basket_diagnosis.py`, `research/qre_routing_readiness_from_basket.py`, `research/qre_sampling_readiness_from_basket.py`
- `reason_record_audit`: `research/qre_reason_record_audit.py`, `logs/qre_reason_record_audit/latest.json`, `logs/reason_records/manifest.v1.json`
- `routing_readiness`: `research/qre_routing_readiness_from_basket.py`, `research/qre_real_basket_evidence_coverage.py`
- `sampling_readiness`: `research/qre_sampling_readiness_from_basket.py`, `research/qre_routing_readiness_from_basket.py`
- `failure_action_mapping`: `research/qre_failure_action_from_basket.py`, `research/qre_reason_records_v1.py`
- `candidate_explanation_rows`: `research/qre_candidate_explanation_rows.py`, `research/qre_failure_action_from_basket.py`, `research/qre_reason_records_v1.py`
- `research_memory_coverage`: `research/qre_research_memory_coverage.py`, `research/qre_reason_records_v1.py`, `research/qre_failure_action_from_basket.py`
- `trusted_loop_operator_kpis`: `research/qre_trusted_loop_operator_kpis.py`, `research/qre_real_basket_diagnosis.py`, `research/qre_real_basket_evidence_coverage.py`, `research/qre_routing_readiness_from_basket.py`, `research/qre_sampling_readiness_from_basket.py`, `research/qre_reason_records_v1.py`
- `behavior_thesis_registry`: `research/production_discovery_catalog.py`, `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`
- `preregistered_campaign_closure`: `research/qre_multiwindow_evidence_closure.py`, `research/qre_hypothesis_disposition_memory.py`, `tests/unit/test_qre_hypothesis_disposition_memory.py`
- `contradiction_and_decay`: `research/qre_contradiction_staleness_intelligence.py`, `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`
- `independent_oos_repetition`: `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`, `research/qre_multiwindow_evidence_closure.py`

## 6. Safety
- This report is read-only.
- Evidence-authoritative status is never inferred from file existence alone.
- Paper, shadow, live, broker, risk, execution, and capital-allocation behavior remain out of scope.
