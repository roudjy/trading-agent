# QRE Source Manifest Schema and License Policy

- No data fetched
- No provider activated
- No recipe, hypothesis seed, or controlled evaluation readiness is unlocked unless all gates pass

## Manifest Summary
- total manifests: 13
- FAIL: 2
- WARN: 11

## License Policy Summary
- UNKNOWN: 2
- WARN: 11

## Source Categories
- connector_wrapper: 2
- free_api_limited: 2
- manual_only: 3
- paid_vendor_candidate: 2
- public_with_terms: 4

## Key Constraints
- quality_gated eligible providers: none
- active_read_only eligible providers: none
- providers blocked by license policy: alpha_vantage_candidate, companies_house_metadata, eodhd_candidate, euronext_issuer_metadata, financial_datasets_mcp, financial_modeling_prep_candidate, nasdaq_listings_metadata, nyse_listings_metadata, openbb_connector, openfigi_symbology, sec_companyfacts, stooq_price_context, yahoo_finance_yfinance
- providers blocked by policy gaps: alpha_vantage_candidate, eodhd_candidate, financial_modeling_prep_candidate, sec_companyfacts

## Source Rows
- alpha_vantage_candidate_manifest: status=WARN, license_policy=WARN, type=fundamental_statement_data, category=free_api_limited, blockers=FACTOR_FIELD_COVERAGE_UNKNOWN, LICENSE_REVIEW_REQUIRED, POINT_IN_TIME_UNKNOWN, REPORT_LAG_POLICY_UNKNOWN, RESTATEMENT_POLICY_UNKNOWN, SOURCE_QUALITY_UNKNOWN
- companies_house_metadata_manifest: status=WARN, license_policy=WARN, type=issuer_metadata, category=manual_only, blockers=LICENSE_REVIEW_REQUIRED
- eodhd_candidate_manifest: status=WARN, license_policy=WARN, type=fundamental_statement_data, category=paid_vendor_candidate, blockers=FACTOR_FIELD_COVERAGE_UNKNOWN, LICENSE_REVIEW_REQUIRED, POINT_IN_TIME_UNKNOWN, REPORT_LAG_POLICY_UNKNOWN, RESTATEMENT_POLICY_UNKNOWN, SOURCE_QUALITY_UNKNOWN
- euronext_issuer_metadata_manifest: status=WARN, license_policy=WARN, type=issuer_metadata, category=public_with_terms, blockers=LICENSE_REVIEW_REQUIRED
- financial_datasets_mcp_manifest: status=FAIL, license_policy=UNKNOWN, type=connector_staging, category=connector_wrapper, blockers=ACCESS_METHOD_UNKNOWN, MISSING_LICENSE_TERMS, SOURCE_QUALITY_UNKNOWN
- financial_modeling_prep_candidate_manifest: status=WARN, license_policy=WARN, type=fundamental_statement_data, category=paid_vendor_candidate, blockers=FACTOR_FIELD_COVERAGE_UNKNOWN, LICENSE_REVIEW_REQUIRED, POINT_IN_TIME_UNKNOWN, REPORT_LAG_POLICY_UNKNOWN, RESTATEMENT_POLICY_UNKNOWN, SOURCE_QUALITY_UNKNOWN
- nasdaq_listings_metadata_manifest: status=WARN, license_policy=WARN, type=listing_metadata, category=public_with_terms, blockers=LICENSE_REVIEW_REQUIRED
- nyse_listings_metadata_manifest: status=WARN, license_policy=WARN, type=listing_metadata, category=public_with_terms, blockers=LICENSE_REVIEW_REQUIRED
- openbb_connector_manifest: status=FAIL, license_policy=UNKNOWN, type=connector_staging, category=connector_wrapper, blockers=MISSING_LICENSE_TERMS, SOURCE_QUALITY_UNKNOWN
- openfigi_symbology_manifest: status=WARN, license_policy=WARN, type=identity_symbology, category=free_api_limited, blockers=LICENSE_REVIEW_REQUIRED
- sec_companyfacts_manifest: status=WARN, license_policy=WARN, type=fundamental_statement_data, category=public_with_terms, blockers=LICENSE_REVIEW_REQUIRED, REPORT_LAG_POLICY_UNKNOWN, RESTATEMENT_POLICY_UNKNOWN, SOURCE_QUALITY_UNKNOWN
- stooq_price_context_manifest: status=WARN, license_policy=WARN, type=market_price_context, category=manual_only, blockers=LICENSE_REVIEW_REQUIRED
- yahoo_finance_yfinance_manifest: status=WARN, license_policy=WARN, type=manual_research_context, category=manual_only, blockers=SOURCE_QUALITY_UNKNOWN
