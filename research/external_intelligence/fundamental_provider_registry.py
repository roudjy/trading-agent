"""Deterministic research-only candidate registry for future fundamental providers."""

from __future__ import annotations

from collections import Counter
from typing import Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "fundamental_provider_candidates"
SOURCE_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "candidate",
    "manual_research_only",
    "staging",
    "quality_gated",
    "active_read_only",
    "deprecated",
    "blocked",
)
ALLOWED_USE_VOCABULARY: Final[tuple[str, ...]] = (
    "source_candidate_research",
    "identity_mapping",
    "metadata_context",
    "fundamental_field_candidate",
    "manual_research_context",
    "connector_discovery",
    "operator_explanation",
)
FORBIDDEN_USE: Final[tuple[str, ...]] = (
    "trade_signal",
    "buy_list",
    "sell_list",
    "strategy_registration",
    "candidate_promotion",
    "paper_activation",
    "shadow_activation",
    "live_activation",
    "capital_allocation",
    "broker_execution",
)
ACTIVE_READ_ONLY_REQUIREMENTS: Final[tuple[str, ...]] = (
    "source_manifest_defined",
    "license_reviewed",
    "quality_gate_signed_off",
    "point_in_time_policy_defined",
    "report_lag_policy_defined",
    "restatement_policy_defined",
)


