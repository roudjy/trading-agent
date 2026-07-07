# QRE Source Onboarding Harness

The source onboarding harness accepts operator-supplied OHLCV data and a declarative source manifest, then emits QRE data-catalog and source-certification artifacts for the existing source qualification policy. It does not grant trading authority, start campaigns, create candidates, call providers, or change frozen research contracts.

## Manifest Contract

Schema version: `qre_source_manifest_v1`.

Required fields:

- `source_id`, `provider_id`, `source_family`, `asset_class`, `venue`
- `allowed_use`
- `license_policy_status`
- `calendar.type` and `calendar.timezone`
- `data.schema` plus timestamp, symbol, OHLCV column mappings
- `timeframe` or `timeframes`
- `universe.symbols`

Screening is allowed only when all of these are true:

- `allowed_use` contains `research_screening`
- `license_policy_status` is `PASS`
- `operator_license_attestation` is present with `provided_by`, `attested_at_utc`, and a non-secret `evidence_ref`
- `source_status` is explicitly set to `quality_gated`, `screening_ready`, or `certified`
- imported bars satisfy the existing `qre_alpha_source_qualification_pr4_v1` metrics and thresholds

For local CSV onboarding, the minimal screening manifest is a manual local-source
manifest plus `allowed_use: [manual_research, research_screening]`,
`license_policy_status: PASS`, `source_status: quality_gated`, and a non-secret
`operator_license_attestation.evidence_ref`. Missing license proof maps to
`source_license_not_screening_eligible` and operator action
`provide_screening_license_attestation`; missing or non-screening `source_status`
is reported by `validate-manifest` before qualification.

Manual-research-only manifests remain allowed as manual-only sources. They are
not automatically promoted to screening, even when the local bars are coherent.

## Local File Adapter

Supported command:

```text
python -m research.qre_source_onboarding import-local --manifest <path> --bars <csv> --out generated_research/data_catalog/imports/<source_id>/<snapshot_id>
```

The adapter supports CSV with mapped `timestamp`, `symbol`, `open`, `high`, `low`, `close`, and `volume` columns. Rows are normalized to UTC, sorted deterministically by symbol and timestamp, deduplicated, checked for conflicting duplicates and OHLCV validity, and fingerprinted from canonical content only. File path and mtime are excluded from identities.

Supported calendars:

- `crypto_24_7` for hourly or daily continuous markets
- `weekday_daily` for weekday-only daily bars

Unsupported or missing calendars produce `missing_calendar` and no synthetic coverage.

## Artifacts

The harness writes only QRE onboarding and qualification artifacts:

- `generated_research/data_catalog/onboarding/latest.json`
- `generated_research/data_catalog/onboarding/source_manifest_latest.json`
- `generated_research/data_catalog/onboarding/import_audit_latest.json`
- `generated_research/data_catalog/source_certification/latest.json`
- `generated_research/alpha_discovery/source_qualifications/latest.json`
- `generated_research/alpha_discovery/source_resolution/latest.json`

Artifacts include manifest hash, data fingerprint, row counts, expected bars, coverage, duplicate/conflict metrics, invalid row metrics, qualification tier, blocked reasons, operator actions, policy version, and generation time.

Local data imports and generated research/catalog artifacts are operator-local
state and should not be committed. This includes raw CSV exports, normalized
local import directories, onboarding JSON, source-certification JSON, and source
resolution or qualification outputs generated from a local import.

`SOURCE_SCREENING_ELIGIBLE` means the immutable local snapshot may be used for
research screening under the source qualification policy. It is not shadow,
paper, live, broker, risk, execution, or trading authority; source resolution
continues to emit `trading_authority: false`.

## Secrets

Provider credentials are out of scope for local import. Future provider skeletons must use environment variables or Docker secrets only:

- `QRE_DATABENTO_API_KEY`
- `QRE_TIINGO_API_KEY`
- `QRE_NASDAQ_DATA_LINK_API_KEY`
- `QRE_ALPHA_VANTAGE_API_KEY`

Secrets must never appear in manifests, logs, artifacts, fixtures, or CI output.

## Provider Onboarding Priority

1. Local exports from Databento, Tiingo, Nasdaq Data Link, Binance, Coinbase, or Kraken: lowest integration risk because QRE does not call provider endpoints.
2. Public crypto candle APIs: possible read-only adapter later, but policy must remain operator-attested and default to manual review.
3. Commercial provider APIs: add only after credentials, terms, rate limits, and allowed-use evidence are explicitly provided.
