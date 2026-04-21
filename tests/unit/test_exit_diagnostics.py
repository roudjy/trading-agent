"""Unit tests for exit-quality diagnostics (v3.8 step 4).

The module under test is a pure evaluation layer. These tests
exercise:
- trade-level MFE / MAE / capture-ratio / winner-giveback / exit-lag
  on long and short synthetic paths with known analytic answers;
- aggregate summary + turnover-adjusted exit quality;
- None-case handling (zero MFE, losing trade);
- determinism across repeated calls;
- non-mutation of caller-owned inputs;
- structure stability of the report dict;
- the opt-in ``BacktestEngine.build_exit_diagnostics`` hook;
- interoperability with the cost-sensitivity harness (no shared
  state; both are side-channels on the same streams).
"""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from agent.backtesting.exit_diagnostics import (
    EXIT_DIAGNOSTICS_VERSION,
    TradeDiagnostic,
    build_exit_diagnostics_report,
    compute_trade_diagnostic,
    extract_interior_bar_returns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ASSET = "BTC"
FOLD = 0
K = 0.01  # kosten_per_kant used in test math


def _ts(day: int) -> str:
    # Bar timestamps encoded as ISO strings. Day is the only axis
    # that matters for alignment in these tests.
    return f"2024-01-{day:02d}T00:00:00+00:00"


def _bars(
    *,
    asset: str,
    fold_index: int,
    entries: list[tuple[int, float]],
) -> list[dict[str, Any]]:
    """Build a synthetic bar-return stream.

    ``entries`` is a list of ``(day, side_adjusted_return)`` tuples.
    """
    out: list[dict[str, Any]] = []
    for day, ret in entries:
        out.append(
            {
                "timestamp_utc": _ts(day),
                "asset": asset,
                "fold_index": fold_index,
                "return": float(ret),
            }
        )
    return out


def _trade(
    *,
    side: str,
    entry_day: int,
    exit_day: int,
    pnl: float,
    asset: str = ASSET,
    fold_index: int = FOLD,
) -> dict[str, Any]:
    return {
        "asset": asset,
        "fold_index": fold_index,
        "side": side,
        "entry_timestamp_utc": _ts(entry_day),
        "exit_timestamp_utc": _ts(exit_day),
        "pnl": float(pnl),
    }


# ---------------------------------------------------------------------------
# 1. Vocabulary pin
# ---------------------------------------------------------------------------


def test_exit_diagnostics_version_is_pinned_string():
    assert EXIT_DIAGNOSTICS_VERSION == "1.0"


# ---------------------------------------------------------------------------
# 2. Long trade: MFE / MAE analytic correctness
# ---------------------------------------------------------------------------


def test_mfe_and_mae_on_simple_long_path():
    # Long trade with interior bars at days 2,3.
    # ratios: T2=1.05, T3=1.02 → cumulative raw: 1.05, 1.071.
    # Exit: realized pnl = 0.04958, k=K → exit anchor = 0.05958 ... no
    # we decide exit-bar anchor = pnl + k. Pick pnl s.t. path[-1] =
    # 0.04958: pnl = 0.03958 for a long trade with close_exit /
    # close_entry = 1.04958.
    interior = [0.05, 0.02]
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.03958,
        kosten_per_kant=K,
        interior_bar_returns=interior,
    )
    assert math.isclose(diag.mfe, 0.071, rel_tol=0, abs_tol=1e-12)
    assert diag.mae == 0.0
    assert math.isclose(
        diag.realized_return, 0.04958, rel_tol=0, abs_tol=1e-12
    )


# ---------------------------------------------------------------------------
# 3. Short trade: MFE / MAE analytic correctness
# ---------------------------------------------------------------------------


def test_mfe_and_mae_on_simple_short_path():
    # Short trade: interior side-adjusted returns 0.05, 0.05263...
    # cumulative close ratio: 0.95, then 0.9.
    # path: [0, 0.05, 0.10, exit]. Choose pnl so exit = 0.08:
    # pnl = 0.07.
    r1 = 0.05
    r2 = (1.0 / 0.95) * 0.9 - 1.0
    # Solve: (1 + r2 * -1) = 0.9/0.95 → r2 = 1 - 0.9/0.95
    r2 = 1.0 - 0.9 / 0.95
    interior = [r1, r2]
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="short",
        realized_pnl=0.07,
        kosten_per_kant=K,
        interior_bar_returns=interior,
    )
    assert math.isclose(diag.mfe, 0.1, rel_tol=0, abs_tol=1e-12)
    assert diag.mae == 0.0
    assert math.isclose(
        diag.realized_return, 0.08, rel_tol=0, abs_tol=1e-12
    )