PROVIDER_ROWS: Final[tuple[dict[str, object], ...]] = (
    {
        "provider_id": "alpha_vantage_candidate",
        "provider_name": "Alpha Vantage",
        "provider_category": "fundamental_api_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "fundamental_field_candidate",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["US", "Europe", "Asia"],
        "factor_field_coverage_potential": [
            "income_statement_ready",
            "balance_sheet_ready",
            "cash_flow_statement_ready",
            "price_history_complete",
        ],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": True,
        "cost_model": "freemium_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "provider_public_terms_reference_required",
        "expected_freshness": "daily_or_slower_unknown",
        "expected_latency": "api_latency_unknown",
        "implementation_priority": 7,
        "risk_level": "medium",
        "known_limitations": [
            "license_terms_not_reviewed",
            "point_in_time_semantics_unknown",
            "rate_limits_not_modeled",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "point_in_time_policy_defined",
            "report_lag_policy_defined",
            "restatement_policy_defined",
            "field_coverage_manifest_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Candidate only. No keys, no fetching, no trust assignment in this phase.",
    },
    {
        "provider_id": "companies_house_metadata",
        "provider_name": "Companies House",
        "provider_category": "issuer_registry_metadata",
        "source_status": "manual_research_only",
        "allowed_use": [
            "manual_research_context",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["uk_equities_metadata"],
        "region_coverage": ["United Kingdom"],
        "factor_field_coverage_potential": ["issuer_identity_context", "filing_presence_context"],
        "point_in_time_support": "metadata_only",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "not_applicable",
        "authentication_required": False,
        "cost_model": "public_manual_research",
        "license_terms_status": "public_site_review_required",
        "license_terms_reference": "companies_house_terms_manual_review_required",
        "expected_freshness": "issuer_registry_schedule_unknown",
        "expected_latency": "manual_lookup",
        "implementation_priority": 11,
        "risk_level": "low",
        "known_limitations": [
            "not_a_fundamental_dataset",
            "manual_context_only",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
        ],
        "activation_requirements": [
            "operator_manual_review",
            "source_manifest_defined",
        ],
        "operator_notes": "Useful for issuer metadata context only; not a direct factor source.",
    },
    {
        "provider_id": "eodhd_candidate",
        "provider_name": "EOD Historical Data",
        "provider_category": "fundamental_api_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "fundamental_field_candidate",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["US", "Europe", "Asia", "Global"],
        "factor_field_coverage_potential": [
            "income_statement_ready",
            "balance_sheet_ready",
            "cash_flow_statement_ready",
            "dividend_history_context",
            "price_history_complete",
        ],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": True,
        "cost_model": "paid_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "provider_public_terms_reference_required",
        "expected_freshness": "daily_or_vendor_defined",
        "expected_latency": "api_latency_unknown",
        "implementation_priority": 6,
        "risk_level": "medium",
        "known_limitations": [
            "paid_vendor_candidate_only",
            "license_terms_not_reviewed",
            "point_in_time_semantics_unknown",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "point_in_time_policy_defined",
            "field_coverage_manifest_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Candidate only. Paid/vendor status alone does not imply trust or readiness.",
    },
    {
        "provider_id": "euronext_issuer_metadata",
        "provider_name": "Euronext Public Issuer Metadata",
        "provider_category": "exchange_metadata_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "identity_mapping",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["europe_equities_metadata"],
        "region_coverage": ["Netherlands", "Belgium", "France", "Portugal", "Ireland"],
        "factor_field_coverage_potential": ["issuer_metadata", "listing_metadata", "venue_context"],
        "point_in_time_support": "metadata_only",
        "restatement_history_support": "not_applicable",
        "report_lag_support": "not_applicable",
        "currency_normalization_support": "metadata_only",
        "authentication_required": False,
        "cost_model": "public_metadata_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "euronext_public_terms_manual_review_required",
        "expected_freshness": "exchange_maintenance_schedule_unknown",
        "expected_latency": "manual_or_http_metadata",
        "implementation_priority": 3,
        "risk_level": "low",
        "known_limitations": [
            "metadata_not_fundamentals",
            "license_terms_not_reviewed",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "activation_requirements": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "operator_notes": "High-value identity context candidate for EU listings; not a factor field source.",
    },
    {
        "provider_id": "financial_datasets_mcp",
        "provider_name": "Financial Datasets MCP",
        "provider_category": "connector_candidate",
        "source_status": "staging",
        "allowed_use": [
            "connector_discovery",
            "source_candidate_research",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["unknown_until_manifested"],
        "region_coverage": ["unknown_until_manifested"],
        "factor_field_coverage_potential": ["unknown_until_manifested"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": "unknown",
        "cost_model": "unknown",
        "license_terms_status": "unknown",
        "license_terms_reference": "operator_manifest_required",
        "expected_freshness": "unknown",
        "expected_latency": "unknown",
        "implementation_priority": 12,
        "risk_level": "medium",
        "known_limitations": [
            "connector_only",
            "no_license_review",
            "no_source_manifest",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "connector_contract_reviewed",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Staging only. Connector discovery does not imply data trust or source authority.",
    },
    {
        "provider_id": "financial_modeling_prep_candidate",
        "provider_name": "Financial Modeling Prep",
        "provider_category": "fundamental_api_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "fundamental_field_candidate",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["equities", "etfs"],
        "region_coverage": ["US", "Europe", "Asia", "Global"],
        "factor_field_coverage_potential": [
            "income_statement_ready",
            "balance_sheet_ready",
            "cash_flow_statement_ready",
            "enterprise_value_ready",
            "price_history_complete",
        ],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": True,
        "cost_model": "freemium_or_paid_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "provider_public_terms_reference_required",
        "expected_freshness": "vendor_defined_unknown",
        "expected_latency": "api_latency_unknown",
        "implementation_priority": 5,
        "risk_level": "medium",
        "known_limitations": [
            "license_terms_not_reviewed",
            "point_in_time_semantics_unknown",
            "restatement_support_unknown",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "point_in_time_policy_defined",
            "field_coverage_manifest_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Candidate only. No API integration or key management in this PR.",
    },
    {
        "provider_id": "nasdaq_listings_metadata",
        "provider_name": "Nasdaq Listings Metadata",
        "provider_category": "exchange_metadata_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "identity_mapping",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["us_listings_metadata"],
        "region_coverage": ["United States"],
        "factor_field_coverage_potential": ["listing_metadata", "issuer_metadata", "venue_context"],
        "point_in_time_support": "metadata_only",
        "restatement_history_support": "not_applicable",
        "report_lag_support": "not_applicable",
        "currency_normalization_support": "metadata_only",
        "authentication_required": False,
        "cost_model": "public_metadata_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "nasdaq_public_terms_manual_review_required",
        "expected_freshness": "listing_file_schedule_unknown",
        "expected_latency": "manual_or_http_metadata",
        "implementation_priority": 4,
        "risk_level": "low",
        "known_limitations": [
            "metadata_not_fundamentals",
            "license_terms_not_reviewed",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "activation_requirements": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "operator_notes": "Useful for US symbology/listing metadata only; not a valuation source.",
    },
    {
        "provider_id": "nyse_listings_metadata",
        "provider_name": "NYSE Listings Metadata",
        "provider_category": "exchange_metadata_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "identity_mapping",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["us_listings_metadata"],
        "region_coverage": ["United States"],
        "factor_field_coverage_potential": ["listing_metadata", "issuer_metadata", "venue_context"],
        "point_in_time_support": "metadata_only",
        "restatement_history_support": "not_applicable",
        "report_lag_support": "not_applicable",
        "currency_normalization_support": "metadata_only",
        "authentication_required": False,
        "cost_model": "public_metadata_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "nyse_public_terms_manual_review_required",
        "expected_freshness": "listing_file_schedule_unknown",
        "expected_latency": "manual_or_http_metadata",
        "implementation_priority": 4,
        "risk_level": "low",
        "known_limitations": [
            "metadata_not_fundamentals",
            "license_terms_not_reviewed",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "activation_requirements": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "operator_notes": "Useful for US venue metadata only; no trust assignment to fundamentals.",
    },
    {
        "provider_id": "openbb_connector",
        "provider_name": "OpenBB",
        "provider_category": "connector_candidate",
        "source_status": "staging",
        "allowed_use": [
            "connector_discovery",
            "source_candidate_research",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["multi_asset_connector_surface"],
        "region_coverage": ["Global"],
        "factor_field_coverage_potential": ["connector_surface_only"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": "unknown",
        "cost_model": "connector_only_unknown",
        "license_terms_status": "unknown",
        "license_terms_reference": "operator_manifest_required",
        "expected_freshness": "depends_on_downstream_provider",
        "expected_latency": "depends_on_downstream_provider",
        "implementation_priority": 13,
        "risk_level": "medium",
        "known_limitations": [
            "connector_only",
            "not_a_trusted_source",
            "downstream_license_status_unknown",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "downstream_provider_manifest_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Staging only. Connector indirection cannot bypass source manifest and licensing policy.",
    },
    {
        "provider_id": "openfigi_symbology",
        "provider_name": "OpenFIGI",
        "provider_category": "symbology_candidate",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "identity_mapping",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["equities", "etfs", "multi_listing_symbology"],
        "region_coverage": ["Global"],
        "factor_field_coverage_potential": ["identity_only_not_fundamentals"],
        "point_in_time_support": "identity_only",
        "restatement_history_support": "not_applicable",
        "report_lag_support": "not_applicable",
        "currency_normalization_support": "metadata_only",
        "authentication_required": False,
        "cost_model": "public_or_limited_use_candidate",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "openfigi_terms_manual_review_required",
        "expected_freshness": "symbology_reference_schedule_unknown",
        "expected_latency": "api_or_manual_lookup_unknown",
        "implementation_priority": 2,
        "risk_level": "low",
        "known_limitations": [
            "not_a_fundamental_source",
            "symbology_only",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "activation_requirements": [
            "source_manifest_defined",
            "license_reviewed",
            "identity_mapping_quality_gate",
        ],
        "operator_notes": "High-priority symbology candidate. Useful for canonical identity, not for factor fields.",
    },
    {
        "provider_id": "sec_companyfacts",
        "provider_name": "SEC EDGAR Company Facts",
        "provider_category": "public_fundamental_filings",
        "source_status": "candidate",
        "allowed_use": [
            "source_candidate_research",
            "fundamental_field_candidate",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["us_equities"],
        "region_coverage": ["United States"],
        "factor_field_coverage_potential": [
            "income_statement_ready",
            "balance_sheet_ready",
            "cash_flow_statement_ready",
            "multi_period_fundamentals",
        ],
        "point_in_time_support": "candidate_with_policy_required",
        "restatement_history_support": "candidate_with_policy_required",
        "report_lag_support": "candidate_with_policy_required",
        "currency_normalization_support": "mostly_usd_but_policy_required",
        "authentication_required": False,
        "cost_model": "public_access_candidate",
        "license_terms_status": "public_source_review_required",
        "license_terms_reference": "sec_edgar_terms_manual_review_required",
        "expected_freshness": "filing_driven",
        "expected_latency": "public_endpoint_latency_unknown",
        "implementation_priority": 1,
        "risk_level": "low",
        "known_limitations": [
            "us_only",
            "point_in_time_policy_not_defined",
            "restatement_policy_not_defined",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
            "point_in_time_policy_defined",
            "report_lag_policy_defined",
            "restatement_policy_defined",
            "field_coverage_manifest_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Highest-priority public candidate for US fundamentals, but still untrusted until full source-manifest and policy gates exist.",
    },
    {
        "provider_id": "stooq_price_context",
        "provider_name": "Stooq",
        "provider_category": "public_price_context",
        "source_status": "manual_research_only",
        "allowed_use": [
            "manual_research_context",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["public_price_context"],
        "region_coverage": ["Europe", "US", "Global"],
        "factor_field_coverage_potential": ["price_context_only"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "not_applicable",
        "report_lag_support": "not_applicable",
        "currency_normalization_support": "unknown",
        "authentication_required": False,
        "cost_model": "public_manual_research",
        "license_terms_status": "manual_review_required",
        "license_terms_reference": "stooq_terms_manual_review_required",
        "expected_freshness": "unknown",
        "expected_latency": "manual_lookup",
        "implementation_priority": 14,
        "risk_level": "low",
        "known_limitations": [
            "not_a_fundamental_source",
            "manual_context_only",
        ],
        "required_quality_gates": [
            "source_manifest_defined",
            "license_reviewed",
        ],
        "activation_requirements": [
            "operator_manual_review",
            "source_manifest_defined",
        ],
        "operator_notes": "Only relevant as manual price context. It does not address fundamental field coverage.",
    },
    {
        "provider_id": "yahoo_finance_yfinance",
        "provider_name": "Yahoo Finance / yfinance",
        "provider_category": "public_convenience_dataset",
        "source_status": "manual_research_only",
        "allowed_use": [
            "manual_research_context",
            "metadata_context",
            "operator_explanation",
        ],
        "forbidden_use": list(FORBIDDEN_USE),
        "asset_coverage": ["equities", "etfs", "price_context"],
        "region_coverage": ["Global"],
        "factor_field_coverage_potential": ["convenience_only_untrusted"],
        "point_in_time_support": "unknown",
        "restatement_history_support": "unknown",
        "report_lag_support": "unknown",
        "currency_normalization_support": "unknown",
        "authentication_required": False,
        "cost_model": "public_convenience_candidate",
        "license_terms_status": "licensing_warning",
        "license_terms_reference": "manual_license_review_required_before_any_manifest",
        "expected_freshness": "unknown",
        "expected_latency": "library_dependent",
        "implementation_priority": 15,
        "risk_level": "high",
        "known_limitations": [
            "licensing_uncertainty",
            "point_in_time_semantics_unknown",
            "restatement_semantics_unknown",
        ],
        "required_quality_gates": [
            "license_reviewed",
            "source_manifest_defined",
            "point_in_time_policy_defined",
        ],
        "activation_requirements": list(ACTIVE_READ_ONLY_REQUIREMENTS),
        "operator_notes": "Manual-research-only with explicit licensing warning. Not trusted for gated factor evaluation.",
    },
)


def validate_provider_rows(rows: list[dict[str, object]] | tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    validated: list[dict[str, object]] = []
    seen_provider_ids: set[str] = set()
    for row in rows:
        provider_id = str(row["provider_id"])
        if provider_id in seen_provider_ids:
            raise ValueError(f"duplicate provider_id: {provider_id}")
        seen_provider_ids.add(provider_id)
        status = str(row["source_status"])
        if status not in SOURCE_STATUS_VOCABULARY:
            raise ValueError(f"invalid source_status for {provider_id}: {status}")
        allowed_use = [str(item) for item in row["allowed_use"]]
        for item in allowed_use:
            if item not in ALLOWED_USE_VOCABULARY:
                raise ValueError(f"invalid allowed_use for {provider_id}: {item}")
        forbidden_use = [str(item) for item in row["forbidden_use"]]
        missing_forbidden = sorted(set(FORBIDDEN_USE) - set(forbidden_use))
        if missing_forbidden:
            raise ValueError(f"{provider_id} missing forbidden_use entries: {missing_forbidden}")
        license_status = str(row["license_terms_status"])
        if license_status in {"unknown", "manual_review_required", "licensing_warning", "public_source_review_required"}:
            if status in {"quality_gated", "active_read_only"}:
                raise ValueError(
                    f"{provider_id} cannot be {status} while license_terms_status={license_status}"
                )
        point_in_time_support = str(row["point_in_time_support"])
        if point_in_time_support == "unknown" and status == "active_read_only":
            raise ValueError(f"{provider_id} cannot be active_read_only with unknown point_in_time_support")
        if status == "active_read_only":
            activation_requirements = {str(item) for item in row["activation_requirements"]}
            missing_requirements = sorted(set(ACTIVE_READ_ONLY_REQUIREMENTS) - activation_requirements)
            if missing_requirements:
                raise ValueError(
                    f"{provider_id} missing active_read_only requirements: {missing_requirements}"
                )
        validated.append(
            {
                **row,
                "allowed_use": sorted(allowed_use),
                "forbidden_use": list(FORBIDDEN_USE),
                "asset_coverage": sorted(str(item) for item in row["asset_coverage"]),
                "region_coverage": sorted(str(item) for item in row["region_coverage"]),
                "factor_field_coverage_potential": sorted(
                    str(item) for item in row["factor_field_coverage_potential"]
                ),
                "known_limitations": sorted(str(item) for item in row["known_limitations"]),
                "required_quality_gates": sorted(str(item) for item in row["required_quality_gates"]),
                "activation_requirements": sorted(str(item) for item in row["activation_requirements"]),
            }
        )
    validated.sort(key=lambda item: str(item["provider_id"]))
    return validated


def build_fundamental_provider_registry() -> dict[str, object]:
    rows = validate_provider_rows(PROVIDER_ROWS)
    status_counts = Counter(str(row["source_status"]) for row in rows)
    priority_rows = sorted(
        rows,
        key=lambda item: (
            int(item["implementation_priority"]),
            str(item["risk_level"]),
            str(item["provider_id"]),
        ),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "source_status_vocabulary": list(SOURCE_STATUS_VOCABULARY),
        "allowed_use_vocabulary": list(ALLOWED_USE_VOCABULARY),
        "forbidden_use_vocabulary": list(FORBIDDEN_USE),
        "summary": {
            "total_providers": len(rows),
            "candidate_count": status_counts.get("candidate", 0),
            "manual_research_only_count": status_counts.get("manual_research_only", 0),
            "staging_count": status_counts.get("staging", 0),
            "quality_gated_count": status_counts.get("quality_gated", 0),
            "active_read_only_count": status_counts.get("active_read_only", 0),
            "deprecated_count": status_counts.get("deprecated", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "highest_priority_candidates": [
                {
                    "provider_id": row["provider_id"],
                    "provider_name": row["provider_name"],
                    "source_status": row["source_status"],
                    "implementation_priority": row["implementation_priority"],
                    "reason": row["operator_notes"],
                }
                for row in priority_rows[:5]
            ],
            "operator_summary": (
                "Provider registry is research-only candidate governance. "
                "No data has been fetched, no provider is trusted by default, and no source becomes active without "
                "license review, source manifests, quality gates, and point-in-time policy."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "no_data_fetch": True,
            "no_api_integration": True,
            "no_vendor_activation": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
