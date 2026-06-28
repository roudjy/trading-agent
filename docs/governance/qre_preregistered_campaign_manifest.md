# QRE Preregistered Campaign Manifest

## Purpose

`reporting.qre_preregistered_campaign_manifest` freezes the executable subset of
the `ADE-QRE-017W` portfolio into a deterministic, content-addressed manifest.
The projector is read-only and fails closed when required preregistration fields
are absent or only scaffold-visible.

## Current 017X behavior

- Source artifact: `logs/qre_campaign_portfolio_plan/latest.json`
- Executable cells are admitted only when the portfolio row is explicitly ready
  and all required fields are materially visible:
  - preset identity
  - asset or basket scope
  - timeframe
  - source readiness
  - data readiness
  - identity readiness
  - train window
  - validation window
  - OOS window
  - null controls
  - cost and slippage readiness
  - minimum sample
  - expected trade count
- Rows that fail any of those checks remain in `blocked_appendix` with exact
  blockers preserved.

## Authority boundary

- Read-only and context-only.
- Produces no campaign execution, no strategy generation, and no queue
  mutation.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_preregistered_campaign_manifest/latest.json`
- `logs/qre_preregistered_campaign_manifest/latest.md`

The JSON artifact includes:

- `manifest_identity`
- `replay_identity`
- `source_portfolio_identity`
- `executable_cells`
- `blocked_appendix`
- frozen decision and next-action vocabularies
- deterministic summary counts and fail-closed recommendation
