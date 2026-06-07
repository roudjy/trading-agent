from __future__ import annotations

from research.data_readiness.fundamental_readiness import build_fundamental_readiness


def test_missing_source_manifest_and_required_fields_block_readiness() -> None:
    report = build_fundamental_readiness()
    assert report["summary"]["ready_count"] == 0
    assert report["summary"]["not_ready_count"] == report["summary"]["factor_rows"] + report["summary"]["recipe_rows"]
    first_factor = report["factor_rows"][0]
    assert "LICENSE_REVIEW_REQUIRED" in first_factor["readiness_block_reasons"]
    assert first_factor["source_manifest_present"] is True


def test_point_in_time_and_report_lag_requirements_fail_closed() -> None:
    report = build_fundamental_readiness()
    point_in_time_rows = [row for row in report["factor_rows"] if row["point_in_time_required"]]
    assert point_in_time_rows
    for row in point_in_time_rows:
        assert "MISSING_POINT_IN_TIME_POLICY" in row["readiness_block_reasons"]
        assert "MISSING_REPORT_LAG_POLICY" in row["readiness_block_reasons"]
        assert "REPORT_LAG_UNKNOWN" in row["readiness_block_reasons"]
        assert "MISSING_RESTATEMENT_POLICY" in row["readiness_block_reasons"]
        assert "RESTATEMENT_POLICY_UNKNOWN" in row["readiness_block_reasons"]


def test_field_coverage_blockers_are_more_specific() -> None:
    report = build_fundamental_readiness()
    rows = {row["factor_id"]: row for row in report["factor_rows"]}
    assert "FACTOR_FIELD_COVERAGE_UNKNOWN" in rows["roic"]["readiness_block_reasons"]
    assert "MISSING_REQUIRED_FIELD" not in rows["roic"]["readiness_block_reasons"]
    assert "MISSING_REQUIRED_FIELD" in rows["earnings_yield"]["readiness_block_reasons"]

