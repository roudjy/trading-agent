# Tiingo Hypothesis Lifecycle

## Purpose

`research.qre_tiingo_hypothesis_lifecycle` consumes the existing Tiingo hypothesis generator output and turns generated hypothesis seeds into research-only lifecycle records, admission decisions, deterministic events, operator updates, and a daily digest input block.

This PR closes the generator-to-admission/operator-observability boundary only. It does not close the full QRE research feedback loop because candidates are not yet materialized, screened, written to feedback memory, or consumed by a later run.

## Input artifact

Default input:

```text
logs/qre_tiingo_hypothesis_generator_e2e/latest.json
```

The module reads this artifact only. It does not rerun the upstream Tiingo E2E harness.

## Output artifacts

Default mode writes nothing and prints JSON to stdout:

```powershell
python -m research.qre_tiingo_hypothesis_lifecycle
```

Write mode writes only:

```text
logs/qre_tiingo_hypothesis_lifecycle/latest.json
logs/qre_tiingo_hypothesis_lifecycle/events.jsonl
logs/qre_tiingo_hypothesis_lifecycle/operator_summary.md
```

`events.jsonl` is rewritten as the complete deterministic event set for the current upstream artifact. It is not an unbounded append log.

## Lifecycle statuses

Allowed lifecycle decisions:

```text
admitted
rejected
blocked
```

Allowed lifecycle statuses:

```text
generated
admissible_for_research_candidate_formulation
rejected_before_candidate_formulation
blocked_missing_or_unsafe_input
```

An admitted hypothesis is admitted only for future research-only candidate formulation. It is not a candidate.

## Admission policy

The admission policy is `tiingo_research_candidate_admission_v1`. It is research-only and requires:

- upstream report kind is `qre_tiingo_hypothesis_generator_e2e`
- upstream final verdict is `pass_data_driven_hypothesis_generation`
- data dependency is proven
- trading authority is false
- real, shuffled, and truncated modes are present
- real mode has a valid profile and hypotheses
- shuffled mode has hypotheses
- real and shuffled content identities differ
- truncated control is blocked with zero hypotheses
- split-adjusted profile is present when corporate action events exist

If any report-level gate fails, the lifecycle report fails closed with `lifecycle_verdict=blocked`.

## Event journal

For admitted hypotheses the module emits:

```text
hypothesis_generated
hypothesis_admitted
```

For blocked report-level evidence it emits:

```text
hypothesis_blocked
```

Event IDs are deterministic and do not include timestamps.

## Operator updates

Every meaningful event gets a short operator update. Updates distinguish:

```text
admitted for future research-only candidate formulation
```

from:

```text
candidate created
strategy registered
trade signal
```

The latter three do not happen in this module.

## Daily digest input

`latest.json` includes:

```text
daily_digest_input.digest_kind = qre_hypothesis_lifecycle_daily_input
```

The block contains generated/admitted/rejected/blocked counts, highlights, blocked-reason counts, next actions, and a false authority summary. The daily status digest consumes this block for observability only. This integration does not add a scheduler or broaden lifecycle authority.

## Daily status digest integration

The QRE daily status digest optionally consumes:

```text
logs/qre_tiingo_hypothesis_lifecycle/latest.json
```

This sidecar provides generated/admitted/rejected/blocked lifecycle counts, the lifecycle verdict, operator-update count, next safe actions, and an explicit false authority summary for the operator-facing daily status report.

When the lifecycle sidecar is present and ready, the daily digest shows:

- hypotheses generated
- hypotheses admitted, rejected, and blocked
- next safe action
- candidate creation false
- screening run false
- trading authority false
- validation, paper, shadow, and live authority false

The digest JSON exposes the same lifecycle details in the persisted daily status packet and in the CLI summary:

```text
tiingo_hypothesis_lifecycle_status
tiingo_hypothesis_lifecycle_counts
tiingo_hypothesis_lifecycle_next_actions
tiingo_hypothesis_lifecycle_authority
```

`logs/qre_daily_status_digest/latest.json` persists those fields, and `logs/qre_daily_status_digest/operator_summary.md` includes a Tiingo hypothesis lifecycle section with generated/admitted/rejected/blocked counts, next safe action, and explicit false authority flags.

Missing lifecycle artifacts are not fatal. The daily digest reports the lifecycle status as unavailable and continues without changing candidate, screening, or trading status.

Malformed or unsafe lifecycle artifacts are reported as malformed or blocked diagnostics. Unsafe authority signals are never treated as permission, and the digest keeps the authority summary false.

Daily digest ingestion is observability-only. It does not create candidates, run screening, promote hypotheses, register strategies, start validation, enable paper/shadow/live, or grant trading authority.

This closes the operator daily-status visibility gap for Tiingo hypothesis lifecycle events. It does not close the full research feedback loop because candidate materialization, screening, feedback memory, and later-run consumption are still separate future steps.

## Safety boundaries

Every report keeps:

```text
trading_authority=false
creates_candidates=false
runs_screening=false
promotes_candidates=false
registers_strategy=false
validation_authority=false
paper_authority=false
shadow_authority=false
live_authority=false
```

A hypothesis admitted by this module is not a strategy, not a trade signal, not validation-ready, not paper-ready, not shadow-ready, and not live-ready.

## What this PR does not do

This PR does not:

- create candidate specs
- run screening
- validate hypotheses
- promote candidates
- register strategies
- start paper, shadow, or live paths
- grant trading authority
- mutate `research/research_latest.json`
- mutate `research/strategy_matrix.csv`

## Why this does not close the full QRE feedback loop yet

The full QRE feedback loop requires a downstream candidate materializer, screening result, evidence or memory writeback, later-run consumption, and tests proving a changed decision. This module stops before candidate materialization and emits only lifecycle/admission/observability artifacts.

## Next safe PR

The next safe PR is a research-only candidate spec contract and materializer that consumes admitted hypothesis lifecycle records. That later PR should still avoid screening, validation, promotion, strategy registration, paper, shadow, live, and trading authority unless those scopes are explicitly approved separately.

