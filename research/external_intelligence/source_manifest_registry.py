"""Deterministic source manifest registry and sidecar writers."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Final

from research.external_intelligence.fundamental_provider_registry import (
    build_fundamental_provider_registry,
)
from research.external_intelligence.source_license_policy import evaluate_license_policy
from research.external_intelligence.source_manifest_schema import (
    FUNDAMENTAL_SOURCE_TYPES,
    IDENTITY_SOURCE_TYPES,
    METADATA_SOURCE_TYPES,
    SCHEMA_VERSION,
    validate_source_manifest_rows,
)


OUTPUT_DIR: Final[Path] = Path("artifacts/external_intelligence")
WRITE_PREFIX: Final[str] = "artifacts/external_intelligence/"
MANIFESTS_NAME: Final[str] = "source_manifests_latest.v1.json"
LICENSE_POLICY_NAME: Final[str] = "source_license_policy_latest.v1.json"
QUALITY_NAME: Final[str] = "source_manifest_quality_latest.v1.json"


SOURCE_MANIFEST_ROWS: Final[tuple[dict[str, object], ...]] = (
    {
        "source_id": "alpha_vantage_candidate_manifest",
        "provider_id": "alpha_vantage_candidate",
        "source_name": "Alpha Vantage Candidate Manifest",
        "source_type": "fundamental_statement_data",
        "source_category": "free_api_limited",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": True,
        "cost_model": "free_limited",
        "license_terms_status": "review_required",
        "license_terms_reference": "alpha_vantage_terms_review_required",
        "allowed_use": ["fundamental_field_candidate", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "api_latency_unknown",
        "expected_freshness": "daily_or_slower_unknown",
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["Asia", "Europe", "US"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["balance_sheet_statement", "cash_flow_statement", "income_statement"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown_without_policy",
        "known_limitations": ["license_terms_not_reviewed", "policy_not_defined"],
        "required_quality_gates": ["field_coverage_manifest_defined", "license_reviewed", "source_quality_reviewed"],
        "activation_requirements": [
            "field_coverage_manifest_defined",
            "license_reviewed",
            "point_in_time_policy_defined",
            "report_lag_policy_defined",
            "restatement_policy_defined",
        ],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": [
            "FACTOR_FIELD_COVERAGE_UNKNOWN",
            "LICENSE_REVIEW_REQUIRED",
            "POINT_IN_TIME_UNKNOWN",
            "REPORT_LAG_POLICY_UNKNOWN",
            "RESTATEMENT_POLICY_UNKNOWN",
            "SOURCE_QUALITY_UNKNOWN",
        ],
        "operator_notes": "Stub manifest only. No API integration or data fetch.",
    },
    {
        "source_id": "companies_house_metadata_manifest",
        "provider_id": "companies_house_metadata",
        "source_name": "Companies House Metadata Manifest",
        "source_type": "issuer_metadata",
        "source_category": "manual_only",
        "source_status": "manual_research_only",
        "access_method": "manual_download",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "companies_house_terms_review_required",
        "allowed_use": ["manual_research_context", "metadata_context", "operator_explanation"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "manual_lookup",
        "expected_freshness": "issuer_registry_schedule_unknown",
        "asset_coverage": ["uk_equities_metadata"],
        "region_coverage": ["United Kingdom"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["issuer_identity_context"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "metadata_only",
        "lookahead_bias_risk": "metadata_only",
        "known_limitations": ["manual_context_only", "not_fundamental_data"],
        "required_quality_gates": ["license_reviewed", "metadata_context_reviewed"],
        "activation_requirements": ["operator_manual_review"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Manual metadata context only. Does not support automated readiness.",
    },
    {
        "source_id": "eodhd_candidate_manifest",
        "provider_id": "eodhd_candidate",
        "source_name": "EOD Historical Data Candidate Manifest",
        "source_type": "fundamental_statement_data",
        "source_category": "paid_vendor_candidate",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": True,
        "cost_model": "paid",
        "license_terms_status": "review_required",
        "license_terms_reference": "eodhd_terms_review_required",
        "allowed_use": ["fundamental_field_candidate", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "api_latency_unknown",
        "expected_freshness": "vendor_defined_unknown",
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["Asia", "Europe", "Global", "US"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["balance_sheet_statement", "cash_flow_statement", "dividend_history", "income_statement"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown_without_policy",
        "known_limitations": ["paid_vendor_candidate_only", "policy_not_defined"],
        "required_quality_gates": ["field_coverage_manifest_defined", "license_reviewed", "source_quality_reviewed"],
        "activation_requirements": ["operator_license_approval", "point_in_time_policy_defined", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": [
            "FACTOR_FIELD_COVERAGE_UNKNOWN","LICENSE_REVIEW_REQUIRED","POINT_IN_TIME_UNKNOWN",
            "REPORT_LAG_POLICY_UNKNOWN","RESTATEMENT_POLICY_UNKNOWN","SOURCE_QUALITY_UNKNOWN",
        ],
        "operator_notes": "Candidate only. Paid status does not imply trust or activation.",
    },
    {
        "source_id": "euronext_issuer_metadata_manifest",
        "provider_id": "euronext_issuer_metadata",
        "source_name": "Euronext Issuer Metadata Manifest",
        "source_type": "issuer_metadata",
        "source_category": "public_with_terms",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "euronext_terms_review_required",
        "allowed_use": ["identity_mapping", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "manual_or_http_metadata",
        "expected_freshness": "exchange_maintenance_schedule_unknown",
        "asset_coverage": ["europe_equities_metadata"],
        "region_coverage": ["Belgium", "France", "Ireland", "Netherlands", "Portugal"],
        "exchange_coverage": ["EPA", "XAMS", "XBRU", "XLIS", "XDUB"],
        "factor_field_coverage_claims": ["issuer_metadata", "listing_metadata", "venue_context"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "metadata_only",
        "lookahead_bias_risk": "metadata_only",
        "known_limitations": ["metadata_not_fundamentals"],
        "required_quality_gates": ["identity_mapping_quality_gate", "license_reviewed"],
        "activation_requirements": ["identity_mapping_quality_gate", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Identity and listing context only. Does not satisfy factor fields.",
    },
    {
        "source_id": "financial_datasets_mcp_manifest",
        "provider_id": "financial_datasets_mcp",
        "source_name": "Financial Datasets MCP Manifest",
        "source_type": "connector_staging",
        "source_category": "connector_wrapper",
        "source_status": "staging",
        "access_method": "connector",
        "authentication_required": False,
        "cost_model": "unknown",
        "license_terms_status": "unknown",
        "license_terms_reference": "operator_manifest_required",
        "allowed_use": ["connector_discovery", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "depends_on_downstream_provider",
        "expected_freshness": "depends_on_downstream_provider",
        "asset_coverage": ["unknown_until_manifested"],
        "region_coverage": ["unknown_until_manifested"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["connector_surface_only"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown",
        "known_limitations": ["connector_only", "downstream_source_not_manifested"],
        "required_quality_gates": ["connector_contract_reviewed", "downstream_provider_manifest_defined"],
        "activation_requirements": ["downstream_provider_manifest_defined", "operator_license_approval"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "FAIL",
        "manifest_block_reasons": ["ACCESS_METHOD_UNKNOWN", "MISSING_LICENSE_TERMS", "SOURCE_QUALITY_UNKNOWN"],
        "operator_notes": "Connector wrapper only. Underlying provider trust must be explicit.",
    },
    {
        "source_id": "financial_modeling_prep_candidate_manifest",
        "provider_id": "financial_modeling_prep_candidate",
        "source_name": "Financial Modeling Prep Candidate Manifest",
        "source_type": "fundamental_statement_data",
        "source_category": "paid_vendor_candidate",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": True,
        "cost_model": "mixed",
        "license_terms_status": "review_required",
        "license_terms_reference": "fmp_terms_review_required",
        "allowed_use": ["fundamental_field_candidate", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "api_latency_unknown",
        "expected_freshness": "vendor_defined_unknown",
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["Asia", "Europe", "Global", "US"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["balance_sheet_statement", "cash_flow_statement", "enterprise_value", "income_statement"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown_without_policy",
        "known_limitations": ["policy_not_defined", "terms_not_reviewed"],
        "required_quality_gates": ["field_coverage_manifest_defined", "license_reviewed", "source_quality_reviewed"],
        "activation_requirements": ["operator_license_approval", "point_in_time_policy_defined", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": [
            "FACTOR_FIELD_COVERAGE_UNKNOWN","LICENSE_REVIEW_REQUIRED","POINT_IN_TIME_UNKNOWN",
            "REPORT_LAG_POLICY_UNKNOWN","RESTATEMENT_POLICY_UNKNOWN","SOURCE_QUALITY_UNKNOWN",
        ],
        "operator_notes": "Candidate only. No integration or claims of readiness.",
    },
    {
        "source_id": "nasdaq_listings_metadata_manifest",
        "provider_id": "nasdaq_listings_metadata",
        "source_name": "Nasdaq Listings Metadata Manifest",
        "source_type": "listing_metadata",
        "source_category": "public_with_terms",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "nasdaq_terms_review_required",
        "allowed_use": ["identity_mapping", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "manual_or_http_metadata",
        "expected_freshness": "listing_file_schedule_unknown",
        "asset_coverage": ["us_listings_metadata"],
        "region_coverage": ["United States"],
        "exchange_coverage": ["XNAS"],
        "factor_field_coverage_claims": ["issuer_metadata", "listing_metadata", "venue_context"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "metadata_only",
        "lookahead_bias_risk": "metadata_only",
        "known_limitations": ["metadata_not_fundamentals"],
        "required_quality_gates": ["identity_mapping_quality_gate", "license_reviewed"],
        "activation_requirements": ["identity_mapping_quality_gate", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Listing metadata only. Does not support factor readiness.",
    },
    {
        "source_id": "nyse_listings_metadata_manifest",
        "provider_id": "nyse_listings_metadata",
        "source_name": "NYSE Listings Metadata Manifest",
        "source_type": "listing_metadata",
        "source_category": "public_with_terms",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "nyse_terms_review_required",
        "allowed_use": ["identity_mapping", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "manual_or_http_metadata",
        "expected_freshness": "listing_file_schedule_unknown",
        "asset_coverage": ["us_listings_metadata"],
        "region_coverage": ["United States"],
        "exchange_coverage": ["XNYS"],
        "factor_field_coverage_claims": ["issuer_metadata", "listing_metadata", "venue_context"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "metadata_only",
        "lookahead_bias_risk": "metadata_only",
        "known_limitations": ["metadata_not_fundamentals"],
        "required_quality_gates": ["identity_mapping_quality_gate", "license_reviewed"],
        "activation_requirements": ["identity_mapping_quality_gate", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Listing metadata only. Does not support factor readiness.",
    },
    {
        "source_id": "openbb_connector_manifest",
        "provider_id": "openbb_connector",
        "source_name": "OpenBB Connector Manifest",
        "source_type": "connector_staging",
        "source_category": "connector_wrapper",
        "source_status": "staging",
        "access_method": "connector",
        "authentication_required": False,
        "cost_model": "unknown",
        "license_terms_status": "unknown",
        "license_terms_reference": "operator_manifest_required",
        "allowed_use": ["connector_discovery", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "depends_on_downstream_provider",
        "expected_freshness": "depends_on_downstream_provider",
        "asset_coverage": ["multi_asset_connector_surface"],
        "region_coverage": ["Global"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["connector_surface_only"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown",
        "known_limitations": ["connector_only", "downstream_source_not_manifested"],
        "required_quality_gates": ["connector_contract_reviewed", "downstream_provider_manifest_defined"],
        "activation_requirements": ["downstream_provider_manifest_defined", "operator_license_approval"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "FAIL",
        "manifest_block_reasons": ["MISSING_LICENSE_TERMS", "SOURCE_QUALITY_UNKNOWN"],
        "operator_notes": "Connector only. Underlying provider must carry its own manifest and policy.",
    },
    {
        "source_id": "openfigi_symbology_manifest",
        "provider_id": "openfigi_symbology",
        "source_name": "OpenFIGI Symbology Manifest",
        "source_type": "identity_symbology",
        "source_category": "free_api_limited",
        "source_status": "candidate",
        "access_method": "static_manifest",
        "authentication_required": False,
        "cost_model": "free_limited",
        "license_terms_status": "review_required",
        "license_terms_reference": "openfigi_terms_review_required",
        "allowed_use": ["identity_mapping", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "api_or_manual_lookup_unknown",
        "expected_freshness": "symbology_reference_schedule_unknown",
        "asset_coverage": ["equities", "etfs", "multi_listing_symbology"],
        "region_coverage": ["Global"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["identity_only_not_fundamentals"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "identity_only",
        "lookahead_bias_risk": "identity_only",
        "known_limitations": ["not_fundamental_source", "symbology_only"],
        "required_quality_gates": ["identity_mapping_quality_gate", "license_reviewed"],
        "activation_requirements": ["identity_mapping_quality_gate", "source_manifest_quality_pass"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Identity context only. Must not unlock fundamental readiness.",
    },
    {
        "source_id": "sec_companyfacts_manifest",
        "provider_id": "sec_companyfacts",
        "source_name": "SEC EDGAR Company Facts Manifest",
        "source_type": "fundamental_statement_data",
        "source_category": "public_with_terms",
        "source_status": "candidate",
        "access_method": "public_api",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "sec_edgar_terms_review_required",
        "allowed_use": ["fundamental_field_candidate", "metadata_context", "operator_explanation", "source_candidate_research"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "public_companyfacts_endpoint_latency_unknown",
        "expected_freshness": "filing_driven_public_disclosure_unknown_lag",
        "asset_coverage": ["us_equities"],
        "region_coverage": ["United States"],
        "exchange_coverage": ["XNYS", "XNAS"],
        "factor_field_coverage_claims": ["balance_sheet_statement", "cash_flow_statement", "income_statement", "multi_period_fundamentals"],
        "point_in_time_support": "partially_supported",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "partially_supported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "unknown_without_policy",
        "lookahead_bias_risk": "unknown_without_policy",
        "known_limitations": [
            "market_cap_not_manifested",
            "point_in_time_policy_not_defined",
            "report_lag_policy_not_defined",
            "restatement_policy_not_defined",
            "us_only",
        ],
        "required_quality_gates": [
            "field_coverage_manifest_defined",
            "issuer_to_symbol_mapping_reviewed",
            "license_reviewed",
            "point_in_time_policy_defined",
            "report_lag_policy_defined",
            "restatement_policy_defined",
            "source_quality_reviewed",
        ],
        "activation_requirements": [
            "field_coverage_manifest_defined",
            "issuer_to_symbol_mapping_reviewed",
            "license_reviewed",
            "point_in_time_policy_defined",
            "report_lag_policy_defined",
            "restatement_policy_defined",
            "source_manifest_quality_pass",
        ],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": [
            "LICENSE_REVIEW_REQUIRED",
            "REPORT_LAG_POLICY_UNKNOWN",
            "RESTATEMENT_POLICY_UNKNOWN",
            "SOURCE_QUALITY_UNKNOWN",
        ],
        "operator_notes": (
            "Manifest present as a public US-fundamentals candidate only. "
            "Terms review, issuer mapping review, report-lag policy, restatement policy, and source-quality review "
            "must pass before any automated readiness unlock is allowed."
        ),
    },
    {
        "source_id": "stooq_price_context_manifest",
        "provider_id": "stooq_price_context",
        "source_name": "Stooq Price Context Manifest",
        "source_type": "market_price_context",
        "source_category": "manual_only",
        "source_status": "manual_research_only",
        "access_method": "manual_download",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "review_required",
        "license_terms_reference": "stooq_terms_review_required",
        "allowed_use": ["manual_research_context", "metadata_context", "operator_explanation"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "manual_lookup",
        "expected_freshness": "unknown",
        "asset_coverage": ["public_price_context"],
        "region_coverage": ["Europe", "Global", "US"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["price_context_only"],
        "point_in_time_support": "unsupported",
        "restatement_history_support": "unsupported",
        "report_lag_support": "unsupported",
        "currency_normalization_support": "unsupported",
        "corporate_action_adjustment_support": "unsupported",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "manual_context_only",
        "known_limitations": ["manual_context_only", "not_fundamental_source"],
        "required_quality_gates": ["license_reviewed"],
        "activation_requirements": ["operator_manual_review"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["LICENSE_REVIEW_REQUIRED"],
        "operator_notes": "Manual market context only. Does not address factor fields.",
    },
    {
        "source_id": "yahoo_finance_yfinance_manifest",
        "provider_id": "yahoo_finance_yfinance",
        "source_name": "Yahoo Finance / yfinance Manifest",
        "source_type": "manual_research_context",
        "source_category": "manual_only",
        "source_status": "manual_research_only",
        "access_method": "static_manifest",
        "authentication_required": False,
        "cost_model": "free",
        "license_terms_status": "reviewed_restricted",
        "license_terms_reference": "yahoo_finance_manual_research_restricted",
        "allowed_use": ["manual_research_context", "metadata_context", "operator_explanation"],
        "forbidden_use": [
            "broker_execution","buy_list","candidate_promotion","capital_allocation","fundamental_field_readiness",
            "live_activation","paper_activation","sell_list","shadow_activation","strategy_registration","trade_signal",
        ],
        "expected_latency": "library_dependent",
        "expected_freshness": "unknown",
        "asset_coverage": ["equities", "etfs", "price_context"],
        "region_coverage": ["Global"],
        "exchange_coverage": [],
        "factor_field_coverage_claims": ["convenience_only_untrusted"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "corporate_action_adjustment_support": "unknown",
        "survivorship_bias_risk": "unknown",
        "lookahead_bias_risk": "unknown",
        "known_limitations": ["licensing_uncertainty", "manual_context_only"],
        "required_quality_gates": ["license_reviewed", "operator_manual_review"],
        "activation_requirements": ["operator_manual_review"],
        "reproducibility_method": "static_registry_stub_only",
        "schema_version": SCHEMA_VERSION,
        "manifest_status": "WARN",
        "manifest_block_reasons": ["SOURCE_QUALITY_UNKNOWN"],
        "operator_notes": "Reviewed-restricted manual context only. Not valid for automated readiness.",
    },
)


def build_source_manifest_registry() -> dict[str, object]:
    provider_registry = build_fundamental_provider_registry()
    provider_rows = {str(row["provider_id"]): row for row in provider_registry["rows"]}
    rows = validate_source_manifest_rows(
        SOURCE_MANIFEST_ROWS,
        known_provider_ids=set(provider_rows),
    )
    policy_rows = [evaluate_license_policy(row) for row in rows]
    policy_by_source = {str(row["source_id"]): row for row in policy_rows}

    status_counts = Counter(str(row["manifest_status"]) for row in rows)
    source_type_counts = Counter(str(row["source_type"]) for row in rows)
    source_category_counts = Counter(str(row["source_category"]) for row in rows)
    policy_counts = Counter(str(row["license_policy_status"]) for row in policy_rows)
    license_status_counts = Counter(str(row["license_terms_status"]) for row in rows)

    quality_gated_eligible = [
        row["provider_id"]
        for row in policy_rows
        if bool(row["allowed_for_quality_gate"])
    ]
    active_read_only_eligible = [
        row["provider_id"]
        for row in policy_rows
        if bool(row["allowed_for_active_read_only"])
    ]
    blocked_by_license = [
        row["provider_id"]
        for row in policy_rows
        if row["license_policy_status"] in {"FAIL", "UNKNOWN", "WARN"}
    ]
    blocked_by_policy_gap = [
        row["provider_id"]
        for row in rows
        if {"POINT_IN_TIME_UNKNOWN", "REPORT_LAG_POLICY_UNKNOWN", "RESTATEMENT_POLICY_UNKNOWN"}
        & set(str(item) for item in row["manifest_block_reasons"])
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "source_manifest_registry",
        "summary": {
            "total_manifests": len(rows),
            "manifest_status_counts": dict(sorted(status_counts.items())),
            "source_type_counts": dict(sorted(source_type_counts.items())),
            "source_category_counts": dict(sorted(source_category_counts.items())),
            "license_policy_counts": dict(sorted(policy_counts.items())),
            "license_terms_status_counts": dict(sorted(license_status_counts.items())),
            "quality_gated_eligible_providers": sorted(quality_gated_eligible),
            "active_read_only_eligible_providers": sorted(active_read_only_eligible),
            "providers_blocked_by_license_policy": sorted(set(blocked_by_license)),
            "providers_blocked_by_policy_gaps": sorted(set(blocked_by_policy_gap)),
            "identity_only_sources": sorted(
                str(row["source_id"]) for row in rows if str(row["source_type"]) in IDENTITY_SOURCE_TYPES
            ),
            "metadata_only_sources": sorted(
                str(row["source_id"]) for row in rows if str(row["source_type"]) in METADATA_SOURCE_TYPES
            ),
            "fundamental_candidate_sources": sorted(
                str(row["source_id"]) for row in rows if str(row["source_type"]) in FUNDAMENTAL_SOURCE_TYPES
            ),
            "operator_summary": (
                "Source manifests are deterministic stubs only. No data has been fetched, no provider is activated, "
                "and manifest presence alone does not unlock recipe, hypothesis, or controlled evaluation readiness."
            ),
        },
        "rows": rows,
        "license_policy_rows": sorted(policy_rows, key=lambda item: str(item["source_id"])),
        "provider_rows": provider_registry["rows"],
        "policy_by_source": policy_by_source,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "no_data_fetch": True,
            "no_api_integration": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def build_source_license_policy_artifact(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": snapshot["schema_version"],
        "report_kind": "source_license_policy",
        "summary": {
            "license_policy_counts": snapshot["summary"]["license_policy_counts"],
            "license_terms_status_counts": snapshot["summary"]["license_terms_status_counts"],
            "quality_gated_eligible_providers": snapshot["summary"]["quality_gated_eligible_providers"],
            "active_read_only_eligible_providers": snapshot["summary"]["active_read_only_eligible_providers"],
            "providers_blocked_by_license_policy": snapshot["summary"]["providers_blocked_by_license_policy"],
        },
        "rows": snapshot["license_policy_rows"],
        "safety_invariants": snapshot["safety_invariants"],
    }


def build_source_manifest_quality_artifact(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": snapshot["schema_version"],
        "report_kind": "source_manifest_quality",
        "summary": snapshot["summary"],
        "rows": [
            {
                "source_id": row["source_id"],
                "provider_id": row["provider_id"],
                "source_type": row["source_type"],
                "source_category": row["source_category"],
                "manifest_status": row["manifest_status"],
                "manifest_block_reasons": row["manifest_block_reasons"],
                "license_policy_status": snapshot["policy_by_source"][str(row["source_id"])]["license_policy_status"],
            }
            for row in snapshot["rows"]
        ],
        "safety_invariants": snapshot["safety_invariants"],
    }


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"source_manifest_registry: refusing write outside allowlist: {path!r}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(*, repo_root: Path = Path("."), output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    manifest_path = base / MANIFESTS_NAME
    license_policy_path = base / LICENSE_POLICY_NAME
    quality_path = base / QUALITY_NAME
    for path in (manifest_path, license_policy_path, quality_path):
        _validate_write_target(path)
    snapshot = build_source_manifest_registry()
    _write_json(manifest_path, snapshot)
    _write_json(license_policy_path, build_source_license_policy_artifact(snapshot))
    _write_json(quality_path, build_source_manifest_quality_artifact(snapshot))
    return {
        "source_manifests": manifest_path.relative_to(repo_root).as_posix(),
        "source_license_policy": license_policy_path.relative_to(repo_root).as_posix(),
        "source_manifest_quality": quality_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.external_intelligence.source_manifest_registry",
        description="Write deterministic source manifest schema and license policy artifacts.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    snapshot = build_source_manifest_registry()
    payload = {
        "source_manifests": snapshot,
        "source_license_policy": build_source_license_policy_artifact(snapshot),
        "source_manifest_quality": build_source_manifest_quality_artifact(snapshot),
    }
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
