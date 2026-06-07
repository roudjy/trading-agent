# QRE Fundamental Provider Candidate Registry

Research-only provider registry. No data has been fetched, no API integration was activated, and no provider is trusted or active by default.

## Status Counts
- total providers: 13
- candidate: 8
- manual_research_only: 3
- staging: 2
- quality_gated: 0
- active_read_only: 0
- deprecated: 0
- blocked: 0

## Highest Priority Candidates
- sec_companyfacts: priority 1 [candidate] - Highest-priority public candidate for US fundamentals, but still untrusted until full source-manifest and policy gates exist.
- openfigi_symbology: priority 2 [candidate] - High-priority symbology candidate. Useful for canonical identity, not for factor fields.
- euronext_issuer_metadata: priority 3 [candidate] - High-value identity context candidate for EU listings; not a factor field source.
- nasdaq_listings_metadata: priority 4 [candidate] - Useful for US symbology/listing metadata only; not a valuation source.
- nyse_listings_metadata: priority 4 [candidate] - Useful for US venue metadata only; no trust assignment to fundamentals.

## Providers By Status
### candidate
- sec_companyfacts: SEC EDGAR Company Facts (public_fundamental_filings, license=public_source_review_required, risk=low)
- openfigi_symbology: OpenFIGI (symbology_candidate, license=manual_review_required, risk=low)
- euronext_issuer_metadata: Euronext Public Issuer Metadata (exchange_metadata_candidate, license=manual_review_required, risk=low)
- nasdaq_listings_metadata: Nasdaq Listings Metadata (exchange_metadata_candidate, license=manual_review_required, risk=low)
- nyse_listings_metadata: NYSE Listings Metadata (exchange_metadata_candidate, license=manual_review_required, risk=low)
- financial_modeling_prep_candidate: Financial Modeling Prep (fundamental_api_candidate, license=manual_review_required, risk=medium)
- eodhd_candidate: EOD Historical Data (fundamental_api_candidate, license=manual_review_required, risk=medium)
- alpha_vantage_candidate: Alpha Vantage (fundamental_api_candidate, license=manual_review_required, risk=medium)
### manual_research_only
- companies_house_metadata: Companies House (issuer_registry_metadata, license=public_site_review_required, risk=low)
- stooq_price_context: Stooq (public_price_context, license=manual_review_required, risk=low)
- yahoo_finance_yfinance: Yahoo Finance / yfinance (public_convenience_dataset, license=licensing_warning, risk=high)
### staging
- financial_datasets_mcp: Financial Datasets MCP (connector_candidate, license=unknown, risk=medium)
- openbb_connector: OpenBB (connector_candidate, license=unknown, risk=medium)

## Safety
- No buy/sell recommendations
- No trade signals
- No strategy registration
- No paper/shadow/live activation
- No broker/risk/execution authority
