# QRE Broad Campaign Funnel Diagnosis

## Purpose

`reporting.qre_broad_campaign_funnel_diagnosis` joins the `017Y` broad
campaign accounting with the `017W` portfolio plan to produce a deterministic,
read-only funnel census and bottleneck diagnosis without changing criteria.

## Current 017Z behavior

- Source execution artifact: `logs/qre_broad_campaign_execution/latest.json`
- Source portfolio artifact: `logs/qre_campaign_portfolio_plan/latest.json`
- Produces:
  - funnel counts
  - criterion recommendations using the closed `017Z` vocabulary
  - one explicit primary bottleneck
  - secondary bottlenecks when visible
  - stratifications by thesis, behavior family, strategy, preset, timeframe,
    regime, and signal-density bucket where supported
  - failure taxonomy from repository-backed reason codes

## Authority boundary

- Read-only and context-only.
- Produces no recalibration, no campaign launch, and no strategy generation.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_broad_campaign_funnel_diagnosis/latest.json`
- `logs/qre_broad_campaign_funnel_diagnosis/latest.md`
