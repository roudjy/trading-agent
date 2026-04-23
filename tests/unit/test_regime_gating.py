"""Unit tests for research.regime_gating (v3.13)."""

from __future__ import annotations

from research.regime_diagnostics import (
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_SUFFICIENT,
)
from research.regime_gating import (
    GATE_RULES,
    NON_AUTHORITATIVE_NOTE,
    build_candidate_gating_experiments,
    gating_rule_ids,
)


def _candidate_diag(
    *,
    assessment: str,
    trend_buckets: list[dict] | None = None,
    vol_buckets: list[dict] | None = None,
) -> dict:
    return {
        "candidate_id": "cid",
        "regime_assessment_status": assessment,
        "regime_breakdown": {
            "trend": trend_buckets or [],
            "vol": vol_buckets or [],
            "width": [],
        },
    }


def _bucket(label: str, trade_count: int, total_pnl: float) -> dict:
    return {
        "label": label,
        "coverage_count": trade_count,
        "arithmetic_return_contribution": total_pnl,
        "trade_count": trade_count,
        "total_pnl": total_pnl,
    }


def test_fixed_three_rules_in_canonical_order() -> None:
    assert gating_rule_ids() == ["trend_only", "trend_low_vol", "trend_expansion"]
    assert len(GATE_RULES) == 3


def test_insufficient_assessment_emits_all_rules_with_null_metrics() -> None:
    diag = _candidate_diag(assessment=ASSESSMENT_INSUFFICIENT)
    experiments = build_candidate_gating_experiments(candidate_diagnostics=diag)
    assert len(experiments) == len(GATE_RULES)
    for exp in experiments:
        assert exp["status"] == ASSESSMENT_INSUFFICIENT
        assert exp["baseline"] is None
        assert exp["filtered"] is None
        assert exp["delta"] is None
        assert exp["non_authoritative_note"] == NON_AUTHORITATIVE_NOTE


def test_trend_only_rule_filters_to_trending_bucket() -> None:
    diag = _candidate_diag(
        assessment=ASSESSMENT_SUFFICIENT,
        trend_buckets=[_bucket("trending", 30, 3.0), _bucket("non_trending", 10, 1.0)],
        vol_buckets=[_bucket("high_vol", 20, 2.0), _bucket("low_vol", 20, 2.0)],
    )
    experiments = build_candidate_gating_experiments(candidate_diagnostics=diag)
    trend_only = next(e for e in experiments if e["rule_id"] == "trend_only")
    assert trend_only["status"] == "evaluated"
    assert trend_only["baseline"]["trades"] == 40
    assert trend_only["filtered"]["trades"] == 30
    assert trend_only["delta"]["trades"] == -10
    # PnL delta should reflect keeping only the trending bucket
    assert abs(trend_only["delta"]["total_pnl"] - (3.0 - 4.0)) < 1e-9


def test_width_dependent_rule_marks_insufficient_axis_evidence() -> None:
    # v3.13 has no width-level trade attribution. Rules that filter
    # on width must report insufficient_axis_evidence, not fabricate
    # a filtered set.
    diag = _candidate_diag(
        assessment=ASSESSMENT_SUFFICIENT,
        trend_buckets=[_bucket("trending", 30, 3.0), _bucket("non_trending", 10, 1.0)],
        vol_buckets=[_bucket("high_vol", 20, 2.0), _bucket("low_vol", 20, 2.0)],
    )
    experiments = build_candidate_gating_experiments(candidate_diagnostics=diag)
    width_rule = next(e for e in experiments if e["rule_id"] == "trend_expansion")
    assert width_rule["status"] == "insufficient_axis_evidence"
    assert width_rule["delta"] is None


def test_trend_low_vol_uses_conservative_intersection() -> None:
    diag = _candidate_diag(
        assessment=ASSESSMENT_SUFFICIENT,
        trend_buckets=[_bucket("trending", 40, 4.0), _bucket("non_trending", 10, 1.0)],
        vol_buckets=[_bucket("high_vol", 15, 1.5), _bucket("low_vol", 25, 2.5)],
    )
    experiments = build_candidate_gating_experiments(candidate_diagnostics=diag)
    rule = next(e for e in experiments if e["rule_id"] == "trend_low_vol")
    assert rule["status"] == "evaluated"
    # Conservative intersection = min(trend_trades, vol_trades) = 25
    assert rule["filtered"]["trades"] == min(40, 25)


def test_no_winner_picking_api() -> None:
    # There must be no function that returns a "best" rule.
    import research.regime_gating as gating

    public = [name for name in dir(gating) if not name.startswith("_")]
    for name in public:
        assert "best" not in name.lower()
        assert "winner" not in name.lower()


def test_all_rules_are_always_reported_even_on_sufficient_candidate() -> None:
    diag = _candidate_diag(
        assessment=ASSESSMENT_SUFFICIENT,
        trend_buckets=[_bucket("trending", 30, 3.0), _bucket("non_trending", 10, 1.0)],
        vol_buckets=[_bucket("high_vol", 20, 2.0), _bucket("low_vol", 20, 2.0)],
    )
    experiments = build_candidate_gating_experiments(candidate_diagnostics=diag)
    assert {e["rule_id"] for e in experiments} == {r.rule_id for r in GATE_RULES}
