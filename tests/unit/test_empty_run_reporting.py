from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from agent.backtesting.engine import BacktestEngine
from research.empty_run_reporting import (
    build_degenerate_run_message,
    build_empty_run_diagnostics_payload,
)


AS_OF_UTC = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _frame(bar_count: int) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=bar_count, freq="1h")
    values = [100.0 + float(i) for i in range(bar_count)]
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": [1.0] * bar_count,
        },
        index=index,
    )


def test_build_empty_run_payload_is_deterministic_and_explicit():
    pair_diagnostics = [
        {
            "asset": "ETH-USD",
            "interval": "4h",
            "requested_start": "2024-05-13",
            "requested_end": "2026-04-13",
            "bar_count": 0,
            "fold_count": 0,
            "status": "dropped",
            "drop_reason": "empty_dataset",
        },
        {
            "asset": "BTC-USD",
            "interval": "1h",
            "requested_start": "2024-05-13",
            "requested_end": "2026-04-13",
            "bar_count": 0,
            "fold_count": 0,
            "status": "dropped",
            "drop_reason": "empty_dataset",
        },
    ]

    first = build_empty_run_diagnostics_payload(
        as_of_utc=AS_OF_UTC,
        failure_stage="preflight_no_evaluable_pairs",
        selected_assets=["BTC-USD", "ETH-USD"],
        selected_intervals=["1h", "4h"],
        interval_ranges={
            "1h": {"start": "2024-05-13", "end": "2026-04-13"},
            "4h": {"start": "2024-05-13", "end": "2026-04-13"},
        },
        pair_diagnostics=pair_diagnostics,
    )
    second = build_empty_run_diagnostics_payload(
        as_of_utc=AS_OF_UTC,
        failure_stage="preflight_no_evaluable_pairs",
        selected_assets=["BTC-USD", "ETH-USD"],
        selected_intervals=["1h", "4h"],
        interval_ranges={
            "1h": {"start": "2024-05-13", "end": "2026-04-13"},
            "4h": {"start": "2024-05-13", "end": "2026-04-13"},
        },
        pair_diagnostics=pair_diagnostics,
    )

    assert first == second
    assert first["version"] == "v1"
    assert first["summary"]["evaluable_pair_count"] == 0
    assert first["summary"]["primary_drop_reasons"] == ["empty_dataset"]
    assert first["pairs"][0]["asset"] == "BTC-USD"
    assert "stage=preflight_no_evaluable_pairs" in first["message"]
    assert "existing_public_outputs_may_be_stale=True" in first["message"]


def test_engine_inspect_asset_readiness_reuses_load_and_fold_logic(monkeypatch):
    engine = BacktestEngine(
        start_datum="2026-01-01",
        eind_datum="2026-04-01",
        evaluation_config=None,
    )
    frames = {
        "BTC-USD": pd.DataFrame(),
        "ETH-USD": _frame(50),
        "SOL-USD": _frame(150),
        "BNB-USD": _frame(700),
    }

    monkeypatch.setattr(engine, "_laad_data", lambda asset, interval: frames[asset])

    readiness = engine.inspect_asset_readiness(
        ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"],
        "1h",
    )

    assert readiness == [
        {
            "asset": "BTC-USD",
            "interval": "1h",
            "requested_start": "2026-01-01",
            "requested_end": "2026-04-01",
            "bar_count": 0,
            "fold_count": 0,
            "status": "dropped",
            "drop_reason": "empty_dataset",
        },
        {
            "asset": "ETH-USD",
            "interval": "1h",
            "requested_start": "2026-01-01",
            "requested_end": "2026-04-01",
            "bar_count": 50,
            "fold_count": 0,
            "status": "dropped",
            "drop_reason": "insufficient_data_bars",
        },
        {
            "asset": "SOL-USD",
            "interval": "1h",
            "requested_start": "2026-01-01",
            "requested_end": "2026-04-01",
            "bar_count": 150,
            "fold_count": 0,
            "status": "dropped",
            "drop_reason": "evaluation_schedule_invalid",
        },
        {
            "asset": "BNB-USD",
            "interval": "1h",
            "requested_start": "2026-01-01",
            "requested_end": "2026-04-01",
            "bar_count": 700,
            "fold_count": 2,
            "status": "evaluable",
            "drop_reason": None,
        },
    ]


def test_build_degenerate_run_message_includes_required_context():
    message = build_degenerate_run_message(
        failure_stage="postrun_no_oos_daily_returns",
        evaluable_pair_count=2,
        selected_assets=["BTC-USD", "ETH-USD"],
        selected_intervals=["1h", "4h"],
        primary_drop_reasons_list=["empty_dataset"],
        evaluations_with_oos_daily_returns=0,
    )

    assert "stage=postrun_no_oos_daily_returns" in message
    assert "evaluable_pair_count=2" in message
    assert "selected_assets=['BTC-USD', 'ETH-USD']" in message
    assert "selected_intervals=['1h', '4h']" in message
    assert "primary_drop_reasons=['empty_dataset']" in message
    assert "evaluations_with_oos_daily_returns=0" in message
