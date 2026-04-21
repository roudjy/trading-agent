"""Cost-sensitivity harness tests (v3.8 step 3).

Pure-module tests: events and bar streams are constructed in-test, no
engine is invoked. Exercises the determinism, monotonicity, and
non-mutation invariants that Step 3 pins.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agent.backtesting.cost_sensitivity import (
    COST_SENSITIVITY_VERSION,
    DEFAULT_SCENARIOS,
    ScenarioSpec,
    build_cost_sensitivity_report,
    derive_fill_positions,
    run_cost_sensitivity,
)
from agent.backtesting.execution import ExecutionEvent


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _ts(day: int) -> str:
    # ISO-8601 UTC timestamp, deterministic
    return f"2024-01-{day:02d}T00:00:00+00:00"


def _full_fill(
    *,
    asset: str,
    side: str,
    day: int,
    sequence: int,
    fold_index: int | None = None,
    fill_price: float = 100.0,
    requested_size: float = 1.0,
    fee_amount: float = 0.0035,
    slippage_bps: float = 0.0,
) -> ExecutionEvent:
    return ExecutionEvent.full_fill(
        asset=asset,
        side=side,  # type: ignore[arg-type]
        timestamp_utc=_ts(day),
        sequence=sequence,
        fold_index=fold_index,
        intended_price=fill_price,
        requested_size=requested_size,
        fill_price=fill_price,
        filled_size=requested_size,
        fee_amount=fee_amount,
        slippage_bps=slippage_bps,
    )


def _accepted(
    *,
    asset: str,
    side: str,
    day: int,
    sequence: int,
    fold_index: int | None = None,
    fill_price: float = 100.0,
    requested_size: float = 1.0,
) -> ExecutionEvent:
    return ExecutionEvent.accepted(
        asset=asset,
        side=side,  # type: ignore[arg-type]
        timestamp_utc=_ts(day),
        sequence=sequence,
        fold_index=fold_index,
        intended_price=fill_price,
        requested_size=requested_size,
    )


def _bar_stream(
    *, asset: str, fold_index: int, days: list[int]
) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_utc": _ts(d),
            "asset": asset,
            "fold_index": fold_index,
            "return": 0.0,
            "trend_regime": "unknown",
            "volatility_regime": "unknown",
            "combined_regime": "unknown",
        }
        for d in days
    ]


def _simple_round_trip_events(
    *, asset: str = "BTC", entry_day: int = 3, exit_day: int = 7
) -> list[ExecutionEvent]:
    # One round trip: accepted+full_fill at entry, accepted+full_fill at exit
    return [
        _accepted(asset=asset, side="long", day=entry_day, sequence=0),
        _full_fill(asset=asset, side="long", day=entry_day, sequence=1),
        _accepted(asset=asset, side="long", day=exit_day, sequence=2),
        _full_fill(asset=asset, side="long", day=exit_day, sequence=3),
    ]


def _simple_dag_returns(n_bars: int = 10) -> list[float]:
    # Gentle uptrend with one small drawdown bar
    base = [0.001] * n_bars
    if n_bars >= 5:
        base[4] = -0.002
    return base


# ---------------------------------------------------------------------------
# 1. Vocabulary / version / defaults
# ---------------------------------------------------------------------------


def test_version_is_pinned_string():
    assert COST_SENSITIVITY_VERSION == "1.0"


def test_default_scenarios_are_pinned_tuple():
    names = tuple(s.name for s in DEFAULT_SCENARIOS)
    assert names == (
        "baseline",
        "fee_x2",
        "fee_x3",
        "slippage_5bps",
        "slippage_10bps",
    )
    baseline = DEFAULT_SCENARIOS[0]
    assert baseline.fee_multiplier == 1.0
    assert baseline.slippage_bps == 0.0


def test_scenario_spec_rejects_negative_fee_multiplier():
    with pytest.raises(ValueError):
        ScenarioSpec(name="bad", fee_multiplier=-1.0, slippage_bps=0.0)


def test_scenario_spec_rejects_negative_slippage_bps():
    with pytest.raises(ValueError):
        ScenarioSpec(name="bad", fee_multiplier=1.0, slippage_bps=-5.0)


def test_scenario_spec_rejects_non_finite_values():
    with pytest.raises(ValueError):
        ScenarioSpec(
            name="bad", fee_multiplier=float("inf"), slippage_bps=0.0
        )
    with pytest.raises(ValueError):
        ScenarioSpec(
            name="bad", fee_multiplier=1.0, slippage_bps=float("nan")
        )


def test_scenario_spec_rejects_empty_name():
    with pytest.raises(ValueError):
        ScenarioSpec(name="", fee_multiplier=1.0, slippage_bps=0.0)


# ---------------------------------------------------------------------------
# 2. Baseline scenario reproduces baseline metrics exactly
# ---------------------------------------------------------------------------


def test_baseline_scenario_matches_original_metrics_bytewise():
    events = _simple_round_trip_events(entry_day=3, exit_day=7)
    dag = _simple_dag_returns(10)
    # fill_positions: entry fill at equity position 3, exit fill at
    # equity position 7 (1-indexed in the curve).
    fill_positions = [3, 7]
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=fill_positions,
        kosten_per_kant=0.0035,
    )
    baseline = next(
        s for s in report["scenarios"] if s["name"] == "baseline"
    )
    # The baseline scenario equity curve must equal the engine's
    # cumprod-of-returns curve (because per_fill_adjustment == 1.0 when
    # m=1.0, s=0.0).
    expected_equity = 1.0
    for r in dag:
        expected_equity *= 1.0 + r
    assert baseline["metrics"]["final_equity"] == pytest.approx(
        expected_equity, rel=1e-12
    )
    assert baseline["metrics"]["total_return"] == pytest.approx(
        expected_equity - 1.0, rel=1e-12
    )


# ---------------------------------------------------------------------------
# 3. Monotonicity: more fees / more slippage -> strictly worse PnL
# ---------------------------------------------------------------------------


def test_increasing_fees_strictly_reduces_pnl():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
        scenarios=(
            ScenarioSpec(name="fee_x1", fee_multiplier=1.0),
            ScenarioSpec(name="fee_x2", fee_multiplier=2.0),
            ScenarioSpec(name="fee_x3", fee_multiplier=3.0),
        ),
    )
    ret_1 = report["scenarios"][0]["metrics"]["total_return"]
    ret_2 = report["scenarios"][1]["metrics"]["total_return"]
    ret_3 = report["scenarios"][2]["metrics"]["total_return"]
    assert ret_1 > ret_2 > ret_3


def test_increasing_slippage_strictly_reduces_pnl():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
        scenarios=(
            ScenarioSpec(name="s0", slippage_bps=0.0),
            ScenarioSpec(name="s5", slippage_bps=5.0),
            ScenarioSpec(name="s10", slippage_bps=10.0),
        ),
    )
    r0 = report["scenarios"][0]["metrics"]["total_return"]
    r5 = report["scenarios"][1]["metrics"]["total_return"]
    r10 = report["scenarios"][2]["metrics"]["total_return"]
    assert r0 > r5 > r10


# ---------------------------------------------------------------------------
# 4. Zero-event / no-trade case
# ---------------------------------------------------------------------------


def test_zero_event_run_produces_baseline_only_metrics():
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=(),
        baseline_dag_returns=dag,
        fill_positions=(),
        kosten_per_kant=0.0035,
    )
    assert report["n_events"] == 0
    assert report["n_full_fills"] == 0
    # With no fills, every scenario collapses to the baseline curve.
    finals = [
        s["metrics"]["final_equity"] for s in report["scenarios"]
    ]
    assert all(
        f == pytest.approx(finals[0], rel=1e-12) for f in finals
    )


# ---------------------------------------------------------------------------
# 5. Determinism across repeated runs
# ---------------------------------------------------------------------------


def test_run_cost_sensitivity_is_deterministic_across_calls():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    r1 = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    r2 = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    assert r1 == r2


# ---------------------------------------------------------------------------
# 6. Multi-asset aggregation (caller supplies merged stream)
# ---------------------------------------------------------------------------


def test_multi_asset_runs_aggregate_as_merged_event_stream():
    # The harness is asset-agnostic: the caller supplies a merged
    # events+positions stream. Verify no asset-specific branching
    # affects the math.
    events_btc = _simple_round_trip_events(
        asset="BTC", entry_day=3, exit_day=7
    )
    events_eth = _simple_round_trip_events(
        asset="ETH", entry_day=4, exit_day=8
    )
    # Merge and resequence manually (caller's responsibility)
    merged = events_btc + events_eth
    merged_positions = [3, 7, 4, 8]
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=merged,
        baseline_dag_returns=dag,
        fill_positions=sorted(merged_positions),
        kosten_per_kant=0.0035,
    )
    assert report["n_full_fills"] == 4
    # fee_x2 must be strictly worse than baseline under 4 fills
    baseline = report["scenarios"][0]["metrics"]["total_return"]
    fee_x2 = report["scenarios"][1]["metrics"]["total_return"]
    assert baseline > fee_x2


# ---------------------------------------------------------------------------
# 7. Fold-based fill tagging is carried through harness output
# ---------------------------------------------------------------------------


def test_fold_based_events_do_not_break_aggregation():
    events: list[ExecutionEvent] = []
    seq = 0
    for fold in (0, 1):
        events.append(
            _accepted(
                asset="BTC",
                side="long",
                day=3 + fold * 4,
                sequence=seq,
                fold_index=fold,
            )
        )
        seq += 1
        events.append(
            _full_fill(
                asset="BTC",
                side="long",
                day=3 + fold * 4,
                sequence=seq,
                fold_index=fold,
            )
        )
        seq += 1
        events.append(
            _accepted(
                asset="BTC",
                side="long",
                day=5 + fold * 4,
                sequence=seq,
                fold_index=fold,
            )
        )
        seq += 1
        events.append(
            _full_fill(
                asset="BTC",
                side="long",
                day=5 + fold * 4,
                sequence=seq,
                fold_index=fold,
            )
        )
        seq += 1
    dag = _simple_dag_returns(12)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 5, 7, 9],
        kosten_per_kant=0.0035,
    )
    assert report["n_full_fills"] == 4
    # baseline > fee_x2 under 4 fills
    assert (
        report["scenarios"][0]["metrics"]["total_return"]
        > report["scenarios"][1]["metrics"]["total_return"]
    )


# ---------------------------------------------------------------------------
# 8. No mutation of original execution events
# ---------------------------------------------------------------------------


def test_events_are_not_mutated_by_harness():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    before_snapshot = [copy.deepcopy(e) for e in events]
    run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    for before, after in zip(before_snapshot, events):
        assert before == after


# ---------------------------------------------------------------------------
# 9. No mutation of baseline dag_returns
# ---------------------------------------------------------------------------


def test_baseline_dag_returns_are_not_mutated():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    dag_copy = list(dag)
    run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    assert dag == dag_copy


# ---------------------------------------------------------------------------
# 10. Output structure is stable and complete
# ---------------------------------------------------------------------------


def test_output_structure_is_stable_and_complete():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    # Top-level keys
    assert set(report.keys()) == {
        "version",
        "kosten_per_kant",
        "n_events",
        "n_full_fills",
        "scenarios",
    }
    assert report["version"] == "1.0"
    assert report["n_events"] == 4
    assert report["n_full_fills"] == 2
    # Scenario-level keys
    for s in report["scenarios"]:
        assert set(s.keys()) == {
            "name",
            "fee_multiplier",
            "slippage_bps",
            "metrics",
        }
        assert set(s["metrics"].keys()) == {
            "final_equity",
            "total_return",
            "max_drawdown",
            "sharpe_proxy",
            "n_full_fills",
            "total_fee_drag_fraction",
            "total_slippage_drag_fraction",
        }


# ---------------------------------------------------------------------------
# 11. Validation: rejects misaligned fill_positions length
# ---------------------------------------------------------------------------


def test_rejects_misaligned_fill_positions_length():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[3],  # only 1 position for 2 full_fills
            kosten_per_kant=0.0035,
        )


def test_rejects_non_monotone_fill_positions():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[7, 3],  # descending
            kosten_per_kant=0.0035,
        )


def test_rejects_fill_position_past_curve_end():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[3, 99],
            kosten_per_kant=0.0035,
        )


def test_rejects_kosten_out_of_range():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[3, 7],
            kosten_per_kant=1.0,
        )
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[3, 7],
            kosten_per_kant=-0.1,
        )


def test_rejects_empty_scenarios():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    with pytest.raises(ValueError):
        run_cost_sensitivity(
            events=events,
            baseline_dag_returns=dag,
            fill_positions=[3, 7],
            kosten_per_kant=0.0035,
            scenarios=(),
        )


# ---------------------------------------------------------------------------
# 12. derive_fill_positions helper
# ---------------------------------------------------------------------------


def test_derive_fill_positions_matches_timestamps():
    events = _simple_round_trip_events(entry_day=3, exit_day=7)
    full_fills = [e for e in events if e.kind == "full_fill"]
    bar_stream = _bar_stream(
        asset="BTC", fold_index=0, days=list(range(2, 12))
    )
    positions = derive_fill_positions(full_fills, bar_stream)
    # day=3 -> bar_stream position 1 -> equity position 2
    # day=7 -> bar_stream position 5 -> equity position 6
    assert positions == [2, 6]


def test_derive_fill_positions_rejects_unknown_timestamp():
    # Use a valid but out-of-stream timestamp (day 29 is valid for Jan).
    full_fills = [
        _full_fill(asset="BTC", side="long", day=29, sequence=1)
    ]
    bar_stream = _bar_stream(
        asset="BTC", fold_index=0, days=[1, 2, 3]
    )
    with pytest.raises(KeyError):
        derive_fill_positions(full_fills, bar_stream)


def test_derive_fill_positions_rejects_non_full_fill_event():
    accepted = _accepted(asset="BTC", side="long", day=3, sequence=0)
    bar_stream = _bar_stream(
        asset="BTC", fold_index=0, days=[3]
    )
    with pytest.raises(ValueError):
        derive_fill_positions([accepted], bar_stream)


# ---------------------------------------------------------------------------
# 13. build_cost_sensitivity_report convenience wrapper
# ---------------------------------------------------------------------------


def test_build_cost_sensitivity_report_end_to_end():
    events = _simple_round_trip_events(entry_day=3, exit_day=7)
    # bar_stream covers days 2..11, so equity positions are 1..10
    bar_stream = _bar_stream(
        asset="BTC", fold_index=0, days=list(range(2, 12))
    )
    # baseline_dag_returns must have the same length as bar_stream
    dag = _simple_dag_returns(len(bar_stream))
    report = build_cost_sensitivity_report(
        events=events,
        bar_return_stream=bar_stream,
        baseline_dag_returns=dag,
        kosten_per_kant=0.0035,
    )
    assert report["n_full_fills"] == 2
    # fee_x2 must be worse than baseline
    baseline = report["scenarios"][0]["metrics"]["total_return"]
    fee_x2 = report["scenarios"][1]["metrics"]["total_return"]
    assert baseline > fee_x2


# ---------------------------------------------------------------------------
# 14. Baseline fee-drag consistency: report matches raw engine equity
# ---------------------------------------------------------------------------


def test_baseline_final_equity_equals_cumprod_of_dag_returns():
    """The baseline scenario must not inject any multiplicative drift.

    This pins that the harness's baseline scenario reproduces
    cumprod(1 + baseline_dag_returns) exactly, so a downstream consumer
    can trust that "baseline" in the report means "engine's actual
    equity".
    """
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    expected = 1.0
    for r in dag:
        expected *= 1.0 + r
    baseline = report["scenarios"][0]["metrics"]["final_equity"]
    assert baseline == pytest.approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------
# 15. All scenarios: correct fill count surfaced
# ---------------------------------------------------------------------------


def test_n_full_fills_surfaces_on_every_scenario():
    events = _simple_round_trip_events()
    dag = _simple_dag_returns(10)
    report = run_cost_sensitivity(
        events=events,
        baseline_dag_returns=dag,
        fill_positions=[3, 7],
        kosten_per_kant=0.0035,
    )
    for s in report["scenarios"]:
        assert s["metrics"]["n_full_fills"] == 2


# ---------------------------------------------------------------------------
# 16. Accepted-only events contribute nothing to cost math
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 17. Engine hook: BacktestEngine.build_cost_sensitivity
# ---------------------------------------------------------------------------


def test_engine_hook_returns_none_when_no_oos_data():
    from agent.backtesting.engine import BacktestEngine
    eng = BacktestEngine.__new__(BacktestEngine)
    eng.kosten_per_kant = 0.0035
    eng._last_window_streams = {}
    assert eng.build_cost_sensitivity() is None


def test_engine_hook_groups_by_asset_fold_and_reports():
    from agent.backtesting.engine import BacktestEngine
    eng = BacktestEngine.__new__(BacktestEngine)
    eng.kosten_per_kant = 0.0035
    bar_stream = _bar_stream(
        asset="BTC", fold_index=0, days=list(range(2, 12))
    )
    events = _simple_round_trip_events(entry_day=3, exit_day=7)
    # Stamp fold_index onto events to match the bar_stream group
    stamped = [
        ExecutionEvent.accepted(
            asset=e.asset,
            side=e.side,
            timestamp_utc=e.timestamp_utc,
            sequence=e.sequence,
            fold_index=0,
            intended_price=e.intended_price,
            requested_size=e.requested_size,
        )
        if e.kind == "accepted"
        else ExecutionEvent.full_fill(
            asset=e.asset,
            side=e.side,
            timestamp_utc=e.timestamp_utc,
            sequence=e.sequence,
            fold_index=0,
            intended_price=e.intended_price,
            requested_size=e.requested_size,
            fill_price=e.fill_price,
            filled_size=e.filled_size,
            fee_amount=e.fee_amount,
            slippage_bps=e.slippage_bps,
        )
        for e in events
    ]
    # Attach a small bar-return variation so fills produce deltas
    for j, entry in enumerate(bar_stream):
        entry["return"] = 0.001 if j != 4 else -0.002
    eng._last_window_streams = {
        "oos_execution_events": stamped,
        "oos_bar_returns": bar_stream,
    }
    report = eng.build_cost_sensitivity()
    assert report is not None
    assert report["version"] == "1.0"
    assert len(report["per_window"]) == 1
    window = report["per_window"][0]
    assert window["asset"] == "BTC"
    assert window["fold_index"] == 0
    assert window["n_full_fills"] == 2


def test_accepted_events_do_not_affect_scenario_metrics():
    # One accepted-only event (no fill) should produce identical
    # metrics to the zero-event case.
    accepted_only = [
        _accepted(asset="BTC", side="long", day=3, sequence=0),
    ]
    dag = _simple_dag_returns(10)
    report_accepted = run_cost_sensitivity(
        events=accepted_only,
        baseline_dag_returns=dag,
        fill_positions=(),
        kosten_per_kant=0.0035,
    )
    report_empty = run_cost_sensitivity(
        events=(),
        baseline_dag_returns=dag,
        fill_positions=(),
        kosten_per_kant=0.0035,
    )
    for a, b in zip(
        report_accepted["scenarios"], report_empty["scenarios"]
    ):
        assert a["metrics"]["final_equity"] == pytest.approx(
            b["metrics"]["final_equity"], rel=1e-12
        )
