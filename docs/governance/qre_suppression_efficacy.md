# QRE Suppression Efficacy

This surface measures only what the current repository artifacts can prove about dead-zone and duplicate suppression.

| metric_id | status | value |
| --- | --- | --- |
| eligible_comparison_population | observed | 12 |
| duplicate_candidates_detected | observed | 0 |
| duplicate_campaigns_detected | observed | 0 |
| duplicate_campaign_pressure_visible | observed | 1 |
| repeated_rejected_scopes_prevented | observed | 2 |
| dead_zone_selections_avoided | observed | 5 |
| evaluations_avoided | observed | 2 |
| compute_avoided | insufficient_evidence | unavailable |
| useful_outcome_rate_with_suppression | insufficient_evidence | unavailable |
| useful_outcome_rate_valid_baseline | insufficient_evidence | unavailable |
| false_suppression_rate | insufficient_evidence | unavailable |
| provenance_completeness | measured | 1.0 |

- mechanics_exist: `True`
- evidence_populated: `True`
- efficacy_measured: `False`
- efficacy_evidence_authoritative: `False`
- final_recommendation: `suppression_efficacy_insufficient_baseline`

Current routing and sampling baselines are reused as context only. They are not treated as a suppression-vs-no-suppression comparator.
