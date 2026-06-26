# QRE Source Quality, PIT, and Identity Readiness

`ADE-QRE-017J` materializes one read-only readiness surface across the
existing cache, source-quality, lifecycle, PIT, historical-accounting,
and symbology foundations.

## Scope

- local observed-source evidence remains distinct from source-manifest
  governance;
- license and allowed-use state fail closed before PIT or identity can
  be treated as readiness;
- identity ambiguity remains visible and blocking;
- PIT, report-lag, and restatement stay explicit per source manifest;
- diagnostics remain research context only.

## Current interpretation

- Repository-local cache evidence exists for observed sources such as
  `yfinance`, but that does not override manifest-level license or
  readiness blockers.
- Candidate source manifests remain blocked on license review, PIT
  policy, report-lag policy, restatement policy, or identity-gate
  completeness.
- Symbology is infrastructure only. Verified mappings are surfaced, but
  ambiguous aliases keep identity readiness partial or blocked.

## Canonical artifact

- `artifacts/data_readiness/source_quality_pit_identity_readiness_latest.v1.json`

## Protected boundaries

- no provider activation;
- no external fetches;
- no mutation of cache or frozen research contracts;
- no paper, shadow, live, broker, risk, or execution behavior.
