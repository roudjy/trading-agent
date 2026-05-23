# QRE Data Cache Manifest

## Purpose

`packages.qre_data.cache_manifest` builds a deterministic read-only manifest
over existing local research cache files.

## Scope

- Reads local `data/cache/*/*.parquet` files.
- Reports source, instrument, timeframe, row count, min/max timestamps, file
  size, content hash, and aggregate coverage rows.
- Writes only optional sidecars under `logs/qre_data_cache_manifest/`.
- Fails closed when the manifest is missing, invalid, empty, or not research
  ready.

## Out Of Scope

- No live fetching.
- No paid data activation.
- No source adapter activation.
- No cache backfill.
- No strategy, registry, campaign, routing, paper, shadow, live, broker, risk,
  or execution behavior.
- No changes to `research/research_latest.json` or `research/strategy_matrix.csv`.

## Commands

```powershell
python -m packages.qre_data.cache_manifest --no-write --frozen-utc 2026-05-23T00:00:00Z
python -m packages.qre_data.cache_manifest --status
python -m packages.qre_data.cache_manifest
```

## Readiness Semantics

`research_ready` is true only when at least one cache file exists, total rows are
positive, and no inspected cache file is unreadable. Missing manifest status is
`missing_manifest` with `research_ready=false` and `fails_closed=true`.
