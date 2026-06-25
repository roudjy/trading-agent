# QRE Evidence Density Inventory

- generated_at_utc: `2026-06-25T08:43:08Z`
- evidence_class_count: `14`
- final_recommendation: `evidence_density_inventory_ready`

## Inventory

| evidence_class | state | fail_closed | producers | consumers | blockers |
| --- | --- | --- | --- | --- | --- |
| source_identity | blocked | yes | 1 | 3 | source_identity_blocked |
| source_quality | thin | yes | 1 | 3 | source_quality_rows_missing, source_quality_not_ready |
| cache_coverage | thin | yes | 1 | 3 | cache_coverage_missing, cache_coverage_not_ready |
| screening_evidence | partial | yes | 1 | 3 | screening_evidence_missing |
| validation_oos_evidence | thin | yes | 1 | 3 | oos_evidence_missing, oos_evidence_unknown, no_oos_evidence, insufficient_oos_evidence |
| campaign_lineage | blocked | yes | 1 | 3 | campaign_lineage_missing |
| candidate_lineage | thin | yes | 1 | 2 | candidate_lineage_missing |
| reason_records | complete | yes | 2 | 3 | reason_record_coverage_incomplete |
| routing_readiness | thin | yes | 1 | 3 | routing_not_ready |
| sampling_readiness | thin | yes | 1 | 3 | sampling_not_ready |
| failure_action_mapping | complete | no | 1 | 3 | non_actionable_failure |
| candidate_explanations | complete | yes | 1 | 3 | paper_blocked, synthesis_blocked |
| research_memory | complete | no | 1 | 2 | memory_index_missing |
| trusted_loop_kpis | complete | no | 1 | 3 | operator_kpi_projection_incomplete |

## State Counts

| population_state | count |
| --- | --- |
| blocked | 2 |
| complete | 5 |
| partial | 1 |
| thin | 6 |

## Top Blockers

| blocker_code | count |
| --- | --- |
| source_identity_blocked | 1 |
| source_quality_rows_missing | 1 |
| source_quality_not_ready | 1 |
| cache_coverage_missing | 1 |
| cache_coverage_not_ready | 1 |
| screening_evidence_missing | 1 |
| oos_evidence_missing | 1 |
| oos_evidence_unknown | 1 |
| no_oos_evidence | 1 |
| insufficient_oos_evidence | 1 |