# ---------------------------------------------------------------------------
# 4. realized_return aligns with trade pnl + kosten_per_kant
# ---------------------------------------------------------------------------


def test_realized_return_equals_pnl_plus_kosten_per_kant():
    for side in ("long", "short"):
        for pnl in (-0.05, 0.0, 0.03):
            diag = compute_trade_diagnostic(
                entry_timestamp_utc=_ts(1),
                exit_timestamp_utc=_ts(3),
                asset=ASSET,
                fold_index=FOLD,
                side=side,
                realized_pnl=pnl,
                kosten_per_kant=K,
                interior_bar_returns=[0.0],
            )
            assert math.isclose(
                diag.realized_return,
                pnl + K,
                rel_tol=0,
                abs_tol=1e-12,
            )


# ---------------------------------------------------------------------------
# 5. capture_ratio on positive MFE is realized / MFE
# ---------------------------------------------------------------------------


def test_capture_ratio_on_positive_mfe():
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.03958,  # exit anchor = 0.04958
        kosten_per_kant=K,
        interior_bar_returns=[0.05, 0.02],
    )
    expected = 0.04958 / 0.071
    assert diag.capture_ratio is not None
    assert math.isclose(
        diag.capture_ratio, expected, rel_tol=0, abs_tol=1e-12
    )


# ---------------------------------------------------------------------------
# 6. capture_ratio is None when MFE == 0
# ---------------------------------------------------------------------------


def test_capture_ratio_none_when_mfe_is_zero():
    # Trade that never went favorable; MFE clamps to 0 and
    # capture_ratio must be None (undefined).
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(3),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=-0.04,  # exit anchor = -0.03
        kosten_per_kant=K,
        interior_bar_returns=[-0.05],
    )
    assert diag.mfe == 0.0
    assert diag.capture_ratio is None


# ---------------------------------------------------------------------------
# 7. winner_giveback on winner
# ---------------------------------------------------------------------------


def test_winner_giveback_on_winner():
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.03958,  # exit anchor = 0.04958
        kosten_per_kant=K,
        interior_bar_returns=[0.05, 0.02],
    )
    assert diag.winner_giveback is not None
    assert math.isclose(
        diag.winner_giveback, 0.071 - 0.04958, abs_tol=1e-12
    )


# ---------------------------------------------------------------------------
# 8. winner_giveback None on losing trade
# ---------------------------------------------------------------------------


def test_winner_giveback_none_on_loser_even_with_positive_mfe():
    # Trade peaked favorably at bar 2 (path=0.05) then turned.
    # Exit anchor = -0.10 → realized_return non-positive →
    # winner_giveback is None despite MFE > 0.
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(3),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=-0.11,  # exit anchor = -0.10
        kosten_per_kant=K,
        interior_bar_returns=[0.05],
    )
    assert diag.mfe == pytest.approx(0.05)
    assert diag.winner_giveback is None
    assert diag.capture_ratio is not None
    assert math.isclose(
        diag.capture_ratio, -0.10 / 0.05, abs_tol=1e-12
    )


# ---------------------------------------------------------------------------
# 9. exit_lag_bars correct on known path
# ---------------------------------------------------------------------------


def test_exit_lag_bars_counts_from_peak():
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.03958,  # exit anchor 0.04958
        kosten_per_kant=K,
        interior_bar_returns=[0.05, 0.02],  # peak at index 2
    )
    # path = [0.0, 0.05, 0.071, 0.04958] → argmax=2, len-1=3
    assert diag.exit_lag_bars == 1
    assert diag.holding_bars == 3


def test_exit_lag_bars_zero_when_peak_at_exit():
    # Monotone-up path; peak is at the exit anchor.
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(4),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.09,  # exit anchor = 0.10, strictly above interior
        kosten_per_kant=K,
        interior_bar_returns=[0.02, 0.03],
    )
    # path = [0.0, 0.02, ~0.0506, 0.10] → argmax = 3 → exit_lag = 0
    assert diag.exit_lag_bars == 0


# ---------------------------------------------------------------------------
# 10. Turnover-adjusted exit quality: deterministic + monotone
# ---------------------------------------------------------------------------


