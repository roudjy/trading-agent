# QRE Routing Baseline Comparison

This surface compares the current context-only router ordering against simple deterministic baselines.

| baseline_id | usefulness | top3_opportunity_capture | top3_high_priority_count |
| --- | --- | --- | --- |
| blocked_reason_count | 2.022 | 0.734 | 1 |
| current_routing_score | 2.022 | 0.734 | 1 |
| fifo_artifact_order | 2.022 | 0.734 | 1 |
| lexical_direction_id | 2.022 | 0.734 | 1 |
| lexical_behavior_id | 1.373 | 0.313 | 0 |

- source router status: `ready`
- source opportunity status: `ready`

Current routing remains context only and does not authorize campaign execution.
