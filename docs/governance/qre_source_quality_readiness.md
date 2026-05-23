# QRE Source Quality Readiness

`packages.qre_data.source_quality_readiness` builds a read-only source identity
and source quality report from the local cache manifest introduced by
ADE-QRE-003.

The report is advisory and fail-closed. It can mark data as not research-ready,
but it cannot fetch data, activate vendor sources, mutate campaigns, change
strategy behavior, or update frozen research outputs.

## Commands

Dry-run from the latest cache manifest:

```powershell
python -m packages.qre_data.source_quality_readiness --no-write --frozen-utc 2026-05-23T00:00:00Z
```

Read latest source quality status:

```powershell
python -m packages.qre_data.source_quality_readiness --status
```

Write deterministic sidecars under `logs/qre_data_source_quality_readiness/`:

```powershell
python -m packages.qre_data.source_quality_readiness
```

## Readiness Rules

- Missing source quality report fails closed.
- Missing or invalid cache manifest fails closed.
- Unknown source, instrument, timeframe, or cache kind blocks source quality.
- Non-ready manifest file status blocks source quality.
- Non-positive row count blocks source quality.
- Missing timestamp range blocks source quality.
- Missing content hash blocks source quality.

## Inactive Scope

This helper does not activate OpenFIGI, CFTC, EIA, OpenBB, CoinGecko, live
fetching, source-derived alpha, live trading, paper trading, shadow trading,
broker integration, risk-engine behavior, or execution paths.