def test_turnover_adjusted_exit_quality_deterministic_and_monotone():
    # Two runs with identical inputs produce identical numbers.
    # Varying only bar_count (while keeping trade_count constant)
    # should increase the adjustment (density drops → (1-d) rises).
    bars_short = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(d, 0.0) for d in range(1, 6)],  # 5 bars
    )
    bars_long = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(d, 0.0) for d in range(1, 21)],  # 20 bars
    )
    # Both streams include our trade's entry/exit timestamps.
    # Use a day pattern that exists in both.
    trades = [
        _trade(
            side="long",
            entry_day=1,
            exit_day=4,
            pnl=0.03958,
        ),
    ]
    # Patch interior returns by overriding the bars between entry/exit
    # Manually construct both streams with days 1..5 or 1..20, and
    # inject the target interior returns at days 2 and 3.
    for stream in (bars_short, bars_long):
        for entry in stream:
            if entry["timestamp_utc"] == _ts(2):
                entry["return"] = 0.05
            elif entry["timestamp_utc"] == _ts(3):
                entry["return"] = 0.02
    rep_short = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars_short,
        kosten_per_kant=K,
    )
    rep_short2 = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars_short,
        kosten_per_kant=K,
    )
    rep_long = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars_long,
        kosten_per_kant=K,
    )
    q_short = rep_short["summary"]["turnover_adjusted_exit_quality"]
    q_short2 = rep_short2["summary"][
        "turnover_adjusted_exit_quality"
    ]
    q_long = rep_long["summary"]["turnover_adjusted_exit_quality"]
    assert q_short == q_short2  # deterministic
    assert q_long > q_short  # denser → smaller adjustment


# ---------------------------------------------------------------------------
# 11. Determinism across repeated report builds
# ---------------------------------------------------------------------------


def test_report_is_deterministic_bytewise():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[
            (1, 0.0),
            (2, 0.05),
            (3, 0.02),
            (4, -0.01),  # exit bar; return is unused by the module
        ],
    )
    trades = [_trade(side="long", entry_day=1, exit_day=4, pnl=0.03958)]
    r1 = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    r2 = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert r1 == r2


# ---------------------------------------------------------------------------
# 12. Empty no-trade input returns valid empty structure
# ---------------------------------------------------------------------------


