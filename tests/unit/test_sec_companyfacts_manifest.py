from __future__ import annotations

from research.data_readiness.fundamental_readiness import build_fundamental_readiness
from research.external_intelligence.source_license_policy import evaluate_license_policy
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


def _sec_row() -> dict[str, object]:
    snapshot = build_source_manifest_registry()
    return next(row for row in snapshot["rows"] if row["source_id"] == "sec_companyfacts_manifest")


def test_sec_companyfacts_manifest_is_hardened_but_not_activated() -> None:
    row = _sec_row()
    assert row["access_method"] == "public_api"
    assert row["source_status"] == "candidate"
    assert row["license_terms_status"] == "review_required"
    assert row["point_in_time_support"] == "partially_supported"
    assert row["report_lag_support"] == "unknown"
    assert row["restatement_history_support"] == "unknown"
    assert "FACTOR_FIELD_COVERAGE_UNKNOWN" not in row["manifest_block_reasons"]
    assert "issuer_to_symbol_mapping_reviewed" in row["required_quality_gates"]
    assert "issuer_to_symbol_mapping_reviewed" in row["activation_requirements"]


def test_sec_companyfacts_license_policy_still_blocks_quality_gate() -> None:
    result = evaluate_license_policy(_sec_row())
    assert result["license_policy_status"] == "WARN"
    assert result["allowed_for_quality_gate"] is False
    assert result["allowed_for_active_read_only"] is False
    assert "LICENSE_REVIEW_REQUIRED" in result["block_reasons"]


def test_sec_companyfacts_manifest_presence_does_not_unlock_readiness() -> None:
    report = build_fundamental_readiness()
    assert report["summary"]["ready_count"] == 0
    sec_sensitive_rows = [
        row for row in report["factor_rows"] if row["point_in_time_required"]
    ]
    assert sec_sensitive_rows
    for row in sec_sensitive_rows:
        assert "LICENSE_REVIEW_REQUIRED" in row["readiness_block_reasons"]
        assert "MISSING_REPORT_LAG_POLICY" in row["readiness_block_reasons"]
        assert "MISSING_RESTATEMENT_POLICY" in row["readiness_block_reasons"]
