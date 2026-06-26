# QRE Action Usefulness Tracking

- generated_at_utc: `2026-06-26T03:15:00Z`
- module_version: `ade-qre-017h-2026-06-26`

## Summary

- Action usefulness tracking compares current bounded recommendations against prior action-usefulness snapshots when available. It proves only repo-backed effects, leaves compute-saved and false-positive claims fail-closed when they are not action-specific, and appends bounded history so later runs can become truly comparative.
- action count: `28`
- current subject count: `97`
- prior snapshot available: `False`
- routing ready count: `2`
- sampling ready count: `2`
- global false-positive proxy rows: `0`
- final recommendation: `action_usefulness_tracking_ready`

## Action Rows

| Action | Current | Prior | Repeated | Resolved | Execution state | Useful outcome |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| collect_more_evidence | 2 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| collect_more_oos_window_evidence | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| collect_oos_evidence | 13 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| collect_screening_evidence | 9 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| eligible_for_readonly_routing | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | downstream_readiness_visible |
| expand_basket_coverage | 21 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| hold_no_action_until_evidence_improves | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| increase_timeframe_or_extend_sample_window | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_evaluation_survivor_gate | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_oos_return_coverage | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_policy_filter_inputs | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_screening_budget_and_worker_health | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_screening_instrumentation | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| inspect_synthesis_gate_evidence | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| investigate_no_safe_bounded_command | 4 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| materialize_lineage_from_existing_artifacts | 25 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| operator_review_unsupported_failure_shape | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| preserve_negative_result | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| preserve_negative_result_for_unstable_parameter_region | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| repair_data_coverage_before_research_action | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| repair_metric_emission | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| repair_policy_trace_consistency | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| repair_policy_trace_instrumentation | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| repair_screening_evidence_instrumentation | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| require_identity_resolution | 2 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| resolve_data_coverage_status | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| resolve_source_identity | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
| review_cost_assumptions | 1 | 0 | 0 | 0 | baseline_no_prior_snapshot | insufficient_evidence |
