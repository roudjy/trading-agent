# Tiingo Hypothesis Generator E2E

## Purpose

`research.qre_tiingo_hypothesis_generator_e2e` is a read-only research-evidence harness for checking whether QRE hypothesis seed generation is actually data-driven from the onboarded Tiingo EOD ETF snapshot.

It does not run research campaigns, validation, candidate promotion, strategy registration, paper, shadow, live, broker, risk, order, or execution paths.

## Why This Exists

The current hypothesis-discovery layer is largely proposal, catalog, and seed driven. This harness makes the data dependency observable by comparing:

- real Tiingo bars,
- a shuffled-return control that preserves return distributions but destroys temporal order,
- a truncated control with insufficient history and cross-section.

A passing result means the emitted read-only hypothesis seed identities depend on the local Tiingo data profile and degrade under controls. A failing result means the layer still behaves as static or template driven for this evidence check.

## Source Prerequisites

The harness fails closed unless source resolution selects:

- `selected_source: tiingo_eod_equities_free`
- `selected_snapshot: qdsnap_2b1258c6f592fa08`
- `current_source_tier: SOURCE_SCREENING_ELIGIBLE`
- `trading_authority: false`
- `unresolved_blockers: []`

Bars are loaded only from local files, preferring:

- `data/imports/tiingo_eod_equities_free/tiingo_eod_etf_20210101_20251231/bars.csv`
- `generated_research/data_catalog/imports/tiingo_eod_equities_free/qdsnap_2b1258c6f592fa08/bars.csv`
- `generated_research/data_catalog/imports/**/qdsnap_2b1258c6f592fa08*/**/*.csv`

There is no network fallback.

## Commands

```powershell
python -m research.qre_tiingo_hypothesis_generator_e2e --mode all --max-hypotheses 5 --seed 1729
```

```powershell
python -m research.qre_tiingo_hypothesis_generator_e2e --mode all --max-hypotheses 5 --seed 1729 --write
```

```powershell
Get-Content .\logs\qre_tiingo_hypothesis_generator_e2e\operator_summary.md -Raw
```

Without `--write`, the module prints JSON to stdout and writes no files. With `--write`, it writes only:

- `logs/qre_tiingo_hypothesis_generator_e2e/latest.json`
- `logs/qre_tiingo_hypothesis_generator_e2e/operator_summary.md`

## Verdicts

- `pass_data_driven_hypothesis_generation`: real-mode hypotheses exist, reference the Tiingo snapshot, use only the Tiingo ETF universe, are generated from the data profile, differ from shuffled-return controls, and degrade under truncation.
- `fail_static_or_template_driven`: real and control identities are identical or controls do not show meaningful degradation.
- `blocked_source_resolution`: source-resolution artifacts are missing, malformed, blocked, wrong-source, wrong-snapshot, wrong-tier, or grant trading authority.
- `blocked_data_unavailable`: local bars are missing, malformed, missing required columns, empty after Tiingo ETF filtering, or match the old controlled universe.
- `blocked_insufficient_history`: available data cannot support the required history window.
- `blocked_insufficient_cross_section`: available data has fewer than three usable Tiingo ETF symbols.
- `blocked_safety_boundary`: a safety flag or output path violates the research-only boundary.

## Safety Boundaries

Every payload carries these false authority flags:

- `network_called`
- `run_research_called`
- `campaign_launcher_called`
- `validation_executed`
- `candidate_promotion_allowed`
- `strategy_registration_allowed`
- `execution_performed`
- `paper_shadow_live_allowed`
- `trading_authority`

This artifact is research-only. It is not a trade signal, not strategy authority, not candidate promotion, and not paper/shadow/live authority.

## Trading Authority

`automatic_actions_allowed=true` in source-resolution artifacts only permits bounded automated research evidence work. It does not grant trading authority. This harness requires `trading_authority=false`, emits hypotheses with `screening_only=true` and `not_trade_signal=true`, and never creates executable strategies or execution state.
