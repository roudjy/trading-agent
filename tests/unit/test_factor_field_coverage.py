from __future__ import annotations

from research.data_readiness.factor_field_coverage import build_factor_field_coverage


def test_factor_field_coverage_is_fail_closed_and_deterministic() -> None:
    left = build_factor_field_coverage()
    right = build_factor_field_coverage()
    assert left == right
    assert left["summary"]["covered_count"] == 0
    assert left["summary"]["approved_provider_count"] == 0
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


def test_factor_field_coverage_exposes_provider_matrix_without_authority() -> None:
    report = build_factor_field_coverage()
    rows = {row["factor_id"]: row for row in report["rows"]}
    earnings_yield = rows["earnings_yield"]
    market_cap = next(
        field for field in earnings_yield["field_coverage"] if field["field_name"] == "market_cap"
    )
    net_income = next(
        field for field in earnings_yield["field_coverage"] if field["field_name"] == "net_income_ttm"
    )

    assert market_cap["coverage_status"] == "MISSING"
    assert net_income["coverage_status"] == "UNKNOWN"
    assert {row["provider_id"] for row in net_income["provider_field_matrix"]} >= {
        "alpha_vantage_candidate",
        "eodhd_candidate",
        "financial_modeling_prep_candidate",
        "sec_companyfacts",
    }
    assert all(row["provider_alpha_authority"] is False for row in net_income["provider_field_matrix"])
    assert all(row["provider_factor_authority"] is False for row in net_income["provider_field_matrix"])