def test_empty_trade_events_returns_valid_zero_structure():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(d, 0.0) for d in range(1, 6)],
    )
    rep = build_exit_diagnostics_report(
        trade_events=[],
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert rep["version"] == EXIT_DIAGNOSTICS_VERSION
    assert rep["trade_count"] == 0
    assert rep["per_trade"] == []
    # Zero-opportunity handling: all summary floats are 0.0 and
    # turnover-adjusted collapses to 0.0 (no trades).
    summary = rep["summary"]
    assert summary["avg_mfe"] == 0.0
    assert summary["avg_mae"] == 0.0
    assert summary["avg_capture_ratio"] == 0.0
    assert summary["avg_winner_giveback"] == 0.0
    assert summary["avg_exit_lag_bars"] == 0.0
    assert summary["turnover_adjusted_exit_quality"] == 0.0


# ---------------------------------------------------------------------------
# 13. Multi-trade aggregation across assets/folds
# ---------------------------------------------------------------------------


def test_multi_trade_aggregation_across_assets_and_folds():
    bars = []
    bars += _bars(
        asset="BTC",
        fold_index=0,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    bars += _bars(
        asset="ETH",
        fold_index=1,
        entries=[(1, 0.0), (2, -0.02), (3, 0.0)],
    )
    trades = [
        _trade(
            side="long",
            entry_day=1,
            exit_day=4,
            pnl=0.03958,
            asset="BTC",
            fold_index=0,
        ),
        _trade(
            side="long",
            entry_day=1,
            exit_day=3,
            pnl=-0.03,
            asset="ETH",
            fold_index=1,
        ),
    ]
    rep = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert rep["trade_count"] == 2
    assert [row["asset"] for row in rep["per_trade"]] == ["BTC", "ETH"]
    # per_trade order preserves trade_events order.
    btc = rep["per_trade"][0]
    eth = rep["per_trade"][1]
    assert btc["fold_index"] == 0
    assert eth["fold_index"] == 1
    # ETH went only down; MFE must be 0, capture/giveback None.
    assert eth["mfe"] == 0.0
    assert eth["capture_ratio"] is None
    assert eth["winner_giveback"] is None


# ---------------------------------------------------------------------------
# 14. Non-mutation of caller-owned inputs
# ---------------------------------------------------------------------------


def test_non_mutation_of_inputs():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    trades = [_trade(side="long", entry_day=1, exit_day=4, pnl=0.03958)]
    bars_copy = copy.deepcopy(bars)
    trades_copy = copy.deepcopy(trades)
    _ = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert bars == bars_copy
    assert trades == trades_copy


# ---------------------------------------------------------------------------
# 15. Engine hook: returns None when no OOS data
# ---------------------------------------------------------------------------


def test_engine_hook_returns_none_when_no_oos_data():
    from agent.backtesting.engine import BacktestEngine

    eng = BacktestEngine.__new__(BacktestEngine)
    eng.kosten_per_kant = 0.0035
    eng._last_window_streams = {}
    assert eng.build_exit_diagnostics() is None


# ---------------------------------------------------------------------------
# 16. Engine hook: groups by (asset, fold) and builds additive report
# ---------------------------------------------------------------------------


def test_engine_hook_groups_by_asset_fold_and_reports():
    from agent.backtesting.engine import BacktestEngine

    eng = BacktestEngine.__new__(BacktestEngine)
    eng.kosten_per_kant = K
    bars = []
    bars += _bars(
        asset="BTC",
        fold_index=0,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    bars += _bars(
        asset="BTC",
        fold_index=1,
        entries=[(1, 0.0), (2, 0.01), (3, 0.0)],
    )
    trades = [
        _trade(
            side="long",
            entry_day=1,
            exit_day=4,
            pnl=0.03958,
            asset="BTC",
            fold_index=0,
        ),
        _trade(
            side="long",
            entry_day=1,
            exit_day=3,
            pnl=0.005,
            asset="BTC",
            fold_index=1,
        ),
    ]
    eng._last_window_streams = {
        "oos_trade_events": trades,
        "oos_bar_returns": bars,
    }
    report = eng.build_exit_diagnostics()
    assert report is not None
    assert report["version"] == EXIT_DIAGNOSTICS_VERSION
    assert report["kosten_per_kant"] == K
    assert len(report["per_window"]) == 2
    # per_window is sorted deterministically by (asset, fold).
    asset_folds = [
        (w["asset"], w["fold_index"]) for w in report["per_window"]
    ]
    assert asset_folds == [("BTC", 0), ("BTC", 1)]
    # Each per-window block carries the full nested report shape.
    for win in report["per_window"]:
        assert set(win.keys()) >= {
            "version",
            "trade_count",
            "summary",
            "per_trade",
            "asset",
            "fold_index",
        }


# ---------------------------------------------------------------------------
# 17. Output structure stable + value types correct
# ---------------------------------------------------------------------------


def test_output_structure_is_stable():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    trades = [_trade(side="long", entry_day=1, exit_day=4, pnl=0.03958)]
    rep = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert set(rep.keys()) == {
        "version",
        "trade_count",
        "summary",
        "per_trade",
    }
    expected_summary_keys = {
        "avg_mfe",
        "avg_mae",
        "avg_capture_ratio",
        "avg_winner_giveback",
        "avg_exit_lag_bars",
        "turnover_adjusted_exit_quality",
    }
    assert set(rep["summary"].keys()) == expected_summary_keys
    for value in rep["summary"].values():
        assert isinstance(value, float)
    row = rep["per_trade"][0]
    assert set(row.keys()) == {
        "entry_timestamp_utc",
        "exit_timestamp_utc",
        "asset",
        "fold_index",
        "side",
        "mfe",
        "mae",
        "realized_return",
        "capture_ratio",
        "winner_giveback",
        "exit_lag_bars",
        "holding_bars",
    }
    assert isinstance(row["mfe"], float)
    assert isinstance(row["mae"], float)
    assert isinstance(row["realized_return"], float)
    assert isinstance(row["exit_lag_bars"], int)
    assert isinstance(row["holding_bars"], int)


# ---------------------------------------------------------------------------
# 18. Cost-sensitivity interop: diagnostics do not see scenarios
# ---------------------------------------------------------------------------


def test_exit_diagnostics_independent_of_cost_sensitivity_scenarios():
    # Running cost-sensitivity on the same streams must not alter the
    # exit-diagnostics result. Both are pure side-channels.
    from agent.backtesting.cost_sensitivity import (
        build_cost_sensitivity_report,
        ScenarioSpec,
    )

    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    trades = [_trade(side="long", entry_day=1, exit_day=4, pnl=0.03958)]
    baseline = [float(b["return"]) for b in bars]

    rep_before = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    # Fire-and-forget on same streams.
    _ = build_cost_sensitivity_report(
        events=[],
        bar_return_stream=bars,
        baseline_dag_returns=baseline,
        kosten_per_kant=K,
        scenarios=(
            ScenarioSpec(
                name="stress",
                fee_multiplier=2.0,
                slippage_bps=10.0,
            ),
        ),
    )
    rep_after = build_exit_diagnostics_report(
        trade_events=trades,
        bar_return_stream=bars,
        kosten_per_kant=K,
    )
    assert rep_before == rep_after


# ---------------------------------------------------------------------------
# 19. Validator: invalid side raises
# ---------------------------------------------------------------------------


def test_invalid_side_raises_value_error():
    with pytest.raises(ValueError):
        compute_trade_diagnostic(
            entry_timestamp_utc=_ts(1),
            exit_timestamp_utc=_ts(2),
            asset=ASSET,
            fold_index=FOLD,
            side="flat",
            realized_pnl=0.0,
            kosten_per_kant=K,
            interior_bar_returns=[],
        )


# ---------------------------------------------------------------------------
# 20. Validator: non-finite bar return raises
# ---------------------------------------------------------------------------


def test_nonfinite_bar_return_raises():
    with pytest.raises(ValueError):
        compute_trade_diagnostic(
            entry_timestamp_utc=_ts(1),
            exit_timestamp_utc=_ts(3),
            asset=ASSET,
            fold_index=FOLD,
            side="long",
            realized_pnl=0.0,
            kosten_per_kant=K,
            interior_bar_returns=[float("nan")],
        )


# ---------------------------------------------------------------------------
# 21. Validator: kosten_per_kant out of range raises
# ---------------------------------------------------------------------------


def test_kosten_per_kant_out_of_range_raises():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.0)],
    )
    with pytest.raises(ValueError):
        build_exit_diagnostics_report(
            trade_events=[],
            bar_return_stream=bars,
            kosten_per_kant=1.5,
        )
    with pytest.raises(ValueError):
        build_exit_diagnostics_report(
            trade_events=[],
            bar_return_stream=bars,
            kosten_per_kant=-0.01,
        )


