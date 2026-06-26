# QRE Funnel Census and Threshold-Distance Audit

## 1. Summary
- snapshot_id: `657a8846bf6ed2c60747ed75e85065979913fe81787b64284dba3bda83512ed8`
- raw_candidate_count: 2
- screening_pass_count: 6
- screening_reject_count: 9
- validation_completed_count: 6
- oos_accepted_count: 1
- campaign_primary_limitation: insufficient_trades
- final_recommendation: funnel_threshold_audit_ready

## 2. Criterion recommendations
| Criterion | Metric | Threshold | Pass | Fail | Recommendation |
| --- | --- | --- | ---: | ---: | --- |
| drawdown_within_limit | max_drawdown | 0.45 | 15 | 0 | keep |
| expectancy_above_zero | expectancy | 0.0 | 6 | 9 | insufficient_evidence_to_change |
| profit_factor_at_or_above_floor | profit_factor | 1.05 | 6 | 9 | insufficient_evidence_to_change |
| sufficient_trades | totaal_trades | 10.0 | 6 | 9 | stratify |
