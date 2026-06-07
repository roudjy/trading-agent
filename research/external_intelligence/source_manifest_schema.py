"""Deterministic schema contracts for read-only source manifests."""

from __future__ import annotations

from typing import Final


SCHEMA_VERSION: Final[str] = "1.0"
SOURCE_TYPE_VOCABULARY: Final[tuple[str, ...]] = (
    "identity_symbology",
    "issuer_metadata",
    "listing_metadata",
    "fundamental_statement_data",
    "fundamental_ratio_data",
    "market_price_context",
    "connector_staging",
    "manual_research_context",
    "unknown",
)
SOURCE_CATEGORY_VOCABULARY: Final[tuple[str, ...]] = (
    "public_free",
    "public_with_terms",
    "free_api_limited",
    "paid_vendor_candidate",
    "connector_wrapper",
    "manual_only",
    "internal_fixture",
    "unknown",
)
SOURCE_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "candidate",
    "manual_research_only",
    "staging",
    "quality_gated",
    "active_read_only",
    "deprecated",
    "blocked",
)
ACCESS_METHOD_VOCABULARY: Final[tuple[str, ...]] = (
    "static_manifest",
    "public_download",
    "public_api",
    "manual_download",
    "connector",
    "fixture",
    "unknown",
)
COST_MODEL_VOCABULARY: Final[tuple[str, ...]] = (
    "free",
    "free_limited",
    "paid",
    "mixed",
    "unknown",
)
LICENSE_TERMS_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "reviewed_allowed",
    "reviewed_restricted",
    "review_required",
    "unknown",
    "blocked",
)
SUPPORT_VOCABULARY: Final[tuple[str, ...]] = (
    "supported",
    "partially_supported",
    "unsupported",
    "unknown",
)
MANIFEST_STATUS_VOCABULARY: Final[tuple[str, ...]] = ("VALID", "WARN", "FAIL", "UNKNOWN")
LICENSE_POLICY_STATUS_VOCABULARY: Final[tuple[str, ...]] = ("PASS", "WARN", "FAIL", "UNKNOWN")
ALLOWED_USE_VOCABULARY: Final[tuple[str, ...]] = (
    "source_candidate_research",
    "identity_mapping",
    "metadata_context",
    "fundamental_field_candidate",
    "manual_research_context",
    "connector_discovery",
    "operator_explanation",
)
FORBIDDEN_USE_VOCABULARY: Final[tuple[str, ...]] = (
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
    "fundamental_field_readiness",
)
BLOCK_REASON_VOCABULARY: Final[tuple[str, ...]] = (
    "MISSING_PROVIDER_ID",
    "UNKNOWN_PROVIDER",
    "MISSING_LICENSE_TERMS",
    "LICENSE_REVIEW_REQUIRED",
    "LICENSE_BLOCKED",
    "MISSING_ALLOWED_USE",
    "MISSING_FORBIDDEN_USE",
    "MISSING_REPRODUCIBILITY_METHOD",
    "MISSING_QUALITY_GATES",
    "POINT_IN_TIME_UNKNOWN",
    "RESTATEMENT_POLICY_UNKNOWN",
    "REPORT_LAG_POLICY_UNKNOWN",
    "FACTOR_FIELD_COVERAGE_UNKNOWN",
    "SOURCE_QUALITY_UNKNOWN",
    "ACCESS_METHOD_UNKNOWN",
    "COST_MODEL_UNKNOWN",
    "UNKNOWN",
)
FUNDAMENTAL_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "fundamental_statement_data",
    "fundamental_ratio_data",
)
IDENTITY_SOURCE_TYPES: Final[tuple[str, ...]] = ("identity_symbology",)
METADATA_SOURCE_TYPES: Final[tuple[str, ...]] = ("issuer_metadata", "listing_metadata")


