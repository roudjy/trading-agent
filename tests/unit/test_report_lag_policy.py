from __future__ import annotations

from research.data_readiness.report_lag_policy import build_report_lag_policy


def test_report_lag_policy_is_deterministic_and_fail_closed() -> None:
    left = build_report_lag_policy()
    right = build_report_lag_policy()
    assert left == right
    assert left["summary"]["required_count"] >= 1


def test_report_lag_policy_keeps_sec_blocked_and_identity_sources_not_required() -> None:
    rows = {row["source_id"]: row for row in build_report_lag_policy()["rows"]}
    sec = rows["sec_companyfacts_manifest"]
    openfigi = rows["openfigi_symbology_manifest"]
    assert sec["requirement_status"] == "REQUIRED"
    assert "MISSING_REPORT_LAG_POLICY" in sec["block_reasons"]
    assert "REPORT_LAG_UNKNOWN" in sec["block_reasons"]
    assert openfigi["policy_status"] == "NOT_REQUIRED"