# ---------------------------------------------------------------------------
# 22. extract_interior_bar_returns: happy path + alignment errors
# ---------------------------------------------------------------------------


def test_extract_interior_bar_returns_happy_path():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02), (4, 0.0)],
    )
    trade = _trade(side="long", entry_day=1, exit_day=4, pnl=0.03958)
    interior = extract_interior_bar_returns(
        trade=trade, bar_return_stream=bars
    )
    assert interior == [0.05, 0.02]


def test_extract_interior_bar_returns_missing_timestamp_raises():
    bars = _bars(
        asset=ASSET,
        fold_index=FOLD,
        entries=[(1, 0.0), (2, 0.05), (3, 0.02)],
    )
    trade = _trade(side="long", entry_day=1, exit_day=9, pnl=0.0)
    with pytest.raises(KeyError):
        extract_interior_bar_returns(
            trade=trade, bar_return_stream=bars
        )


def test_extract_interior_bar_returns_wrong_fold_partition_raises():
    bars = _bars(
        asset=ASSET,
        fold_index=7,  # fold 7, not 0
        entries=[(1, 0.0), (2, 0.0), (3, 0.0)],
    )
    trade = _trade(
        side="long",
        entry_day=1,
        exit_day=3,
        pnl=0.0,
        fold_index=0,
    )
    with pytest.raises(KeyError):
        extract_interior_bar_returns(
            trade=trade, bar_return_stream=bars
        )


# ---------------------------------------------------------------------------
# 23. TradeDiagnostic dataclass is frozen
# ---------------------------------------------------------------------------


def test_trade_diagnostic_is_frozen():
    diag = compute_trade_diagnostic(
        entry_timestamp_utc=_ts(1),
        exit_timestamp_utc=_ts(2),
        asset=ASSET,
        fold_index=FOLD,
        side="long",
        realized_pnl=0.0,
        kosten_per_kant=K,
        interior_bar_returns=[],
    )
    with pytest.raises(Exception):
        diag.mfe = 999.0  # type: ignore[misc]
    assert isinstance(diag, TradeDiagnostic)