def validate_source_manifest_rows(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    known_provider_ids: set[str],
) -> list[dict[str, object]]:
    """Validate and normalize source manifests."""

    validated: list[dict[str, object]] = []
    seen_source_ids: set[str] = set()
    for row in rows:
        source_id = str(row["source_id"])
        if source_id in seen_source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)

        provider_id = str(row["provider_id"])
        if not provider_id:
            raise ValueError(f"{source_id} missing provider_id")
        if provider_id not in known_provider_ids:
            raise ValueError(f"{source_id} references unknown provider_id: {provider_id}")

        for field_name, vocabulary in (
            ("source_type", SOURCE_TYPE_VOCABULARY),
            ("source_category", SOURCE_CATEGORY_VOCABULARY),
            ("source_status", SOURCE_STATUS_VOCABULARY),
            ("access_method", ACCESS_METHOD_VOCABULARY),
            ("cost_model", COST_MODEL_VOCABULARY),
            ("license_terms_status", LICENSE_TERMS_STATUS_VOCABULARY),
            ("point_in_time_support", SUPPORT_VOCABULARY),
            ("restatement_history_support", SUPPORT_VOCABULARY),
            ("report_lag_support", SUPPORT_VOCABULARY),
            ("currency_normalization_support", SUPPORT_VOCABULARY),
            ("corporate_action_adjustment_support", SUPPORT_VOCABULARY),
            ("manifest_status", MANIFEST_STATUS_VOCABULARY),
        ):
            value = str(row[field_name])
            if value not in vocabulary:
                raise ValueError(f"{source_id} invalid {field_name}: {value}")

        allowed_use = sorted(str(item) for item in row["allowed_use"])
        if not allowed_use:
            raise ValueError(f"{source_id} missing allowed_use")
        for item in allowed_use:
            if item not in ALLOWED_USE_VOCABULARY:
                raise ValueError(f"{source_id} invalid allowed_use: {item}")

        forbidden_use = sorted(str(item) for item in row["forbidden_use"])
        if not forbidden_use:
            raise ValueError(f"{source_id} missing forbidden_use")
        for item in forbidden_use:
            if item not in FORBIDDEN_USE_VOCABULARY:
                raise ValueError(f"{source_id} invalid forbidden_use: {item}")
        if "fundamental_field_readiness" not in forbidden_use and str(row["source_type"]) in (
            *IDENTITY_SOURCE_TYPES,
            *METADATA_SOURCE_TYPES,
            "connector_staging",
            "manual_research_context",
        ):
            raise ValueError(f"{source_id} must forbid fundamental_field_readiness")

        if not str(row["reproducibility_method"]):
            raise ValueError(f"{source_id} missing reproducibility_method")
        if not list(row["required_quality_gates"]):
            raise ValueError(f"{source_id} missing required_quality_gates")
        if not str(row["license_terms_reference"]):
            raise ValueError(f"{source_id} missing license_terms_reference")
        if not str(row["schema_version"]):
            raise ValueError(f"{source_id} missing schema_version")

        manifest_block_reasons = sorted(str(item) for item in row["manifest_block_reasons"])
        for item in manifest_block_reasons:
            if item not in BLOCK_REASON_VOCABULARY:
                raise ValueError(f"{source_id} invalid manifest_block_reasons entry: {item}")

        validated.append(
            {
                **row,
                "allowed_use": allowed_use,
                "forbidden_use": forbidden_use,
                "asset_coverage": sorted(str(item) for item in row["asset_coverage"]),
                "region_coverage": sorted(str(item) for item in row["region_coverage"]),
                "exchange_coverage": sorted(str(item) for item in row["exchange_coverage"]),
                "factor_field_coverage_claims": sorted(
                    str(item) for item in row["factor_field_coverage_claims"]
                ),
                "known_limitations": sorted(str(item) for item in row["known_limitations"]),
                "required_quality_gates": sorted(str(item) for item in row["required_quality_gates"]),
                "activation_requirements": sorted(str(item) for item in row["activation_requirements"]),
                "manifest_block_reasons": manifest_block_reasons,
            }
        )
    validated.sort(key=lambda item: str(item["source_id"]))
    return validated
