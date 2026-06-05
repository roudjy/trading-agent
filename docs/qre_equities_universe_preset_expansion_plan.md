# QRE Equities Universe And Preset Expansion Plan

## Status

This document is planning-only.

It does not authorize:

- strategy mutation
- preset mutation
- threshold relaxation
- paper trading activation
- shadow trading activation
- live trading activation

Current phase remains controlled validation and evidence review only.

## Why This Plan Exists

`equities_exploratory_v1` currently gives bounded diagnostic value, but its candidate set is too narrow to answer the broader user goal of equity research across:

- Netherlands
- Europe
- United States
- Asia

The next expansion must improve research breadth without weakening discipline.

## Current Known Limits

Current diagnostics show:

- one preset family dominates the exploratory run
- 4h interval coverage is useful but narrow
- linkage is working for catalog-authorized hypotheses
- OOS evidence can exist without promotion
- promotion is blocked by concrete criteria, not by missing linkage

Operationally, the system is now able to distinguish:

1. runtime gate failures
2. public-result criteria failures
3. OOS-evidence sufficiency
4. stale runtime artifact interference

That means the next expansion can be evidence-led instead of guess-led.

## Expansion Axes

The work must stay split across five separate questions.

### 1. Universe Expansion

Add more equities only after each candidate universe passes data and liquidity review.

Candidate regional buckets:

- Netherlands: `ASML`, `ADYEN`, `INGA`, `PHIA`, `SHELL`
- Europe ex-NL: `SAP`, `SIE`, `MC`, `AIR`, `SU`, `NESN`
- United States: `AAPL`, `MSFT`, `NVDA`, `AMD`, `AMZN`, `META`, `GOOGL`, `JPM`, `XOM`, `HD`, `COST`
- Asia: `TSM`, `SONY`, `7203.T`, `9988.HK`, `005930.KS`

These are planning candidates, not approved runtime defaults.

### 2. Interval Expansion

Intervals must be assessed separately from universe growth.

Recommended review order:

1. keep `4h` as the baseline comparison point
2. evaluate whether `1d` adds cleaner trend structure
3. consider `1h` only after higher-timeframe equity evidence is stable

Do not add multiple new intervals in the same hypothesis test unless the test goal explicitly requires it.

### 3. Strategy Family Expansion

Trend remains the primary research direction.

Safe order:

1. strengthen the current trend family diagnosis
2. add one adjacent trend family only if it tests a distinct hypothesis
3. keep mean reversion deprioritized for this track unless new equity evidence justifies reopening it

No new family should be added merely to increase candidate count.

### 4. Threshold Review

Thresholds may be reviewed analytically, but not relaxed by default.

The review should answer:

- which criteria block most often
- whether the blockers reflect poor strategy quality or poor universe fit
- whether any criterion is structurally mismatched to slower equity trend strategies

Any threshold change must be its own scoped decision with isolated evidence.

### 5. Liquidity And Data Availability

Assets must satisfy both market quality and reproducibility constraints.

Admission criteria:

- reliable historical data source availability
- stable ticker mapping across providers
- sufficient traded volume for the selected interval
- low risk of frequent splits, symbol changes, or missing-session artifacts corrupting comparisons
- reproducible retrieval through the existing data boundary

If a region cannot meet these requirements, it stays out until data readiness is proven.

## Universe Admission Rules

A candidate equity or ETF should only enter an exploratory universe when all conditions below are met:

1. the symbol is easy to map deterministically
2. historical bars are available over the required OOS window
3. trading sessions and timezone handling are understood
4. liquidity is high enough that trade counts are meaningful
5. the asset adds diversity rather than duplicating an already-covered exposure

Preferred early composition:

- broad US large caps
- a small Europe sample
- a small Asia sample
- Netherlands as a distinct local bucket, not merged away

## Preset Expansion Rules

Preset expansion is not approved in this document.

When preset work begins later, it should follow:

1. preserve the registry and package authority boundaries
2. create one new exploratory preset at a time
3. tie each preset to a written hypothesis
4. compare against the existing `equities_exploratory_v1` baseline
5. preserve negative results

## Overfitting Controls

The expansion must avoid turning the exploratory preset into a hidden parameter sweep.

Controls:

- no brute-force parameter search
- no region-specific tuning before cross-region evidence exists
- no interval-specific threshold loosening without a separate review
- no adding assets solely because they improve one recent run
- no silent exclusion of failing assets from diagnostics

Failure memory must remain visible in reports and fixtures.

## Hypothesis Selector Guardrails

When later work allows broader hypothesis selection, the selector may draw from approved universes only.

It must not:

- invent unapproved assets
- promote paper/live capability
- treat this plan as execution authority
- bypass catalog, registry, or controlled validation policy

## Safe Rollout Sequence

The default rollout order is:

1. diagnostic only
2. controlled validation
3. evidence review
4. paper-readiness review only if gates pass
5. never live trading under this plan

Paper-readiness remains future-gated and does not follow automatically from better exploratory evidence.

## Explicit Non-Goals

This plan does not:

- activate paper, shadow, or live runtime
- authorize broker, risk, or execution changes
- mutate frozen contracts
- approve threshold changes
- approve preset changes
- promise region coverage by a fixed date

## Next Research Step After This PR

The next research-facing branch should stay diagnostic:

`diagnose/equities-exploratory-v1-blockers`

That branch can decide, with evidence, whether the next move is:

- universe expansion
- interval expansion
- preset expansion
- strategy-family expansion
- threshold analysis only
