"""Engine emission tests for ExecutionEvent (v3.8 step 2).

Pins the semantics by which ``BacktestEngine._simuleer_detailed``
emits canonical ``ExecutionEvent`` records on entry and exit fills
under the current engine model (next-bar-close fills, flat
``kosten_per_kant`` on each side, no slippage model).

Step 2 emission is additive-only:

- non-emission paths (default, ``_simuleer``, training folds) are
  byte-identical to pre-Step-2 behavior.
- emission paths produce deterministic event streams that faithfully
  describe the existing fills without influencing equity math.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.engine import BacktestEngine
from agent.backtesting.execution import (
    ALLOWED_REASON_CODES,
    EXECUTION_EVENT_VERSION,
    ExecutionEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine(kosten_per_kant: float = 0.001) -> BacktestEngine:
    """Construct a minimal engine matching the existing test pattern."""
    e = BacktestEngine.__new__(BacktestEngine)
    e.kosten_per_kant = kosten_per_kant
    e.start = "2022-01-01"
    e.eind = "2023-01-01"
    e.min_trades = 5
    return e


def _ramp_frame(
    n: int = 30, start: float = 100.0, step: float = 1.0
) -> pd.DataFrame:
    """Deterministic monotonically increasing OHLCV frame."""
    close = np.array([start + step * i for i in range(n)], dtype=float)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": [10_000] * n,
        },
        index=idx,
    )


def _block_signal(df: pd.DataFrame, entry_i: int, exit_i: int) -> pd.Series:
    """Signal series: +1 from entry_i..exit_i-1, 0 elsewhere.

    Under the engine's ``shift(1)`` rule the fill happens one bar
    after the signal turns on. So entry fill is at ``entry_i + 1``,
    exit fill is at ``exit_i + 1``.
    """
    sig = pd.Series(0, index=df.index, dtype=int)
    sig.iloc[entry_i:exit_i] = 1
    return sig


def _run_detailed(
    engine: BacktestEngine,
    df: pd.DataFrame,
    signal: pd.Series,
    *,
    include_execution_events: bool,
    fold_index=None,
    asset: str = "BTC-EUR",
):
    """Wrap ``_simuleer_detailed`` with a signal-only strategy."""
    return engine._simuleer_detailed(
        df,
        lambda d: signal,
        asset,
        regime_window=None,
        fold_index=fold_index,
        include_trade_events=False,
        include_execution_events=include_execution_events,
    )


# ---------------------------------------------------------------------------
# 1. Emission gating
# ---------------------------------------------------------------------------


def test_no_events_emitted_when_flag_is_false():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    pnls, _, _, trade_events, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=False
    )
    assert len(exec_events) == 0
    # pnls still computed, proving non-emission path is live
    assert len(pnls) == 1


def test_events_emitted_for_executed_trade_when_flag_is_true():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    # One trade -> accepted+full_fill at entry AND accepted+full_fill at exit.
    assert len(exec_events) == 4
    kinds = [e.kind for e in exec_events]
    assert kinds == ["accepted", "full_fill", "accepted", "full_fill"]


# ---------------------------------------------------------------------------
# 2. Fill semantics: intended_price / fill_price / slippage
# ---------------------------------------------------------------------------


def test_fill_price_equals_intended_price_and_matches_close():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    # Entry fills at bar 6 (shift(1) of signal[5]=1); exit at bar 15
    # (signal[14]=1, signal[15]=0, shifted => sig[15]=1,
    #  sig[16]=0 => exit at i=16).
    # Recompute per shift(1).fillna(0):
    #   sig_shifted[i] = signal[i-1] for i>=1, 0 for i==0.
    # Entry: first i where shifted sig becomes 1 is i = entry_i + 1 = 6.
    # Exit: first i where shifted sig differs from current positie is
    #       i = exit_i + 1 = 16 (shifted 1 until i=15, 0 from i=16).
    entry_full_fill = exec_events[1]
    exit_full_fill = exec_events[3]
    assert entry_full_fill.kind == "full_fill"
    assert exit_full_fill.kind == "full_fill"
    assert entry_full_fill.intended_price == entry_full_fill.fill_price
    assert exit_full_fill.intended_price == exit_full_fill.fill_price
    assert entry_full_fill.fill_price == float(df["close"].iloc[6])
    assert exit_full_fill.fill_price == float(df["close"].iloc[16])


def test_slippage_bps_is_explicit_zero_under_current_semantics():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    fills = [e for e in exec_events if e.kind == "full_fill"]
    assert all(e.slippage_bps == 0.0 for e in fills)
    # Accepted events carry no slippage at all.
    accepted = [e for e in exec_events if e.kind == "accepted"]
    assert all(e.slippage_bps is None for e in accepted)


# ---------------------------------------------------------------------------
# 3. Fee attribution
# ---------------------------------------------------------------------------


def test_fee_amount_matches_current_equity_drag():
    eng = _engine(kosten_per_kant=0.0035)
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    entry_fill = exec_events[1]
    exit_fill = exec_events[3]
    # Entry fee: equity pre-entry is 1.0 (no prior trades).
    assert entry_fill.fee_amount == pytest.approx(1.0 * 0.0035)
    # Exit fee: equity at exit = 1.0 * (1 - k) [entry fee] *
    #           prod(1 + daily_ret) while in position.
    k = eng.kosten_per_kant
    equity = 1.0
    equity *= 1.0 - k  # entry side
    for i in range(7, 17):  # bars held from entry (i=6 -> flat at i=16)
        # at bar i, equity *= 1 + (close[i]/close[i-1] - 1)*positie
        # positie = 1 for bars i in [6..15] (before exit bar flips positie=0).
        if i <= 15:
            c_i = float(df["close"].iloc[i])
            c_prev = float(df["close"].iloc[i - 1])
            dag_ret = c_i / c_prev - 1.0
            equity *= 1.0 + dag_ret
    # At bar i=16 the engine marks-to-market (positie still 1 on entry equity
    # update at line ~1197-1200) then exits. Mark-to-market for i=16:
    c_16 = float(df["close"].iloc[16])
    c_15 = float(df["close"].iloc[15])
    dag_ret_exit_bar = c_16 / c_15 - 1.0
    equity *= 1.0 + dag_ret_exit_bar
    assert exit_fill.fee_amount == pytest.approx(equity * k, rel=1e-12)


def test_requested_and_filled_size_are_one_for_every_full_fill():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    fills = [e for e in exec_events if e.kind == "full_fill"]
    assert all(e.requested_size == 1.0 for e in fills)
    assert all(e.filled_size == 1.0 for e in fills)


# ---------------------------------------------------------------------------
# 4. Determinism + sequence + fold_index
# ---------------------------------------------------------------------------


def test_event_stream_is_deterministic_across_repeated_runs():
    eng1 = _engine()
    eng2 = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, events_a = _run_detailed(
        eng1, df, sig, include_execution_events=True
    )
    _, _, _, _, events_b = _run_detailed(
        eng2, df, sig, include_execution_events=True
    )
    assert events_a == events_b
    # Bytewise event_ids must also match.
    assert [e.event_id for e in events_a] == [e.event_id for e in events_b]


def test_sequence_is_monotone_within_a_single_call():
    eng = _engine()
    df = _ramp_frame(40)
    # Two separate trades: on [5..15], then on [20..30].
    sig = pd.Series(0, index=df.index, dtype=int)
    sig.iloc[5:15] = 1
    sig.iloc[20:30] = 1
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    # Two trades -> 8 events total.
    assert len(exec_events) == 8
    seqs = [e.sequence for e in exec_events]
    assert seqs == list(range(len(exec_events)))
    assert seqs == sorted(seqs)


def test_fold_index_is_carried_onto_every_event_and_into_event_id():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True, fold_index=3
    )
    assert len(exec_events) == 4
    assert all(e.fold_index == 3 for e in exec_events)
    # Fold-aware event_id prefix: "f3|{seq}|..."
    for e in exec_events:
        assert e.event_id.startswith(f"f3|{e.sequence}|")


def test_fold_index_none_path_is_unchanged_event_id_composition():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True, fold_index=None
    )
    # Step-1 None-path id shape is "{seq}|{asset}|{ts}|{kind}".
    for e in exec_events:
        assert e.event_id.startswith(f"{e.sequence}|")
        assert not e.event_id.startswith("f")


# ---------------------------------------------------------------------------
# 5. Event ordering (accepted before full_fill per fill)
# ---------------------------------------------------------------------------


def test_accepted_precedes_full_fill_and_shares_timestamp():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    # Entry pair shares ts, exit pair shares ts; exit ts > entry ts.
    assert exec_events[0].kind == "accepted"
    assert exec_events[1].kind == "full_fill"
    assert exec_events[0].timestamp_utc == exec_events[1].timestamp_utc
    assert exec_events[2].kind == "accepted"
    assert exec_events[3].kind == "full_fill"
    assert exec_events[2].timestamp_utc == exec_events[3].timestamp_utc
    assert exec_events[0].timestamp_utc < exec_events[2].timestamp_utc


# ---------------------------------------------------------------------------
# 6. No events when no execution happens
# ---------------------------------------------------------------------------


def test_no_events_when_signal_never_triggers_trade():
    eng = _engine()
    df = _ramp_frame(30)
    # Signal always flat - engine never enters a position.
    sig = pd.Series(0, index=df.index, dtype=int)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    assert exec_events == []


# ---------------------------------------------------------------------------
# 7. Equity / pnl math is unchanged by emission
# ---------------------------------------------------------------------------


def test_equity_and_pnl_match_with_and_without_emission():
    eng1 = _engine(kosten_per_kant=0.0035)
    eng2 = _engine(kosten_per_kant=0.0035)
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    p_off, d_off, m_off, t_off, e_off = _run_detailed(
        eng1, df, sig, include_execution_events=False
    )
    p_on, d_on, m_on, t_on, e_on = _run_detailed(
        eng2, df, sig, include_execution_events=True
    )
    assert p_off == p_on
    assert d_off == d_on
    assert m_off == m_on
    assert t_off == t_on
    assert e_off == [] and len(e_on) == 4


def test_simuleer_three_tuple_contract_preserved():
    """``_simuleer`` must continue to return exactly three lists."""
    eng = _engine()
    df = _ramp_frame(30)
    result = eng._simuleer(
        df, lambda d: pd.Series(1, index=d.index, dtype=int), "TEST"
    )
    assert isinstance(result, tuple)
    assert len(result) == 3
    trades, dag_rets, maand_rets = result
    assert isinstance(trades, list)
    assert isinstance(dag_rets, list)
    assert isinstance(maand_rets, list)


# ---------------------------------------------------------------------------
# 8. Event_id uniqueness across folds
# ---------------------------------------------------------------------------


def test_event_id_unique_across_folds_with_shared_timestamp():
    """Two folds evaluating the same bar produce distinct event_ids."""
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, fold_a = _run_detailed(
        eng, df, sig, include_execution_events=True, fold_index=0
    )
    _, _, _, _, fold_b = _run_detailed(
        eng, df, sig, include_execution_events=True, fold_index=1
    )
    ids_a = {e.event_id for e in fold_a}
    ids_b = {e.event_id for e in fold_b}
    assert ids_a.isdisjoint(ids_b)


# ---------------------------------------------------------------------------
# 9. Event validity (version + vocabulary pins hold end-to-end)
# ---------------------------------------------------------------------------


def test_emitted_events_are_valid_instances_with_pinned_version():
    eng = _engine()
    df = _ramp_frame(30)
    sig = _block_signal(df, entry_i=5, exit_i=15)
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    for e in exec_events:
        assert isinstance(e, ExecutionEvent)
        assert e.version == EXECUTION_EVENT_VERSION
        assert e.kind in ("accepted", "full_fill")
        assert e.side in ("long", "short")
        # No rejected / canceled emission under current engine.
        assert e.reason_code is None
    # Sanity: emission vocabulary is the Step 1 reason-code vocabulary.
    assert "NO_LIQUIDITY" in ALLOWED_REASON_CODES


def test_short_position_emits_side_short_on_both_events():
    eng = _engine()
    df = _ramp_frame(30)
    sig = pd.Series(0, index=df.index, dtype=int)
    sig.iloc[5:15] = -1  # short trade
    _, _, _, _, exec_events = _run_detailed(
        eng, df, sig, include_execution_events=True
    )
    assert len(exec_events) == 4
    assert all(e.side == "short" for e in exec_events)
