"""Unit tests for research.regime_diagnostics (v3.13)."""

from __future__ import annotations

from research.regime_diagnostics import (
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_SUFFICIENT,
    MIN_TRADES_PER_AXIS,
    REGIME_CONCENTRATED_THRESHOLD,
    build_candidate_diagnostics,
    summarize_diagnostics,
)


def _regime_diag_for(
    candidate_id: str,
    *,
    trend: list[tuple[str, int, float]],
    vol: list[tuple[str, int, float]],
) -> dict:
    """Minimal sidecar shape matching research/regime_reporting.py output."""

    def _entries(items):
        return [
            {
                "label": label,
                "coverage_count": trade_count,
                "arithmetic_return_contribution": total_pnl,
                "trade_count": trade_count,
                "trade_metrics": {"total_pnl": total_pnl},
            }
            for label, trade_count, total_pnl in items
        ]

    return {
        "strategies": [
            {
                "strategy_id": candidate_id,
                "regime_breakdown": {
                    "trend": _entries(trend),
                    "volatility": _entries(vol),
                },
            }
        ]
    }


def test_missing_sidecar_yields_insufficient_assessment() -> None:
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "x"},
        regime_diagnostics=None,
    )
    assert diag["regime_assessment_status"] == ASSESSMENT_INSUFFICIENT
    assert diag["regime_dependency_scores"]["trend"] is None
    assert diag["regime_dependency_scores"]["vol"] is None
    assert diag["regime_dependency_scores"]["overall"] is None


def test_insufficient_evidence_when_trade_count_below_threshold() -> None:
    sidecar = _regime_diag_for(
        "cid",
        trend=[("trending", 3, 0.01), ("non_trending", 2, -0.01)],
        vol=[("high_vol", 2, 0.0), ("low_vol", 3, 0.0)],
    )
    assert 3 + 2 < MIN_TRADES_PER_AXIS
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "cid"},
        regime_diagnostics=sidecar,
    )
    assert diag["regime_assessment_status"] == ASSESSMENT_INSUFFICIENT
    assert diag["regime_dependency_scores"]["trend"] is None
    assert diag["regime_dependency_scores"]["vol"] is None


def test_sufficient_evidence_but_single_bucket_trend_marks_axis_insufficient() -> None:
    # 15 trades on trend, all in "trending" — one bucket only → axis
    # insufficient (needs ≥2 non-insufficient buckets carrying trades)
    sidecar = _regime_diag_for(
        "cid",
        trend=[("trending", 15, 1.0), ("non_trending", 0, 0.0)],
        vol=[("high_vol", 7, 0.5), ("low_vol", 8, 0.5)],
    )
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "cid"},
        regime_diagnostics=sidecar,
    )
    # one axis has evidence, so overall candidate is sufficient
    assert diag["regime_assessment_status"] == ASSESSMENT_SUFFICIENT
    assert diag["axis_sufficiency"]["trend"] is False
    assert diag["axis_sufficiency"]["vol"] is True
    assert diag["regime_dependency_scores"]["trend"] is None
    assert diag["regime_dependency_scores"]["vol"] is not None


def test_overall_is_max_of_available_axis_scores() -> None:
    sidecar = _regime_diag_for(
        "cid",
        trend=[("trending", 18, 9.0), ("non_trending", 3, 1.0)],
        vol=[("high_vol", 10, 5.0), ("low_vol", 11, 5.0)],
    )
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "cid"},
        regime_diagnostics=sidecar,
    )
    scores = diag["regime_dependency_scores"]
    available = [s for s in (scores["trend"], scores["vol"], scores["width"]) if s is not None]
    assert scores["overall"] == max(available)


def test_threshold_constant_is_documented_and_in_band() -> None:
    assert 0.5 <= REGIME_CONCENTRATED_THRESHOLD <= 1.0


def test_summarize_diagnostics_aggregates_counts() -> None:
    entries = [
        {"regime_assessment_status": ASSESSMENT_SUFFICIENT},
        {"regime_assessment_status": ASSESSMENT_INSUFFICIENT},
        {"regime_assessment_status": ASSESSMENT_SUFFICIENT},
    ]
    summary = summarize_diagnostics(entries)
    assert summary["candidates_total"] == 3
    assert summary["candidates_with_sufficient_evidence"] == 2
    assert summary["regime_axes"] == ["trend", "vol", "width"]


def test_width_distribution_plumbs_into_regime_tags_summary() -> None:
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "cid"},
        regime_diagnostics=None,
        width_distribution={"expansion": 5, "compression": 3, "insufficient": 2},
    )
    assert diag["regime_tags_summary"]["width"] == {
        "expansion": 5,
        "compression": 3,
        "insufficient": 2,
    }


def test_upstream_unknown_label_collapses_to_insufficient_bucket() -> None:
    sidecar = {
        "strategies": [
            {
                "strategy_id": "cid",
                "regime_breakdown": {
                    "trend": [
                        {
                            "label": "unknown",
                            "coverage_count": 100,
                            "arithmetic_return_contribution": 0.0,
                            "trade_count": 20,
                            "trade_metrics": {"total_pnl": 0.0},
                        }
                    ],
                    "volatility": [
                        {
                            "label": "high_vol",
                            "coverage_count": 20,
                            "arithmetic_return_contribution": 1.0,
                            "trade_count": 10,
                            "trade_metrics": {"total_pnl": 1.0},
                        },
                        {
                            "label": "low_vol",
                            "coverage_count": 20,
                            "arithmetic_return_contribution": 1.0,
                            "trade_count": 10,
                            "trade_metrics": {"total_pnl": 1.0},
                        },
                    ],
                },
            }
        ]
    }
    diag = build_candidate_diagnostics(
        registry_v2_entry={"candidate_id": "cid"},
        regime_diagnostics=sidecar,
    )
    assert diag["regime_dependency_scores"]["trend"] is None
    vol_score = diag["regime_dependency_scores"]["vol"]
    assert vol_score is not None
    assert 0.49 <= vol_score <= 0.51
