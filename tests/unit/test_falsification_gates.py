"""Unit tests for research.falsification gate functions.

Each gate is a pure post-hoc heuristic or statistical check; these
tests exercise pass / fail paths with known inputs and pin the typed
gate_kind / severity vocabulary.

D3: the fee/slippage gate is a *heuristic*, not true cost-perturbation
sensitivity. This test file pins `gate_kind == "heuristic"` so any
drift toward presenting the heuristic as true sensitivity fails CI.

D4: these verdicts carry diagnostic evidence only — the promotion
layer remains the sole decision authority. The public contract
regression pins the boundary (no `status` field on the sidecar).
"""

from __future__ import annotations

from dataclasses import asdict

from research.falsification import (
    FalsificationVerdict,
    GATE_KIND_HEURISTIC,
    GATE_KIND_STATISTICAL,
    GATE_KIND_STRUCTURAL,
    SEVERITY_BLOCK,
    SEVERITY_INFO,
    SEVERITY_WARN,
    check_corrected_significance,
    check_fee_drag_ratio,
    check_low_trade_count,
    check_oos_collapse,
    check_single_asset_edge_concentration,
    check_single_param_point_edge_concentration,
)


def test_low_trade_count_passes_at_threshold():
    verdict = check_low_trade_count({"totaal_trades": 30}, threshold=30)

    assert verdict.passed is True
    assert verdict.gate_kind == GATE_KIND_STATISTICAL
    assert verdict.severity == SEVERITY_INFO


def test_low_trade_count_warns_below_threshold():
    verdict = check_low_trade_count({"totaal_trades": 5}, threshold=30)

    assert verdict.passed is False
    assert verdict.severity == SEVERITY_WARN
    assert verdict.evidence["totaal_trades"] == 5


def test_single_asset_edge_concentration_passes_with_diverse_assets():
    metrics = {
        "BTC/EUR": {"gross_pnl": 100.0},
        "ETH/EUR": {"gross_pnl": 80.0},
        "SOL/EUR": {"gross_pnl": 60.0},
    }

    verdict = check_single_asset_edge_concentration(metrics, contribution_threshold=0.8)

    assert verdict.passed is True
    assert verdict.gate_kind == GATE_KIND_STRUCTURAL
    assert verdict.evidence["top_asset"] == "BTC/EUR"


def test_single_asset_edge_concentration_warns_when_one_asset_dominates():
    metrics = {
        "BTC/EUR": {"gross_pnl": 900.0},
        "ETH/EUR": {"gross_pnl": 50.0},
        "SOL/EUR": {"gross_pnl": 50.0},
    }

    verdict = check_single_asset_edge_concentration(metrics, contribution_threshold=0.7)

    assert verdict.passed is False
    assert verdict.severity == SEVERITY_WARN


def test_single_asset_edge_concentration_passes_for_single_asset_universe():
    """With only one asset, the 'concentration' notion is degenerate."""
    metrics = {"BTC/EUR": {"gross_pnl": 500.0}}

    verdict = check_single_asset_edge_concentration(metrics, contribution_threshold=0.5)

    assert verdict.passed is True


def test_single_param_point_edge_concentration_passes_when_edge_spread():
    metrics = {
        "point_a": {"gross_pnl": 100.0},
        "point_b": {"gross_pnl": 90.0},
        "point_c": {"gross_pnl": 80.0},
    }

    verdict = check_single_param_point_edge_concentration(metrics)

    assert verdict.passed is True


def test_single_param_point_edge_concentration_warns_when_edge_collapses_to_one_point():
    metrics = {
        "point_a": {"gross_pnl": 1000.0},
        "point_b": {"gross_pnl": 10.0},
        "point_c": {"gross_pnl": 10.0},
    }

    verdict = check_single_param_point_edge_concentration(metrics, contribution_threshold=0.5)

    assert verdict.passed is False
    assert verdict.severity == SEVERITY_WARN


