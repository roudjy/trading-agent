# QRE Approved Bounded Source No OOS Trades

## Approved Scope

- approval manifest: `research/operator_approvals/qre_bounded_validation_approval_first_batch.v1.json`
- approval id: `qre_bounded_validation_first_batch_001`
- symbols: `AAPL`, `NVDA`
- preset: `trend_pullback_continuation_daily_v1`
- timeframe: `daily_v1`
- external fetch allowed: `false`
- real run allowed: `true`
- evidence acceptance allowed: `true`

## Accepted Evidence State

- accepted structured lineage count: `2`
- accepted structured OOS count: `0`
- evidence_complete_count: `0`
- campaign lineage blocker cleared for approved scope: `yes`
- remaining exact blocker for approved scope: `no_oos_evidence`

## OOS Rejection Result

- exact rejection reason: `non_positive_oos_trade_count`
- approved bounded local overlap window produced OOS trade counts of `0` for both approved candidates
- OOS window, metrics, and cost/slippage refs were present, but they were not sufficient for accepted OOS because the trade count stayed non-positive
- no external fetch was used

## Interpretation

The approved bounded source was sufficient to produce verifier-accepted structured lineage for the exact approved scope, but it did not produce acceptable structured OOS evidence. This is a genuine fail-closed result for the currently approved local source/window, not a metadata-mapping failure and not a clearance bug.

## External Fetch And Scope Decision

- external fetch required for this result: `no`
- different approved bounded source/window likely required for positive OOS evidence: `yes`
- current approval scope is insufficient to reach `evidence_complete_count > 0` without a different evidence-producing bounded source/window

## Recommended Next Operator Decision

`approve a different bounded validation source/window`
