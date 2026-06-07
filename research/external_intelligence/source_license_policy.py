"""Deterministic license policy evaluation for source manifests."""

from __future__ import annotations

from research.external_intelligence.source_manifest_schema import (
    BLOCK_REASON_VOCABULARY,
    FUNDAMENTAL_SOURCE_TYPES,
    LICENSE_POLICY_STATUS_VOCABULARY,
)


def evaluate_license_policy(manifest: dict[str, object]) -> dict[str, object]:
    """Return a deterministic policy result for a single source manifest."""

    block_reasons: list[str] = []
    warnings: list[str] = []
    license_terms_status = str(manifest["license_terms_status"])
    source_status = str(manifest["source_status"])
    source_type = str(manifest["source_type"])

    if license_terms_status == "blocked":
        policy_status = "FAIL"
        block_reasons.append("LICENSE_BLOCKED")
        allowed_for_quality_gate = False
        allowed_for_active_read_only = False
    elif license_terms_status == "unknown":
        policy_status = "UNKNOWN"
        block_reasons.append("MISSING_LICENSE_TERMS")
        allowed_for_quality_gate = False
        allowed_for_active_read_only = False
    elif license_terms_status == "review_required":
        policy_status = "WARN"
        block_reasons.append("LICENSE_REVIEW_REQUIRED")
        allowed_for_quality_gate = False
        allowed_for_active_read_only = False
    elif license_terms_status == "reviewed_restricted":
        policy_status = "WARN"
        warnings.append("reviewed_restricted_source_requires_narrow_manual_use")
        allowed_for_quality_gate = False
        allowed_for_active_read_only = False
    else:
        policy_status = "PASS"
        allowed_for_quality_gate = True
        allowed_for_active_read_only = True

    if not str(manifest["license_terms_reference"]):
        if license_terms_status == "reviewed_allowed":
            policy_status = "FAIL"
            block_reasons.append("MISSING_LICENSE_TERMS")
            allowed_for_quality_gate = False
            allowed_for_active_read_only = False
        else:
            warnings.append("missing_license_terms_reference")

    if source_status == "active_read_only" and not allowed_for_active_read_only:
        policy_status = "FAIL"
        block_reasons.append("LICENSE_BLOCKED" if license_terms_status == "blocked" else "LICENSE_REVIEW_REQUIRED")

    if source_status == "quality_gated" and not allowed_for_quality_gate:
        if policy_status != "FAIL":
            policy_status = "WARN"
        if license_terms_status in {"unknown", "review_required"}:
            block_reasons.append(
                "MISSING_LICENSE_TERMS" if license_terms_status == "unknown" else "LICENSE_REVIEW_REQUIRED"
            )

    if source_type not in FUNDAMENTAL_SOURCE_TYPES:
        warnings.append("source_type_does_not_satisfy_fundamental_field_readiness")

    if str(manifest["access_method"]) == "connector":
        warnings.append("connector_wrapper_requires_underlying_source_manifest")

    if policy_status not in LICENSE_POLICY_STATUS_VOCABULARY:
        raise ValueError(f"invalid license policy status: {policy_status}")
    for item in block_reasons:
        if item not in BLOCK_REASON_VOCABULARY:
            raise ValueError(f"invalid block reason: {item}")

    explanation = (
        "License policy pass requires reviewed_allowed terms plus downstream source-quality and policy gates."
        if policy_status == "PASS"
        else "License policy remains fail-closed until terms review and downstream policy gates are explicit."
    )
    return {
        "source_id": manifest["source_id"],
        "provider_id": manifest["provider_id"],
        "license_terms_status": license_terms_status,
        "license_policy_status": policy_status,
        "allowed_for_quality_gate": allowed_for_quality_gate,
        "allowed_for_active_read_only": allowed_for_active_read_only,
        "block_reasons": sorted(set(block_reasons)),
        "warnings": sorted(set(warnings)),
        "operator_explanation": explanation,
    }
