from __future__ import annotations

from research.external_intelligence.source_license_policy import evaluate_license_policy
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


def _manifest(source_id: str) -> dict[str, object]:
    snapshot = build_source_manifest_registry()
    return next(row for row in snapshot["rows"] if row["source_id"] == source_id)


def test_unknown_license_blocks_quality_gated_and_active_read_only() -> None:
    row = _manifest("openbb_connector_manifest")
    result = evaluate_license_policy(row)
    assert result["license_policy_status"] == "UNKNOWN"
    assert result["allowed_for_quality_gate"] is False
    assert result["allowed_for_active_read_only"] is False


def test_review_required_blocks_active_read_only() -> None:
    row = _manifest("sec_companyfacts_manifest")
    result = evaluate_license_policy(row)
    assert result["license_policy_status"] == "WARN"
    assert result["allowed_for_active_read_only"] is False
    assert "LICENSE_REVIEW_REQUIRED" in result["block_reasons"]


def test_reviewed_restricted_is_manual_only_and_not_automated_readiness() -> None:
    row = _manifest("yahoo_finance_yfinance_manifest")
    result = evaluate_license_policy(row)
    assert result["license_policy_status"] == "WARN"
    assert result["allowed_for_quality_gate"] is False
    assert "source_type_does_not_satisfy_fundamental_field_readiness" in result["warnings"]


def test_connector_wrapper_and_identity_only_do_not_inherit_trust() -> None:
    connector = evaluate_license_policy(_manifest("financial_datasets_mcp_manifest"))
    identity = evaluate_license_policy(_manifest("openfigi_symbology_manifest"))
    assert "connector_wrapper_requires_underlying_source_manifest" in connector["warnings"]
    assert "source_type_does_not_satisfy_fundamental_field_readiness" in identity["warnings"]
