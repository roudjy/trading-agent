from __future__ import annotations

from research.data_readiness.fundamental_readiness import build_fundamental_readiness
from research.external_intelligence.source_license_policy import evaluate_license_policy
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


def _openfigi_row() -> dict[str, object]:
    snapshot = build_source_manifest_registry()
    return next(row for row in snapshot["rows"] if row["source_id"] == "openfigi_symbology_manifest")


def test_openfigi_manifest_is_explicitly_identity_only() -> None:
    row = _openfigi_row()
    assert row["access_method"] == "public_api"
    assert row["source_type"] == "identity_symbology"
    assert row["source_status"] == "candidate"
    assert "identity_mapping" in row["allowed_use"]
    assert "metadata_context" in row["allowed_use"]
    assert "fundamental_field_readiness" in row["forbidden_use"]
    assert "alias_resolution_reviewed" in row["required_quality_gates"]
    assert "operator_api_usage_approval" in row["activation_requirements"]


def test_openfigi_license_policy_remains_fail_closed() -> None:
    result = evaluate_license_policy(_openfigi_row())
    assert result["license_policy_status"] == "WARN"
    assert result["allowed_for_quality_gate"] is False
    assert result["allowed_for_active_read_only"] is False
    assert "source_type_does_not_satisfy_fundamental_field_readiness" in result["warnings"]


def test_openfigi_does_not_unlock_fundamental_readiness() -> None:
    report = build_fundamental_readiness()
    assert report["summary"]["ready_count"] == 0
    first_factor = report["factor_rows"][0]
    assert "MISSING_REQUIRED_FIELD" in first_factor["readiness_block_reasons"] or "FACTOR_FIELD_COVERAGE_UNKNOWN" in first_factor["readiness_block_reasons"]
