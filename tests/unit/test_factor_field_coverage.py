from __future__ import annotations

from research.data_readiness.factor_field_coverage import build_factor_field_coverage


def test_factor_field_coverage_is_fail_closed_and_deterministic() -> None:
    left = build_factor_field_coverage()
    right = build_factor_field_coverage()
    assert left == right
    assert left["summary"]["covered_count"] == 0
    assert left["summary"]["partial_count"] > 0
    assert left["summary"]["unknown_count"] > 0


def test_factor_field_coverage_distinguishes_claimed_and_unclaimed_fields() -> None:
    report = build_factor_field_coverage()
    rows = {row["factor_id"]: row for row in report["rows"]}

    assert rows["roic"]["field_coverage_status"] == "UNKNOWN"
    assert rows["roic"]["coverage_block_reasons"] == ["FACTOR_FIELD_COVERAGE_UNKNOWN"]

    assert rows["earnings_yield"]["field_coverage_status"] == "PARTIAL"
    assert rows["earnings_yield"]["coverage_block_reasons"] == [
        "FACTOR_FIELD_COVERAGE_UNKNOWN",
        "MISSING_REQUIRED_FIELD",
    ]

    assert rows["twelve_month_momentum"]["field_coverage_status"] == "MISSING"
    assert rows["twelve_month_momentum"]["coverage_block_reasons"] == ["MISSING_REQUIRED_FIELD"]

