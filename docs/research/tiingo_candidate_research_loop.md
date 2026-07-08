# Tiingo Candidate Research Loop

## Purpose

This PR closes a research-only mini-loop from admitted Tiingo hypothesis seeds to candidate specs, screening results, feedback records, and next-run feedback consumption.

The module is an observability and research-screening bridge. It consumes the governed Tiingo hypothesis lifecycle artifact and turns admitted lifecycle records into deterministic research-only candidate specs, screens those specs against local Tiingo bars, writes feedback records, and lets a later run consume that feedback.

## Scope

The loop is:

```text
Tiingo hypothesis lifecycle artifact
-> stable seed input contract
-> deterministic research-only candidate spec
-> screening metrics and null controls
-> feedback record
-> next-run feedback consumption
```

The implementation lives in:

```text
research/qre_tiingo_candidate_research_loop.py
```

Default mode prints JSON and writes nothing:

```powershell
python -m research.qre_tiingo_candidate_research_loop
```

Write mode writes only:

```text
logs/qre_tiingo_candidate_research_loop/
```

## What This PR Builds

- stable input contracts from admitted Tiingo lifecycle records
- deterministic research-only candidate specs for the five admitted Tiingo feature families
- screening metrics over local Tiingo bars
- seeded shuffled-selection null controls
- equal-weight benchmark comparison
- feedback records for retain, reject, modify, block, or insufficient-evidence outcomes
- next-run feedback consumption that can retain, suppress, modify, defer, or block candidate handling
- JSONL sidecars and an operator summary
- daily-digest-ready input block for a later digest integration PR

## What This PR Does Not Build

This does not create validation-ready strategies, paper/shadow/live readiness, trading signals, orders, broker instructions, or risk approvals.

It also does not:

- call `research.run_research`
- call a campaign launcher
- register strategies
- promote candidates
- start validation
- enable paper mode
- enable shadow mode
- enable live mode
- create orders or positions
- grant broker, risk, or trading authority
- mutate `research/research_latest.json`
- mutate `research/strategy_matrix.csv`

## Input Contracts

The module consumes:

```text
logs/qre_tiingo_hypothesis_lifecycle/latest.json
```

It fails closed unless the lifecycle artifact is present, well-formed, from `qre_tiingo_hypothesis_lifecycle`, has `summary.lifecycle_verdict=pass_research_only_admission_boundary`, has `summary.daily_digest_ready=true`, and keeps all lifecycle authority flags false.

Only admitted lifecycle records become contracts. Rejected or blocked records are skipped. Contract IDs are deterministic and based on the hypothesis seed ID, source hypothesis ID, source snapshot ID, feature family, and source hypothesis digest.

## Candidate Materialization

Each admitted input contract materializes at most one v1 research-only candidate spec unless `--max-candidates` limits it or prior feedback suppresses it.

Implemented feature-family templates:

- `cross_sectional_momentum`
- `risk_on_risk_off_regime`
- `defensive_rotation`
- `volatility_compression_breakout`
- `mean_reversion_after_extreme_dispersion`

Unknown families are blocked with `blocked_unknown_candidate_family`.

Candidate specs are not executable strategy registrations. They keep:

```text
research_only=true
screening_only=true
not_trade_signal=true
trading_authority=false
creates_orders=false
```

## Screening Metrics

Screening uses local Tiingo bars only. It does not download data or call external APIs.

The screening protocol is:

```text
tiingo_research_candidate_screening_v1
```

Metrics include:

- observation count
- rebalance count
- selection count
- candidate total return
- equal-weight benchmark total return
- excess return
- annualized return
- annualized volatility
- sharpe-like score
- max drawdown
- win rate
- turnover proxy

Minimum evidence gates require at least 252 observations, 12 rebalance windows, 16 null iterations, and finite candidate and benchmark metrics.

## Null Controls

Each screened candidate receives seeded null controls:

- `shuffled_selection_null`
- `equal_weight_benchmark`

The shuffled-selection null is deterministic for a fixed seed and changes when the seed changes.

## Feedback Records

Each screening result maps to one feedback record:

```text
screening_pass -> retain_for_more_screening
null_not_beaten -> modify_candidate_later
screening_fail -> reject_candidate_for_now
insufficient_evidence -> insufficient_evidence
blocked_unsafe_input -> block_candidate
```

Feedback records are consumable by the next run and keep:

```text
research_only=true
trading_authority=false
```

## Next-Run Feedback Consumption

If `--prior-feedback-input` exists, the module reads feedback records before writing any new outputs.

Prior feedback changes later candidate handling:

- retain feedback rematerializes the same candidate
- reject feedback suppresses the same candidate
- modify feedback creates a deterministic modified candidate variant
- insufficient-evidence feedback defers screening and records the need for more data
- block feedback blocks materialization

This is the minimum closed research-only loop for this phase.

## Output Artifacts

Write mode produces:

```text
logs/qre_tiingo_candidate_research_loop/latest.json
logs/qre_tiingo_candidate_research_loop/input_contracts.jsonl
logs/qre_tiingo_candidate_research_loop/candidate_specs.jsonl
logs/qre_tiingo_candidate_research_loop/screening_results.jsonl
logs/qre_tiingo_candidate_research_loop/feedback_records.jsonl
logs/qre_tiingo_candidate_research_loop/operator_summary.md
```

Generated logs are not committed.

## Safety Boundaries

Every report keeps:

```text
research_only=true
screening_only=true
trading_authority=false
creates_orders=false
broker_authority=false
risk_authority=false
promotes_candidates=false
registers_strategy=false
validation_authority=false
paper_authority=false
shadow_authority=false
live_authority=false
```

The operator summary ends with:

```text
No orders were created. No broker/risk authority exists. No validation, promotion, strategy registration, paper, shadow, or live authority was granted.
```

## Relationship To QRE Feedback-Loop Closure

This closes a narrow research-only feedback loop for Tiingo-derived hypotheses. It does not close the broader QRE feedback loop across strategy registration, validation, paper readiness, shadow readiness, or live readiness.

The loop is deliberately bounded to candidate screening and feedback consumption. It provides a deterministic proof that research feedback can affect the next candidate handling decision without granting active trading authority.

## Next Safe PR

1. include Tiingo candidate research loop status in daily digest
2. broaden candidate parameter variants under feedback control
3. add evidence ledger sidecar for research-only candidate screening

