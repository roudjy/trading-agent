from __future__ import annotations

import json
from pathlib import Path

from research.equity_factors import controlled_factor_evaluation as evaluation


def _seed_row(*, feasibility_status: str = "FEASIBLE", blocked_reason_codes: list[str] | None = None) -> dict[str, object]:
    return {
        "hypothesis_seed_id": "equity_factor_seed::test_recipe",
        "source_recipe_id": "test_recipe",
        "target_universe_ids": ["test_universe"],
        "factor_ids": ["roic"],
        "feasibility_status": feasibility_status,
        "blocked_reason_codes": blocked_reason_codes or [],
    }


def _factor_contracts(point_in_time_required: bool = True) -> dict[str, object]:
    return {
        "rows": [
            {
                "factor_id": "roic",
                "required_fields": ["nopat_ttm", "invested_capital"],
                "point_in_time_required": point_in_time_required,
            }
        ]
    }


def _factor_readiness(currency_normalization_required: bool = False) -> dict[str, object]:
    return {
        "factor_rows": [
            {
                "factor_id": "roic",
                "currency_normalization_required": currency_normalization_required,
            }
        ]
    }


def test_controlled_factor_evaluation_blocks_when_seed_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_hypothesis_seeds",
        lambda: {"rows": [_seed_row(feasibility_status="BLOCKED", blocked_reason_codes=["MISSING_SOURCE_MANIFEST"])]},
    )
    monkeypatch.setattr(evaluation, "build_fundamental_readiness", lambda: _factor_readiness())
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_calculation_contracts",
        lambda: _factor_contracts(),
    )

    row = evaluation.build_controlled_factor_evaluation_readiness()["rows"][0]
    assert row["readiness_status"] == "BLOCKED"
    assert "BLOCKED_SOURCE_MANIFEST" in row["blocked_reason_codes"]
    assert row["allowed_next_action"] == "add_source_manifest"


def test_controlled_factor_evaluation_maps_license_policy_blockers(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_hypothesis_seeds",
        lambda: {"rows": [_seed_row(feasibility_status="BLOCKED", blocked_reason_codes=["LICENSE_REVIEW_REQUIRED"])]},
    )
    monkeypatch.setattr(evaluation, "build_fundamental_readiness", lambda: _factor_readiness())
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_calculation_contracts",
        lambda: _factor_contracts(),
    )

    row = evaluation.build_controlled_factor_evaluation_readiness()["rows"][0]
    assert "BLOCKED_SOURCE_LICENSE_POLICY" in row["blocked_reason_codes"]
    assert row["allowed_next_action"] == "operator_review"


def test_controlled_factor_evaluation_not_ready_when_point_in_time_policy_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_hypothesis_seeds",
        lambda: {"rows": [_seed_row()]},
    )
    monkeypatch.setattr(evaluation, "build_fundamental_readiness", lambda: _factor_readiness())
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_calculation_contracts",
        lambda: _factor_contracts(point_in_time_required=True),
    )

    row = evaluation.build_controlled_factor_evaluation_readiness()["rows"][0]
    assert row["readiness_status"] == "NOT_READY"
    assert "BLOCKED_POINT_IN_TIME_POLICY" in row["blocked_reason_codes"]
    assert "BLOCKED_OOS_POLICY" in row["blocked_reason_codes"]


def test_controlled_factor_evaluation_not_ready_when_cost_and_null_models_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_hypothesis_seeds",
        lambda: {"rows": [_seed_row()]},
    )
    monkeypatch.setattr(evaluation, "build_fundamental_readiness", lambda: _factor_readiness())
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_calculation_contracts",
        lambda: _factor_contracts(point_in_time_required=False),
    )

    row = evaluation.build_controlled_factor_evaluation_readiness()["rows"][0]
    assert row["readiness_status"] == "NOT_READY"
    assert "BLOCKED_COST_MODEL" in row["blocked_reason_codes"]
    assert "BLOCKED_NULL_MODEL" in row["blocked_reason_codes"]


def test_controlled_factor_evaluation_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_hypothesis_seeds",
        lambda: {"rows": [_seed_row()]},
    )
    monkeypatch.setattr(evaluation, "build_fundamental_readiness", lambda: _factor_readiness())
    monkeypatch.setattr(
        evaluation,
        "build_equity_factor_calculation_contracts",
        lambda: _factor_contracts(point_in_time_required=False),
    )

    first = evaluation.build_controlled_factor_evaluation_readiness()
    second = evaluation.build_controlled_factor_evaluation_readiness()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_controlled_factor_evaluation_source_has_no_performance_claims() -> None:
    source = Path(evaluation.__file__).read_text(encoding="utf-8").lower()
    assert "performance claim" not in source
    assert "alpha certainty" not in source
    assert "buy_list" in source
