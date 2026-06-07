from __future__ import annotations

from research.data_readiness.point_in_time_policy import build_point_in_time_policy


def test_point_in_time_policy_is_deterministic_and_fail_closed() -> None:
    left = build_point_in_time_policy()
    right = build_point_in_time_policy()
    assert left == right
    assert left["summary"]["required_count"] >= 1


def test_sec_companyfacts_and_openfigi_are_classified_conservatively() -> None:
    rows = {row["source_id"]: row for row in build_point_in_time_policy()["rows"]}
    sec = rows["sec_companyfacts_manifest"]
    openfigi = rows["openfigi_symbology_manifest"]
    assert sec["requirement_status"] == "REQUIRED"
    assert sec["policy_status"] in {"POLICY_MISSING", "REVIEW_REQUIRED", "FAIL_CLOSED"}
    assert "MISSING_POINT_IN_TIME_POLICY" in sec["block_reasons"]
    assert openfigi["requirement_status"] == "NOT_REQUIRED"
    assert openfigi["policy_status"] == "NOT_REQUIRED"
