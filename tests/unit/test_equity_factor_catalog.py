from __future__ import annotations

from research.equity_factors import factor_catalog


def test_factor_catalog_has_unique_ids_and_closed_policy_vocab() -> None:
    report = factor_catalog.build_equity_factor_catalog()
    ids = [row["factor_id"] for row in report["rows"]]
    assert len(ids) == len(set(ids))
    for row in report["rows"]:
        assert row["allowed_use"] == [
            "hypothesis_seed",
            "research_screening",
            "operator_explanation",
        ]
        assert row["forbidden_use"] == [
            "direct_trade_signal",
            "candidate_promotion",
            "capital_allocation",
        ]


def test_factor_contracts_have_required_fields_and_are_deterministic() -> None:
    left = factor_catalog.build_equity_factor_calculation_contracts()
    right = factor_catalog.build_equity_factor_calculation_contracts()
    assert left == right
    assert left["summary"]["contract_count"] >= 20
    assert all(row["required_fields"] for row in left["rows"])
