from __future__ import annotations

from research.data_readiness.factor_field_coverage import build_factor_field_coverage


def test_factor_field_coverage_is_fail_closed_and_deterministic() -> None:
    left = build_factor_field_coverage()
    right = build_factor_field_coverage()
    assert left == right
    assert left["summary"]["missing_count"] >= 20
    assert all(row["field_coverage_status"] == "MISSING" for row in left["rows"])

