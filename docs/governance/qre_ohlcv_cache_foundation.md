# QRE OHLCV/Cache Foundation

## Purpose

`research.qre_ohlcv_cache_foundation` materializes one deterministic read-only
foundation report over the existing local OHLCV/cache evidence surfaces.

It composes:

- `packages.qre_data.cache_manifest`
- `packages.qre_data.source_quality_readiness`
- `research.qre_source_cache_readiness_materialization`
- `research.qre_cache_throughput_manifest`
- `research.external_intelligence.source_manifest_registry`

## Scope

- Uses repository-local cache sidecars and datasets first.
- Reports whether the local cache foundation is reproducible, versioned, and
  quality-gated.
- Surfaces future external source blockers separately from the local foundation.
- Writes only:
  - `logs/qre_ohlcv_cache_foundation/latest.json`
  - `logs/qre_ohlcv_cache_foundation/operator_summary.md`
  - `artifacts/cache/cache_foundation_latest.v1.json`

## Out Of Scope

- No external fetches.
- No cache backfill or mutation.
- No activation of source providers.
- No paper, shadow, live, broker, risk, execution, or capital-allocation paths.
- No mutation of `research/research_latest.json` or `research/strategy_matrix.csv`.

## Commands

```powershell
python -m research.qre_ohlcv_cache_foundation
python -m research.qre_ohlcv_cache_foundation --write
python -m research.qre_ohlcv_cache_foundation --duckdb-available true --polars-available true
```

## Readiness Semantics

The foundation is `ready` only when all of the following are true:

- the local cache manifest is research-ready;
- the local source-quality report is research-ready;
- the source/cache materialization links both sidecars;
- the throughput manifest remains research-ready.

External source providers may still remain blocked. Those blockers are reported
explicitly and do not silently change the local cache foundation into authority
for trading or source activation.
