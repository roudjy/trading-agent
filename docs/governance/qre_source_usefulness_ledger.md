# QRE Source Usefulness Ledger

`ADE-QRE-017K` materializes the repository's read-only source usefulness
surface.

## Purpose

This surface tracks source usefulness, disagreement proxies, quality-failure
proxies, cache-hit proxies, and operator-visible utility using existing local
sidecars only. It does not promote sources, infer trading authority, or fetch
external data.

## Current shape

The canonical artifact is:

- `logs/qre_source_usefulness_ledger/latest.json`

The operator summary is:

- `logs/qre_source_usefulness_ledger/operator_summary.md`

The report is read-only and advisory. It derives its current rows from the local
cache manifest and source-quality readiness sidecars, then exposes a
deterministic usefulness snapshot for operator review.

## Scope

- read local cache and source-quality sidecars;
- summarize usefulness as an operator-facing research surface;
- keep the output deterministic and reproducible;
- preserve negative and blocked states explicitly.

## Out of scope

- no external data fetches;
- no cache mutation;
- no source promotion or activation;
- no paper, shadow, live, broker, risk, execution, or capital-allocation work;
- no mutation of frozen contracts:
  - `research/research_latest.json`
  - `research/strategy_matrix.csv`
- no `.claude/**` edits.

## Canonical commands

```powershell
python -m research.qre_source_usefulness_ledger
python -m research.qre_source_usefulness_ledger --write
python -m research.qre_source_usefulness_ledger --status
```

## Readiness note

The ledger is research-ready only when the local cache manifest, source-quality
sidecar, and source rows are all present and consistent. If any required input is
missing, the surface fails closed.
