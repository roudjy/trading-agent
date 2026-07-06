# QRE Source Certification Policy

Policy version: `qre_alpha_source_qualification_pr4_v1`.

QRE source certification is evidence-based. A snapshot can become
`SOURCE_SCREENING_ELIGIBLE` only when its source manifest permits automated
research screening and its measured snapshot metrics satisfy the screening
policy. The policy does not grant trading, candidate, paper, shadow, live, or
Step 5 authority.

## Required Source Manifest

Each snapshot must resolve to a source manifest by `source_id`, `provider_id`,
or an approved alias. Missing manifests block qualification with
`missing_source_manifest`.

The manifest must show:

- `license_policy_status=PASS` or equivalent screening-approved status;
- `allowed_use` includes `research_screening` or `automated_research_screening`;
- `source_status` is `quality_gated`, `screening_ready`, or `certified`.

Otherwise the snapshot is blocked with
`source_license_not_screening_eligible`.

## Expected Bars And Calendars

Expected bars must be measured from the data catalog integrity layer. Crypto
24/7 hourly/daily data can use a deterministic continuous calendar. Daily
weekday-only markets can use deterministic weekday counts. Intraday session
markets require an explicit or reliable session calendar; otherwise
`expected_bar_count` and `coverage_ratio` remain null and the snapshot is
blocked with `missing_expected_bar_count` and `missing_calendar`.

Coverage is never set to `1.0` when expected bars are unknown.

## Screening Thresholds

Screening eligibility requires:

- `coverage_ratio >= 0.90`;
- `unique_bar_count >= 48`;
- duplicate bar ratio `<= 0.05`;
- no conflicting duplicate bars;
- no invalid OHLCV/timestamp rows;
- stable fingerprint and immutable/reproducible snapshot identity;
- required query, period, source, instrument, timeframe, and lineage fields.

Validation eligibility remains separate and is not granted by this policy.

## Operator Actions

Common blocked reason codes are:

- `missing_source_manifest`;
- `source_license_not_screening_eligible`;
- `missing_expected_bar_count`;
- `missing_calendar`;
- `insufficient_coverage`;
- `duplicate_bar_ratio_too_high`;
- `conflicting_rows_present`;
- `insufficient_unique_history`;
- `invalid_ohlcv_or_timestamp`;
- `impossible_bar_density`.
