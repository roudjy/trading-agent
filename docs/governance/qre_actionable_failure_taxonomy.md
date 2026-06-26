# QRE Actionable Failure Taxonomy

- generated_at_utc: `2026-06-26T02:10:00Z`
- module_version: `ade-qre-017g-2026-06-26`

## Summary

- Actionable failure taxonomy consolidates current screening, basket, and minimal failure-action surfaces into one read-only view. Supported classes carry exactly one bounded next action; thin or empty evidence remains explicit and fails closed.
- supported failure classes: `6`
- insufficient-evidence classes: `19`
- all supported classes have exactly one next action: `True`
- final recommendation: `actionable_failure_taxonomy_ready`

## Taxonomy Rows

| Surface | Failure class | Count | Evidence status | Next action | Supported |
| --- | --- | ---: | --- | --- | --- |
| failure_action_mapping_minimal | no_failure_inputs | 0 | insufficient_evidence | collect_more_evidence | false |
| qre_failure_action_from_basket | oos_evidence_missing | 3 | supported | collect_more_evidence | true |
| qre_failure_action_from_basket | ready_for_readonly_research | 2 | supported | eligible_for_readonly_routing | true |
| qre_failure_action_from_basket | source_identity_blocked | 1 | supported | require_identity_resolution | true |
| qre_failure_action_from_basket | source_or_cache_coverage_missing | 9 | supported | expand_basket_coverage | true |
| screening_failure_attribution | cost_sensitivity | 0 | not_observed | review_cost_assumptions | false |
| screening_failure_attribution | data_coverage_gap | 0 | not_observed | repair_data_coverage_before_research_action | false |
| screening_failure_attribution | data_coverage_unknown | 0 | not_observed | resolve_data_coverage_status | false |
| screening_failure_attribution | identity_unresolved | 0 | not_observed | resolve_source_identity | false |
| screening_failure_attribution | incomplete_policy_trace | 0 | not_observed | repair_policy_trace_instrumentation | false |
| screening_failure_attribution | insufficient_oos_window | 0 | not_observed | collect_more_oos_window_evidence | false |
| screening_failure_attribution | insufficient_trades | 16 | supported | increase_timeframe_or_extend_sample_window | true |
| screening_failure_attribution | missing_diagnostics | 0 | not_observed | inspect_screening_instrumentation | false |
| screening_failure_attribution | missing_metric_field | 0 | not_observed | repair_metric_emission | false |
| screening_failure_attribution | missing_screening_evidence | 0 | not_observed | repair_screening_evidence_instrumentation | false |
| screening_failure_attribution | no_candidate_after_policy_filter | 0 | not_observed | inspect_policy_filter_inputs | false |
| screening_failure_attribution | no_oos_returns | 0 | not_observed | inspect_oos_return_coverage | false |
| screening_failure_attribution | no_survivor_after_eval | 0 | not_observed | inspect_evaluation_survivor_gate | false |
| screening_failure_attribution | parameter_instability | 0 | not_observed | preserve_negative_result_for_unstable_parameter_region | false |
| screening_failure_attribution | policy_trace_inconsistent | 0 | not_observed | repair_policy_trace_consistency | false |
| screening_failure_attribution | strict_gate_rejection | 12 | supported | preserve_negative_result | true |
| screening_failure_attribution | synthesis_gate_blocked | 0 | not_observed | inspect_synthesis_gate_evidence | false |
| screening_failure_attribution | timeout | 0 | not_observed | inspect_screening_budget_and_worker_health | false |
| screening_failure_attribution | unknown_screening_failure | 0 | not_observed | hold_no_action_until_evidence_improves | false |
| screening_failure_attribution | unsupported_failure_shape | 0 | not_observed | operator_review_unsupported_failure_shape | false |
