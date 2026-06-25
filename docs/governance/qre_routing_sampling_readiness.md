# QRE Routing and Sampling Readiness

## 1. Summary
| Field | Value |
| --- | --- |
| routing candidates | 15 |
| sampling candidates | 15 |
| routing ready | 2 |
| sampling ready | 2 |
| shared ready | 2 |
| routing reason-record coverage | 100.0% |
| sampling reason-record coverage | 100.0% |
| final recommendation | readiness_population_materialized |
| exact next action | preserve_evidence_backed_ready_and_non_ready_states |

## 2. State counts
| State | Routing | Sampling |
| --- | --- | --- |
| ready | 2 | 2 |
| blocked | 1 | 1 |
| deferred | 12 | 12 |
| fail_closed | 0 | 0 |

## 3. Candidate examples
| Symbol | Preset | Routing | Sampling | Shared ready | Reason records | Primary reasons |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | trend_pullback_continuation_daily_v1 | ready (97) | ready (100) | yes | routing+sampling | evidence_ready_for_readonly_routing, sampling_ready_for_readonly_requirements |
| NVDA | trend_pullback_continuation_daily_v1 | ready (97) | ready (100) | yes | routing+sampling | evidence_ready_for_readonly_routing, sampling_ready_for_readonly_requirements |
| ASMI | relative_strength_vs_sector_daily_v1 | blocked (0) | blocked (0) | no | routing+sampling | source_identity_blocked |
| AMD | relative_strength_vs_region_daily_v1 | deferred (90) | deferred (90) | no | routing+sampling | oos_evidence_missing |
| ASML | trend_continuation_daily_v1 | deferred (90) | deferred (90) | no | routing+sampling | oos_evidence_missing |
| MSFT | relative_strength_vs_region_daily_v1 | deferred (90) | deferred (90) | no | routing+sampling | oos_evidence_missing |
| TSM | vol_compression_breakout_daily_v1 | deferred (32) | deferred (32) | no | routing+sampling | source_or_cache_coverage_missing |
| ADYEN | relative_strength_vs_sector_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| BABA | post_shock_stabilization_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| BESI | trend_continuation_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| QQQ | index_regime_filter_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| SMH | vol_compression_breakout_4h_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| SONY | vol_compression_breakout_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| SPY | vol_compression_breakout_4h_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |
| TM | post_shock_stabilization_daily_v1 | deferred (15) | deferred (15) | no | routing+sampling | source_or_cache_coverage_missing |

## 4. Doctrine
- Routing and sampling readiness are evidence-derived, read-only surfaces.
- Missing reason-record support, missing basket evidence, or missing real readiness inputs fail closed.
- This report does not activate routing, sampling, paper, shadow, live, broker, risk, or execution behavior.