def test_single_param_point_edge_concentration_handles_empty_input():
    verdict = check_single_param_point_edge_concentration({})

    assert verdict.passed is True
    assert verdict.evidence["per_param_share"] == {}


def test_oos_collapse_passes_when_oos_sharpe_holds_up():
    verdict = check_oos_collapse({"sharpe": 1.0}, {"sharpe": 0.8})

    assert verdict.passed is True
    assert verdict.gate_kind == GATE_KIND_STATISTICAL


def test_oos_collapse_blocks_when_oos_sharpe_halves():
    verdict = check_oos_collapse({"sharpe": 1.0}, {"sharpe": 0.2}, sharpe_drop_ratio=0.5)

    assert verdict.passed is False
    assert verdict.severity == SEVERITY_BLOCK


def test_oos_collapse_passes_trivially_when_is_sharpe_is_non_positive():
    verdict = check_oos_collapse({"sharpe": -0.5}, {"sharpe": -1.0})

    assert verdict.passed is True
    assert verdict.evidence["applicable"] is False


def test_fee_drag_ratio_gate_kind_is_heuristic_not_sensitivity():
    """D3 pin: this gate is explicitly a heuristic, not true sensitivity."""
    verdict = check_fee_drag_ratio(
        {"totaal_trades": 10, "gross_return": 1.0},
        cost_per_side=0.001,
    )

    assert verdict.gate_kind == GATE_KIND_HEURISTIC
    assert "heuristic" in verdict.evidence["note"].lower()


def test_fee_drag_ratio_passes_when_drag_is_small_fraction_of_edge():
    verdict = check_fee_drag_ratio(
        {"totaal_trades": 10, "gross_return": 1.0},
        cost_per_side=0.001,
        threshold=0.5,
    )

    assert verdict.passed is True


def test_fee_drag_ratio_warns_when_drag_dominates_gross_return():
    verdict = check_fee_drag_ratio(
        {"totaal_trades": 1000, "gross_return": 0.05},
        cost_per_side=0.001,
        threshold=0.5,
    )

    assert verdict.passed is False
    assert verdict.severity == SEVERITY_WARN


def test_corrected_significance_passes_when_psr_and_dsr_above_thresholds():
    verdict = check_corrected_significance(
        {"psr": 0.95, "dsr_canonical": 0.3},
        min_dsr_canonical=0.0,
        min_psr=0.9,
    )

    assert verdict.passed is True


def test_corrected_significance_warns_on_missing_payload():
    verdict = check_corrected_significance(None)

    assert verdict.passed is False
    assert verdict.evidence["reason"] == "defensibility_payload_missing"


def test_corrected_significance_warns_on_individual_missing_fields():
    verdict = check_corrected_significance({"psr": 0.95})

    assert verdict.passed is False
    assert "dsr_missing" in verdict.evidence["failures"]


def test_corrected_significance_warns_when_values_below_thresholds():
    verdict = check_corrected_significance(
        {"psr": 0.5, "dsr_canonical": -0.5},
        min_dsr_canonical=0.0,
        min_psr=0.9,
    )

    assert verdict.passed is False
    failures = verdict.evidence["failures"]
    assert "psr_below_threshold" in failures
    assert "dsr_below_threshold" in failures


def test_falsification_verdict_carries_no_status_field():
    """D4 pin: verdicts are diagnostic evidence, not a competing status.

    If a `status` field is ever added to FalsificationVerdict, the
    boundary with promotion is broken. This test catches that.
    """
    verdict = check_low_trade_count({"totaal_trades": 10}, threshold=30)

    payload = asdict(verdict)
    assert "status" not in payload
    assert set(payload.keys()) == {"gate", "gate_kind", "passed", "severity", "evidence"}


def test_falsification_verdict_is_frozen():
    verdict = FalsificationVerdict(
        gate="x", gate_kind=GATE_KIND_HEURISTIC, passed=True, severity=SEVERITY_INFO
    )

    import pytest

    with pytest.raises(Exception):
        verdict.gate = "y"  # type: ignore[misc]
