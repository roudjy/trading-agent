from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import agent.backtesting.engine as engine_module
from agent.backtesting.engine import (
    BacktestEngine,
    EngineExecutionSnapshot,
    EngineInterrupted,
)
from agent.backtesting.strategies import trend_pullback_v1_strategie
from agent.backtesting.thin_strategy import build_features_for
from research.candidate_resume import CandidateResumeState
from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_TIMED_OUT,
    ScreeningCandidateInterrupted,
    _classify_trend_pullback_exit_reason,
    _exit_health_class,
    _exit_semantic_metadata,
    _sample_diagnostics_summary,
    _trend_break_bar_path_simulation_summary,
    _trend_break_bar_path_threshold_comparison_summary,
    _trend_break_invalidation_simulation_summary,
    _trend_break_invalidation_summary,
    _trend_pullback_boundary_by_trade_key,
    _trend_pullback_exit_reason_summary,
    _trend_pullback_features_by_timestamp,
    build_screening_runtime_records,
    build_screening_sidecar_payload,
    execute_screening_candidate,
)


class FakeClock:
    def __init__(self, start: datetime):
        self.current = start
        self.mono = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.current += timedelta(seconds=seconds)


def _trend_pullback_alignment_frame() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=130, freq="D", tz=UTC)
    close_values: list[float] = []
    price = 100.0
    for i in range(len(index)):
        phase = i % 12
        if phase in (0, 1, 2, 3, 4):
            price *= 1.006
        elif phase in (5, 6):
            price *= 0.985
        elif phase in (7, 8, 9):
            price *= 1.012
        else:
            price *= 0.998
        close_values.append(price)

    close = np.array(close_values, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000,
        },
        index=index,
    )


def _captured_features_for_index(
    feature_calls: list[dict[str, object]],
    expected_index: tuple[pd.Timestamp, ...],
) -> dict[str, pd.Series] | None:
    for call in feature_calls:
        if call["index"] == expected_index:
            return call["features"]  # type: ignore[return-value]
    return None


def _feature_values_equal(left: object, right: object) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    return float(left) == pytest.approx(float(right))


def _assert_diagnostic_row_matches_engine_features(
    diagnostic_row: dict[str, object],
    engine_features: dict[str, pd.Series],
    timestamp: pd.Timestamp,
) -> None:
    for alias in ("ema_fast", "ema_slow", "pullback_distance"):
        assert _feature_values_equal(
            diagnostic_row[alias],
            engine_features[alias].get(timestamp),
        )


def _expected_empty_boundary_summary() -> dict[str, object]:
    return {
        "trade_count": 0,
        "bucket_counts": {},
        "bucket_pnl_summary": {},
        "by_exit_reason": {},
        "by_unknown_subcategory": {},
        "by_asset": {},
    }


def _expected_empty_realized_pnl_impact() -> dict[str, object]:
    return {
        "by_exit_reason": {},
        "by_unknown_subcategory": {},
        "by_boundary_proximity_bucket": {},
        "by_asset": {},
        "by_fold_index": {},
    }


def _capture_engine_plain_feature_calls(monkeypatch) -> list[dict[str, object]]:
    feature_calls: list[dict[str, object]] = []
    real_engine_build_features_for = engine_module.build_features_for

    def _capturing_engine_build_features_for(requirements, df):
        features = real_engine_build_features_for(requirements, df)
        feature_calls.append(
            {
                "index": tuple(df.index),
                "features": {
                    alias: series.copy()
                    for alias, series in features.items()
                },
            }
        )
        return features

    monkeypatch.setattr(
        engine_module,
        "build_features_for",
        _capturing_engine_build_features_for,
    )
    return feature_calls


def test_screening_sidecar_payload_counts_are_deterministic():
    records = build_screening_runtime_records(
        candidates=[
            {"candidate_id": "b", "strategy_name": "beta", "asset": "ETH-USD", "interval": "1h"},
            {"candidate_id": "a", "strategy_name": "alpha", "asset": "BTC-USD", "interval": "1d"},
        ],
        budget_seconds=30,
    )
    records[0]["final_status"] = "rejected"
    records[1]["final_status"] = "passed"

    payload = build_screening_sidecar_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC),
        records=records,
    )

    assert payload["summary"] == {
        "candidate_count": 2,
        "pending_count": 0,
        "running_count": 0,
        "passed_count": 1,
        "rejected_count": 1,
        "timed_out_count": 0,
        "errored_count": 0,
        "skipped_count": 0,
    }
    assert [item["candidate_id"] for item in payload["candidates"]] == ["a", "b"]


def test_execute_screening_candidate_times_out_cooperatively():
    clock = FakeClock(datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC))

    class SlowEngine:
        def __init__(self):
            self.last_evaluation_report = None

        def run(self, strategie_func, assets, interval="1d"):
            clock.advance(2)
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.01, -0.01],
                }
            }
            return {
                "totaal_trades": 12,
                "goedgekeurd": True,
            }

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"periode": [14, 21, 28]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=SlowEngine(),
        budget_seconds=1,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )

    assert outcome["final_status"] == FINAL_STATUS_TIMED_OUT
    assert outcome["reason_code"] == "candidate_budget_exceeded"
    assert outcome["samples_total"] == 3
    assert outcome["samples_completed"] == 1
    assert outcome["legacy_decision"]["reason"] == "candidate_budget_exceeded"


def test_execute_screening_candidate_surfaces_candidate_error():
    clock = FakeClock(datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC))

    class BrokenEngine:
        def run(self, strategie_func, assets, interval="1d"):
            raise RuntimeError("boom")

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: None,
            "params": {"periode": [14]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=BrokenEngine(),
        budget_seconds=30,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )

    assert outcome["final_status"] == FINAL_STATUS_ERRORED
    assert outcome["reason_code"] == "screening_candidate_error"
    assert outcome["reason_detail"] == "boom"
    assert outcome["samples_completed"] == 0


def test_execute_screening_candidate_resume_matches_fresh_result():
    class ResumeAwareEngine:
        def __init__(self, interrupt_on_second_sample: bool):
            self.interrupt_on_second_sample = interrupt_on_second_sample
            self.last_evaluation_report = None

        def run(
            self,
            strategie_func,
            assets,
            interval="1d",
            deadline_monotonic=None,
            resume_snapshot=None,
        ):
            periode = int(strategie_func.params["periode"])
            if self.interrupt_on_second_sample and periode == 21 and resume_snapshot is None:
                raise EngineInterrupted(
                    reason="stop_requested",
                    snapshot=EngineExecutionSnapshot(
                        phase="evaluate_out_of_sample",
                        asset_index=0,
                        fold_index=0,
                        completed_window_ids=(("BTC-USD", "train", 0),),
                    ),
                )
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.01, -0.01],
                }
            }
            return {
                "totaal_trades": 12,
                "goedgekeurd": periode == 14,
            }

    strategy = {
        "factory": lambda **params: SimpleNamespace(params=params),
        "params": {"periode": [14, 21]},
    }
    candidate = {"candidate_id": "candidate-1", "asset": "BTC-USD", "interval": "1d"}

    fresh_outcome = execute_screening_candidate(
        strategy=strategy,
        candidate=candidate,
        engine=ResumeAwareEngine(interrupt_on_second_sample=False),
        budget_seconds=30,
        max_samples=2,
    )

    interrupted = None
    try:
        execute_screening_candidate(
            strategy=strategy,
            candidate=candidate,
            engine=ResumeAwareEngine(interrupt_on_second_sample=True),
            budget_seconds=30,
            max_samples=2,
        )
    except ScreeningCandidateInterrupted as exc:
        interrupted = exc

    assert interrupted is not None

    resumed_outcome = execute_screening_candidate(
        strategy=strategy,
        candidate=candidate,
        engine=ResumeAwareEngine(interrupt_on_second_sample=True),
        budget_seconds=30,
        max_samples=2,
        resume_state=CandidateResumeState(
            completed_samples=tuple(interrupted.completed_samples),
            active_sample_index=interrupted.active_sample_index,
            active_snapshot=interrupted.engine_snapshot,
        ),
    )

    comparable_keys = {
        key: value
        for key, value in fresh_outcome.items()
        if key not in {"started_at", "finished_at", "sample_diagnostics", "sample_diagnostics_summary"}
    }
    resumed_comparable = {
        key: value
        for key, value in resumed_outcome.items()
        if key not in {"started_at", "finished_at", "sample_diagnostics", "sample_diagnostics_summary"}
    }
    assert resumed_comparable == comparable_keys

def test_execute_screening_candidate_blocks_zero_trade_promoted_sample() -> None:
    class ZeroTradePassLikeEngine:
        min_trades = 10

        def __init__(self):
            self.last_evaluation_report = None

        def run(self, strategie_func, assets, interval="1d"):
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.0, 0.0],
                }
            }
            return {
                "expectancy": 1.0,
                "profit_factor": 2.0,
                "win_rate": 1.0,
                "max_drawdown": 0.0,
                "totaal_trades": 0,
                "trades_per_maand": 0.0,
                "goedgekeurd": True,
            }

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"periode": [14]},
        },
        candidate={"asset": "NVDA", "interval": "4h"},
        engine=ZeroTradePassLikeEngine(),
        budget_seconds=30,
        max_samples=1,
        screening_phase="exploratory",
    )

    assert outcome["decision"] == "rejected_in_screening"
    assert outcome["final_status"] == "rejected"
    assert outcome["reason_code"] == "insufficient_trades"
    assert outcome["legacy_decision"] == {
        "status": "rejected_in_screening",
        "reason": "insufficient_trades",
        "sampled_combination_count": 1,
    }
    assert outcome["pass_kind"] is None
    assert outcome["diagnostic_metrics"]["totaal_trades"] == 0.0
    assert outcome["diagnostic_metrics"]["trades_per_maand"] == 0.0


def test_execute_screening_candidate_relabels_zero_trade_rejected_sample() -> None:
    class ZeroTradeRejectedLikeEngine:
        min_trades = 10

        def __init__(self):
            self.last_evaluation_report = None

        def run(self, strategie_func, assets, interval="1d"):
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.0, 0.0],
                }
            }
            return {
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "totaal_trades": 0,
                "trades_per_maand": 0.0,
                "goedgekeurd": False,
            }

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"periode": [14]},
        },
        candidate={"asset": "AMD", "interval": "4h"},
        engine=ZeroTradeRejectedLikeEngine(),
        budget_seconds=30,
        max_samples=1,
        screening_phase="exploratory",
    )

    assert outcome["decision"] == "rejected_in_screening"
    assert outcome["final_status"] == "rejected"
    assert outcome["reason_code"] == "insufficient_trades"
    assert outcome["legacy_decision"] == {
        "status": "rejected_in_screening",
        "reason": "insufficient_trades",
        "sampled_combination_count": 1,
    }
    assert outcome["diagnostic_metrics"]["totaal_trades"] == 0.0
    assert outcome["diagnostic_metrics"]["trades_per_maand"] == 0.0


def test_execute_screening_candidate_keeps_promoted_sample_when_later_sample_insufficient() -> None:
    class MixedSampleEngine:
        min_trades = 10

        def __init__(self):
            self.last_evaluation_report = None
            self.calls = 0

        def run(self, strategie_func, assets, interval="1d"):
            self.calls += 1
            if self.calls == 1:
                self.last_evaluation_report = {
                    "evaluation_samples": {
                        "daily_returns": [0.01, -0.01],
                        "trade_pnls": [0.03, 0.01, -0.02],
                    }
                }
                return {
                    "expectancy": 0.02,
                    "profit_factor": 2.0,
                    "win_rate": 0.6,
                    "max_drawdown": 0.05,
                    "totaal_trades": 12,
                    "trades_per_maand": 1.0,
                    "goedgekeurd": True,
                }
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.0, 0.0],
                    "trade_pnls": [],
                }
            }
            return {
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "totaal_trades": 0,
                "trades_per_maand": 0.0,
                "goedgekeurd": False,
            }

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"periode": [14, 21]},
        },
        candidate={"asset": "NVDA", "interval": "4h"},
        engine=MixedSampleEngine(),
        budget_seconds=30,
        max_samples=2,
        screening_phase="exploratory",
    )

    assert outcome["decision"] == "promoted_to_validation"
    assert outcome["final_status"] == "passed"
    assert outcome["reason_code"] is None
    assert outcome["legacy_decision"] == {
        "status": "promoted_to_validation",
        "reason": None,
        "sampled_combination_count": 2,
    }
    assert outcome["diagnostic_metrics"]["expectancy"] == 0.02
    assert outcome["diagnostic_metrics"]["profit_factor"] == 2.0
    assert outcome["diagnostic_metrics"]["win_rate"] == 0.6
    assert outcome["diagnostic_metrics"]["totaal_trades"] == 12.0
    assert outcome["diagnostic_metrics"]["trades_per_maand"] == 1.0
    assert outcome["diagnostic_metrics"]["criteria_checks"]
    assert outcome["sample_diagnostics_summary"] == {
        "sample_count": 2,
        "promoted_sample_count": 1,
        "rejected_sample_count": 1,
        "rejection_reason_counts": {
            "insufficient_trades": 1,
            "passed": 1,
        },
        "best_sample_index": 0,
        "best_expectancy": 0.02,
        "best_profit_factor": 2.0,
        "best_totaal_trades": 12.0,
        "best_sample_exit_quality_audit": {
            "advisory_only": True,
            "selected_best_sample_index": 0,
            "performance_best_sample_index": 0,
            "exit_quality_best_sample_index": 0,
            "exit_quality_disagreement": False,
            "selected_sample_health_score": 0.0,
            "exit_quality_best_health_score": 0.0,
            "selected_sample_risk_exit_share": 0.0,
            "selected_sample_unknown_exit_share": 0.0,
            "selected_sample_boundary_exit_share": 0.0,
            "selected_sample_late_or_choppy_exit_share": 0.0,
            "selected_sample_total_pnl": 0.0,
            "selected_sample_risk_exit_total_pnl": 0.0,
            "advisory_message": (
                "Selected performance-best sample matches advisory "
                "exit-quality-best sample."
            ),
        },
    }
    assert outcome["sample_diagnostics"] == [
        {
            "sample_index": 0,
            "params": {"periode": 14},
            "status": "promoted_to_validation",
            "reason": None,
            "criteria_checks": {
                "sufficient_trades": True,
                "expectancy_above_zero": True,
                "profit_factor_at_or_above_floor": True,
                "drawdown_within_limit": True,
            },
            "trade_distribution": {
                "trade_count": 3,
                "avg_trade_pnl": 0.006667,
                "median_trade_pnl": 0.01,
                "avg_win": 0.02,
                "avg_loss": -0.02,
                "largest_win": 0.03,
                "largest_loss": -0.02,
                "win_loss_ratio": 1.0,
            },
            "exit_metadata_summary": {
                "trade_count": 0,
                "exit_kind_counts": {},
                "signal_change_count": 0,
                "window_end_count": 0,
                "unknown_exit_kind_count": 0,
                "has_exit_decision_timestamps": False,
            },
            "trend_pullback_exit_reason_summary": {
                "trade_count": 0,
                "exit_reason_counts": {},
                "exit_reason_semantics": {},
                "exit_reason_pnl_summary": {},
                "signal_change_unknown_subcategory_counts": {},
                "signal_change_unknown_subcategory_pnl_summary": {},
                "realized_pnl_impact": _expected_empty_realized_pnl_impact(),
                "exit_health_summary": _expected_empty_exit_health_summary(),
                "boundary_proximity_summary": _expected_empty_boundary_summary(),
                "pullback_resolved_count": 0,
                "trend_break_count": 0,
                "pullback_resolved_and_trend_break_count": 0,
                "window_end_count": 0,
                "signal_change_unknown_count": 0,
            },
            "trend_break_invalidation_summary": None,
            "trend_break_invalidation_simulation_summary": None,
            "trend_break_bar_path_simulation_summary": None,
            "trend_break_bar_path_threshold_comparison_summary": None,
            "metrics": {
                "expectancy": 0.02,
                "profit_factor": 2.0,
                "win_rate": 0.6,
                "max_drawdown": 0.05,
                "totaal_trades": 12.0,
                "trades_per_maand": 1.0,
            },
        },
        {
            "sample_index": 1,
            "params": {"periode": 21},
            "status": "rejected_in_screening",
            "reason": "insufficient_trades",
            "criteria_checks": {
                "sufficient_trades": False,
                "expectancy_above_zero": False,
                "profit_factor_at_or_above_floor": False,
                "drawdown_within_limit": True,
            },
            "trade_distribution": {
                "trade_count": 0,
                "avg_trade_pnl": 0.0,
                "median_trade_pnl": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0,
                "win_loss_ratio": 0.0,
            },
            "exit_metadata_summary": {
                "trade_count": 0,
                "exit_kind_counts": {},
                "signal_change_count": 0,
                "window_end_count": 0,
                "unknown_exit_kind_count": 0,
                "has_exit_decision_timestamps": False,
            },
            "trend_pullback_exit_reason_summary": {
                "trade_count": 0,
                "exit_reason_counts": {},
                "exit_reason_semantics": {},
                "exit_reason_pnl_summary": {},
                "signal_change_unknown_subcategory_counts": {},
                "signal_change_unknown_subcategory_pnl_summary": {},
                "realized_pnl_impact": _expected_empty_realized_pnl_impact(),
                "exit_health_summary": _expected_empty_exit_health_summary(),
                "boundary_proximity_summary": _expected_empty_boundary_summary(),
                "pullback_resolved_count": 0,
                "trend_break_count": 0,
                "pullback_resolved_and_trend_break_count": 0,
                "window_end_count": 0,
                "signal_change_unknown_count": 0,
            },
            "trend_break_invalidation_summary": None,
            "trend_break_invalidation_simulation_summary": None,
            "trend_break_bar_path_simulation_summary": None,
            "trend_break_bar_path_threshold_comparison_summary": None,
            "metrics": {
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "totaal_trades": 0.0,
                "trades_per_maand": 0.0,
            },
        },
    ]

def test_classify_trend_pullback_exit_reason_from_decision_features() -> None:
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=1.0,
            ema_fast=101.0,
            ema_slow=100.0,
            exit_kind="signal_change",
        )
        == "pullback_resolved"
    )
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=-1.0,
            ema_fast=99.0,
            ema_slow=100.0,
            exit_kind="signal_change",
        )
        == "trend_break"
    )
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=1.0,
            ema_fast=99.0,
            ema_slow=100.0,
            exit_kind="signal_change",
        )
        == "pullback_resolved_and_trend_break"
    )
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=-1.0,
            ema_fast=101.0,
            ema_slow=100.0,
            exit_kind="signal_change",
        )
        == "signal_change_unknown"
    )


def test_pullback_resolved_and_trend_break_has_ambiguous_advisory_semantics() -> None:
    reason = _classify_trend_pullback_exit_reason(
        pullback_distance=1.0,
        ema_fast=99.0,
        ema_slow=100.0,
        exit_kind="signal_change",
    )

    assert reason == "pullback_resolved_and_trend_break"
    assert reason != "pullback_resolved"

    semantic = _exit_semantic_metadata(reason)
    assert semantic["exit_semantic_class"] == "ambiguous_late_or_choppy_exit"
    assert semantic["exit_semantic_label"] == (
        "simultaneous pullback resolution and trend break"
    )
    assert semantic["exit_semantic_warning"] == "not automatically healthy"

    summary = _trend_pullback_exit_reason_summary(
        trade_events=[
            {
                "exit_decision_timestamp_utc": "decision",
                "exit_kind": "signal_change",
            },
        ],
        features_by_timestamp={
            "decision": {
                "pullback_distance": 1.0,
                "ema_fast": 99.0,
                "ema_slow": 100.0,
            },
        },
    )
    assert summary["exit_reason_counts"] == {
        "pullback_resolved_and_trend_break": 1,
    }
    assert summary["exit_reason_semantics"][
        "pullback_resolved_and_trend_break"
    ]["exit_semantic_class"] == "ambiguous_late_or_choppy_exit"


def _expected_empty_exit_health_summary() -> dict[str, object]:
    return {
        "advisory_only": True,
        "taxonomy": [
            "healthy_exit",
            "risk_exit",
            "late_or_choppy_exit",
            "boundary_exit",
            "unknown_exit",
            "neutral_exit",
        ],
        "overall": {
            "trade_count": 0,
            "total_pnl": 0.0,
            "health_class_counts": {},
            "by_health_class": {},
        },
        "by_asset": {},
        "by_exit_reason": {},
        "by_unknown_subcategory": {},
        "by_boundary_proximity_bucket": {},
    }


def test_exit_health_ratio_v1_maps_reasons_and_keeps_boundary_context_separate() -> None:
    assert _exit_health_class("pullback_resolved") == "healthy_exit"
    assert _exit_health_class("trend_break") == "risk_exit"
    assert (
        _exit_health_class("pullback_resolved_and_trend_break")
        == "late_or_choppy_exit"
    )
    assert _exit_health_class("signal_change_unknown") == "unknown_exit"
    assert _exit_health_class("window_end") == "boundary_exit"
    assert _exit_health_class("unsupported_reason") == "neutral_exit"

    trade_events = [
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": "healthy",
            "exit_kind": "signal_change",
            "pnl": 0.04,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": "risk",
            "exit_kind": "signal_change",
            "pnl": -0.03,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": "late",
            "exit_kind": "signal_change",
            "pnl": -0.01,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": "unknown",
            "exit_kind": "signal_change",
            "pnl": 0.0,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": "boundary",
            "exit_kind": "window_end",
            "pnl": 0.0,
        },
    ]
    features_by_timestamp = {
        "healthy": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        "risk": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "late": {
            "pullback_distance": 1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "unknown": {
            "pullback_distance": -1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        "boundary": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    summary = _trend_pullback_exit_reason_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        boundary_by_trade_key={
            ("TEST", 0, "risk"): {"bars_to_window_end": 1},
            ("TEST", 0, "boundary"): {"bars_to_window_end": 0},
        },
    )

    health = summary["exit_health_summary"]
    assert health["advisory_only"] is True
    assert health["overall"]["health_class_counts"] == {
        "boundary_exit": 1,
        "healthy_exit": 1,
        "late_or_choppy_exit": 1,
        "risk_exit": 1,
        "unknown_exit": 1,
    }
    assert health["overall"]["by_health_class"]["healthy_exit"][
        "trade_share"
    ] == 0.2
    assert health["overall"]["by_health_class"]["risk_exit"]["total_pnl"] == -0.03
    assert health["overall"]["by_health_class"]["risk_exit"]["pnl_share"] == 0.0
    assert health["by_exit_reason"]["trend_break"]["exit_health_class"] == "risk_exit"
    assert health["by_exit_reason"]["pullback_resolved_and_trend_break"][
        "exit_health_class"
    ] == "late_or_choppy_exit"
    assert health["by_unknown_subcategory"]["signal_change_ambiguous_transition"][
        "health_class_counts"
    ] == {"unknown_exit": 1}
    assert health["by_boundary_proximity_bucket"]["near_window_end_1_bar"][
        "health_class_counts"
    ] == {"risk_exit": 1}
    assert health["by_boundary_proximity_bucket"]["window_end"][
        "health_class_counts"
    ] == {"boundary_exit": 1}


def test_exit_health_ratio_handles_zero_total_pnl_safely() -> None:
    summary = _trend_pullback_exit_reason_summary(
        trade_events=[
            {
                "exit_decision_timestamp_utc": "healthy",
                "exit_kind": "signal_change",
                "pnl": 0.01,
            },
            {
                "exit_decision_timestamp_utc": "risk",
                "exit_kind": "signal_change",
                "pnl": -0.01,
            },
        ],
        features_by_timestamp={
            "healthy": {
                "pullback_distance": 1.0,
                "ema_fast": 101.0,
                "ema_slow": 100.0,
            },
            "risk": {
                "pullback_distance": -1.0,
                "ema_fast": 99.0,
                "ema_slow": 100.0,
            },
        },
    )

    health = summary["exit_health_summary"]["overall"]["by_health_class"]
    assert health["healthy_exit"]["pnl_share"] == 0.0
    assert health["risk_exit"]["pnl_share"] == 0.0
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=-1.0,
            ema_fast=101.0,
            ema_slow=100.0,
            exit_kind="window_end",
        )
        == "window_end"
    )
    assert (
        _classify_trend_pullback_exit_reason(
            pullback_distance=None,
            ema_fast=101.0,
            ema_slow=100.0,
            exit_kind="signal_change",
        )
        == "signal_change_unknown"
    )

def test_trend_pullback_exit_reason_summary_counts_decision_reasons() -> None:
    trade_events = [
        {"exit_decision_timestamp_utc": "t1", "exit_kind": "signal_change"},
        {"exit_decision_timestamp_utc": "t2", "exit_kind": "signal_change"},
        {"exit_decision_timestamp_utc": "t3", "exit_kind": "signal_change"},
        {"exit_decision_timestamp_utc": "t4", "exit_kind": "window_end"},
        {"exit_decision_timestamp_utc": "missing", "exit_kind": "signal_change"},
    ]
    features_by_timestamp = {
        "t1": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        "t2": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "t3": {
            "pullback_distance": 1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "t4": {
            "pullback_distance": -1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }

    summary = _trend_pullback_exit_reason_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
    )

    assert summary["trade_count"] == 5
    assert summary["exit_reason_counts"] == {
        "pullback_resolved": 1,
        "pullback_resolved_and_trend_break": 1,
        "signal_change_unknown": 1,
        "trend_break": 1,
        "window_end": 1,
    }
    assert summary["signal_change_unknown_subcategory_counts"] == {
        "signal_change_missing_feature_timestamp": 1,
    }
    assert summary["pullback_resolved_count"] == 1
    assert summary["trend_break_count"] == 1
    assert summary["pullback_resolved_and_trend_break_count"] == 1
    assert summary["window_end_count"] == 1
    assert summary["signal_change_unknown_count"] == 1

    impact = summary["realized_pnl_impact"]
    assert impact["by_exit_reason"]["trend_break"]["trade_count"] == 1
    assert impact["by_exit_reason"]["trend_break"]["total_pnl"] == 0.0
    assert impact["by_exit_reason"]["trend_break"]["median_pnl"] == 0.0
    assert impact["by_unknown_subcategory"][
        "signal_change_missing_feature_timestamp"
    ]["total_pnl"] == 0.0
    assert impact["by_boundary_proximity_bucket"][
        "unknown_boundary_distance"
    ]["trade_count"] == 5

    boundary = summary["boundary_proximity_summary"]
    assert boundary["trade_count"] == 5
    assert boundary["bucket_counts"] == {"unknown_boundary_distance": 5}
    assert boundary["by_exit_reason"]["trend_break"]["bucket_counts"] == {
        "unknown_boundary_distance": 1,
    }
    assert boundary["by_unknown_subcategory"][
        "signal_change_missing_feature_timestamp"
    ]["bucket_counts"] == {"unknown_boundary_distance": 1}


def test_trend_pullback_exit_reason_summary_explains_unknown_subcategories() -> None:
    trade_events = [
        {
            "exit_kind": "signal_change",
            "pnl": -0.01,
        },
        {
            "exit_decision_timestamp_utc": "missing-feature-row",
            "exit_kind": "signal_change",
            "pnl": -0.02,
        },
        {
            "exit_decision_timestamp_utc": "nan-feature-row",
            "exit_kind": "signal_change",
            "pnl": -0.03,
        },
        {
            "exit_decision_timestamp_utc": "ambiguous-state",
            "exit_kind": "signal_change",
            "pnl": 0.04,
        },
        {
            "exit_decision_timestamp_utc": "trend-break",
            "exit_kind": "signal_change",
            "pnl": -0.05,
        },
    ]
    features_by_timestamp = {
        "nan-feature-row": {
            "pullback_distance": float("nan"),
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        "ambiguous-state": {
            "pullback_distance": -1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        "trend-break": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
    }

    summary = _trend_pullback_exit_reason_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
    )

    assert summary["exit_reason_counts"] == {
        "signal_change_unknown": 4,
        "trend_break": 1,
    }
    assert summary["signal_change_unknown_count"] == 4
    assert summary["signal_change_unknown_subcategory_counts"] == {
        "signal_change_ambiguous_transition": 1,
        "signal_change_feature_unavailable": 1,
        "signal_change_missing_feature_timestamp": 1,
        "signal_change_missing_metadata": 1,
    }
    subtype_pnl = summary["signal_change_unknown_subcategory_pnl_summary"]
    assert subtype_pnl["signal_change_ambiguous_transition"] == {
        "trade_count": 1,
        "total_pnl": 0.04,
        "avg_pnl": 0.04,
        "median_pnl": 0.04,
        "loss_count": 0,
        "winner_count": 1,
        "loss_pnl_total": 0.0,
        "winner_pnl_total": 0.04,
        "loss_rate": 0.0,
        "win_rate": 1.0,
        "largest_loss": 0.0,
        "largest_win": 0.04,
    }
    assert subtype_pnl["signal_change_feature_unavailable"] == {
        "trade_count": 1,
        "total_pnl": -0.03,
        "avg_pnl": -0.03,
        "median_pnl": -0.03,
        "loss_count": 1,
        "winner_count": 0,
        "loss_pnl_total": -0.03,
        "winner_pnl_total": 0.0,
        "loss_rate": 1.0,
        "win_rate": 0.0,
        "largest_loss": -0.03,
        "largest_win": 0.0,
    }
    assert summary["realized_pnl_impact"]["by_unknown_subcategory"] == subtype_pnl


def test_trend_pullback_exit_reason_summary_hardens_realized_pnl_impact_dimensions() -> None:
    trade_events = [
        {
            "asset": "LOW",
            "fold_index": 0,
            "exit_decision_timestamp_utc": f"pullback-{idx}",
            "exit_kind": "signal_change",
            "pnl": 0.001,
        }
        for idx in range(5)
    ]
    trade_events.extend(
        [
            {
                "asset": "HIGH",
                "fold_index": 1,
                "exit_decision_timestamp_utc": "trend-break-damage",
                "exit_kind": "signal_change",
                "pnl": -0.12,
            },
            {
                "asset": "HIGH",
                "fold_index": 1,
                "exit_decision_timestamp_utc": "ambiguous-unknown",
                "exit_kind": "signal_change",
                "pnl": -0.03,
            },
        ]
    )
    features_by_timestamp = {
        **{
            f"pullback-{idx}": {
                "pullback_distance": 1.0,
                "ema_fast": 101.0,
                "ema_slow": 100.0,
            }
            for idx in range(5)
        },
        "trend-break-damage": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "ambiguous-unknown": {
            "pullback_distance": -1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    boundary_by_trade_key = {
        ("LOW", 0, f"pullback-{idx}"): {"bars_to_window_end": 4 + idx}
        for idx in range(5)
    }
    boundary_by_trade_key[("HIGH", 1, "trend-break-damage")] = {
        "bars_to_window_end": 1,
    }
    boundary_by_trade_key[("HIGH", 1, "ambiguous-unknown")] = {
        "bars_to_window_end": 0,
    }

    summary = _trend_pullback_exit_reason_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        boundary_by_trade_key=boundary_by_trade_key,
    )

    assert summary["exit_reason_counts"] == {
        "pullback_resolved": 5,
        "signal_change_unknown": 1,
        "trend_break": 1,
    }
    impact = summary["realized_pnl_impact"]
    assert impact["by_exit_reason"]["pullback_resolved"]["trade_count"] == 5
    assert impact["by_exit_reason"]["pullback_resolved"]["total_pnl"] == pytest.approx(
        0.005
    )
    assert impact["by_exit_reason"]["trend_break"]["trade_count"] == 1
    assert impact["by_exit_reason"]["trend_break"]["total_pnl"] == -0.12
    assert impact["by_exit_reason"]["trend_break"]["loss_rate"] == 1.0
    assert impact["by_unknown_subcategory"][
        "signal_change_ambiguous_transition"
    ]["total_pnl"] == -0.03
    assert impact["by_boundary_proximity_bucket"][
        "near_window_end_1_bar"
    ]["total_pnl"] == -0.12
    assert impact["by_boundary_proximity_bucket"]["window_end"]["total_pnl"] == -0.03
    assert impact["by_asset"]["LOW"]["trade_count"] == 5
    assert impact["by_asset"]["LOW"]["total_pnl"] == pytest.approx(0.005)
    assert impact["by_asset"]["HIGH"]["trade_count"] == 2
    assert impact["by_asset"]["HIGH"]["total_pnl"] == -0.15
    assert impact["by_fold_index"]["0"]["total_pnl"] == pytest.approx(0.005)
    assert impact["by_fold_index"]["1"]["total_pnl"] == -0.15


def test_trend_pullback_boundary_proximity_summary_is_report_only() -> None:
    index = pd.date_range(
        "2025-01-01",
        periods=6,
        freq="1D",
        tz=UTC,
    )
    frame = pd.DataFrame({"close": [100, 101, 102, 103, 104, 105]}, index=index)
    engine = SimpleNamespace(
        _laad_data=lambda asset, interval: frame.copy(),
        _timestamp_to_utc_iso=lambda timestamp: pd.Timestamp(timestamp)
        .tz_convert(UTC)
        .isoformat(),
    )
    candidate = {"asset": "TEST", "interval": "1d"}
    boundary_by_trade_key = _trend_pullback_boundary_by_trade_key(
        engine=engine,
        candidate=candidate,
        evaluation_report={
            "folds_by_asset": {
                "TEST": [
                    {"test": [0, 5]},
                ],
            },
        },
    )

    timestamps = [pd.Timestamp(ts).tz_convert(UTC).isoformat() for ts in index]
    assert boundary_by_trade_key[("TEST", 0, timestamps[5])][
        "bars_to_window_end"
    ] == 0
    assert boundary_by_trade_key[("TEST", 0, timestamps[4])][
        "bars_to_window_end"
    ] == 1
    assert boundary_by_trade_key[("TEST", 0, timestamps[3])][
        "bars_to_window_end"
    ] == 2

    trade_events = [
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": timestamps[5],
            "exit_kind": "signal_change",
            "pnl": -0.05,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": timestamps[4],
            "exit_kind": "signal_change",
            "pnl": 0.03,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": timestamps[3],
            "exit_kind": "signal_change",
            "pnl": -0.02,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": timestamps[0],
            "exit_kind": "signal_change",
            "pnl": 0.04,
        },
        {
            "asset": "TEST",
            "fold_index": 0,
            "exit_decision_timestamp_utc": timestamps[4],
            "exit_kind": "window_end",
            "pnl": 0.01,
        },
        {
            "exit_kind": "signal_change",
            "pnl": -0.06,
        },
    ]
    features_by_timestamp = {
        timestamps[5]: {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        timestamps[4]: {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        timestamps[3]: {
            "pullback_distance": -1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
        timestamps[0]: {
            "pullback_distance": 1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
    }

    summary = _trend_pullback_exit_reason_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        boundary_by_trade_key=boundary_by_trade_key,
    )

    assert summary["exit_reason_counts"] == {
        "pullback_resolved": 1,
        "pullback_resolved_and_trend_break": 1,
        "signal_change_unknown": 2,
        "trend_break": 1,
        "window_end": 1,
    }
    boundary = summary["boundary_proximity_summary"]
    assert boundary["bucket_counts"] == {
        "near_window_end_1_bar": 1,
        "near_window_end_2_to_3_bars": 1,
        "not_near_window_end": 1,
        "unknown_boundary_distance": 1,
        "window_end": 2,
    }
    assert boundary["bucket_pnl_summary"]["window_end"] == {
        "trade_count": 2,
        "total_pnl": -0.04,
        "avg_pnl": -0.02,
        "median_pnl": -0.02,
        "loss_count": 1,
        "winner_count": 1,
        "loss_pnl_total": -0.05,
        "winner_pnl_total": 0.01,
        "loss_rate": 0.5,
        "win_rate": 0.5,
        "largest_loss": -0.05,
        "largest_win": 0.01,
    }
    assert boundary["by_exit_reason"]["trend_break"]["bucket_counts"] == {
        "window_end": 1,
    }
    assert boundary["by_exit_reason"]["window_end"]["bucket_counts"] == {
        "window_end": 1,
    }
    assert boundary["by_unknown_subcategory"][
        "signal_change_ambiguous_transition"
    ]["bucket_counts"] == {
        "near_window_end_2_to_3_bars": 1,
    }
    assert boundary["by_unknown_subcategory"][
        "signal_change_missing_metadata"
    ]["bucket_counts"] == {
        "unknown_boundary_distance": 1,
    }
    assert boundary["by_asset"]["TEST"]["bucket_counts"] == {
        "near_window_end_1_bar": 1,
        "near_window_end_2_to_3_bars": 1,
        "not_near_window_end": 1,
        "window_end": 2,
    }
    impact = summary["realized_pnl_impact"]
    assert impact["by_boundary_proximity_bucket"]["window_end"] == {
        "trade_count": 2,
        "total_pnl": -0.04,
        "avg_pnl": -0.02,
        "median_pnl": -0.02,
        "loss_count": 1,
        "winner_count": 1,
        "loss_pnl_total": -0.05,
        "winner_pnl_total": 0.01,
        "loss_rate": 0.5,
        "win_rate": 0.5,
        "largest_loss": -0.05,
        "largest_win": 0.01,
    }
    assert impact["by_asset"]["TEST"]["total_pnl"] == pytest.approx(0.01)
    assert impact["by_fold_index"]["0"]["trade_count"] == 5


def test_sample_selection_ignores_boundary_proximity_diagnostics() -> None:
    sample_diagnostics = [
        {
            "sample_index": 0,
            "criteria_checks": {"sufficient_trades": True},
            "status": "promoted_to_validation",
            "reason": None,
            "metrics": {
                "expectancy": 0.02,
                "profit_factor": 1.5,
                "totaal_trades": 10,
            },
            "trend_pullback_exit_reason_summary": {
                "boundary_proximity_summary": {
                    "bucket_counts": {"window_end": 10},
                },
            },
        },
        {
            "sample_index": 1,
            "criteria_checks": {"sufficient_trades": True},
            "status": "promoted_to_validation",
            "reason": None,
            "metrics": {
                "expectancy": 0.01,
                "profit_factor": 5.0,
                "totaal_trades": 100,
            },
            "trend_pullback_exit_reason_summary": {
                "boundary_proximity_summary": {
                    "bucket_counts": {"not_near_window_end": 100},
                },
            },
        },
    ]

    assert _sample_diagnostics_summary(sample_diagnostics)["best_sample_index"] == 0


def test_best_sample_exit_quality_audit_flags_disagreement_without_changing_selection() -> None:
    sample_diagnostics = [
        {
            "sample_index": 0,
            "criteria_checks": {"sufficient_trades": True},
            "status": "promoted_to_validation",
            "reason": None,
            "metrics": {
                "expectancy": 0.05,
                "profit_factor": 2.0,
                "totaal_trades": 20,
            },
            "trend_pullback_exit_reason_summary": {
                "realized_pnl_impact": {
                    "by_exit_reason": {
                        "trend_break": {"total_pnl": -0.10},
                    },
                },
                "exit_health_summary": {
                    "overall": {
                        "by_health_class": {
                            "risk_exit": {
                                "trade_share": 0.8,
                                "total_pnl": -0.10,
                            },
                            "healthy_exit": {
                                "trade_share": 0.2,
                                "total_pnl": 0.02,
                            },
                        },
                    },
                },
            },
        },
        {
            "sample_index": 1,
            "criteria_checks": {"sufficient_trades": True},
            "status": "promoted_to_validation",
            "reason": None,
            "metrics": {
                "expectancy": 0.01,
                "profit_factor": 1.2,
                "totaal_trades": 20,
            },
            "trend_pullback_exit_reason_summary": {
                "realized_pnl_impact": {
                    "by_exit_reason": {
                        "pullback_resolved": {"total_pnl": 0.02},
                    },
                },
                "exit_health_summary": {
                    "overall": {
                        "by_health_class": {
                            "healthy_exit": {
                                "trade_share": 0.9,
                                "total_pnl": 0.02,
                            },
                            "unknown_exit": {
                                "trade_share": 0.1,
                                "total_pnl": 0.0,
                            },
                        },
                    },
                },
            },
        },
    ]

    summary = _sample_diagnostics_summary(sample_diagnostics)

    assert summary["best_sample_index"] == 0
    audit = summary["best_sample_exit_quality_audit"]
    assert audit["advisory_only"] is True
    assert audit["performance_best_sample_index"] == 0
    assert audit["selected_best_sample_index"] == 0
    assert audit["exit_quality_best_sample_index"] == 1
    assert audit["exit_quality_disagreement"] is True
    assert audit["selected_sample_health_score"] == pytest.approx(-0.6)
    assert audit["exit_quality_best_health_score"] == pytest.approx(0.8)
    assert audit["selected_sample_risk_exit_share"] == 0.8
    assert audit["selected_sample_risk_exit_total_pnl"] == -0.10
    assert "differs" in audit["advisory_message"]


def test_trend_pullback_diagnostic_features_match_engine_fold_local_features(
    monkeypatch,
) -> None:
    frame = _trend_pullback_alignment_frame()
    strategy = trend_pullback_v1_strategie(
        ema_fast_window=3,
        ema_slow_window=8,
        entry_k=0.5,
    )
    engine = BacktestEngine(
        "2025-01-01",
        "2025-05-30",
        evaluation_config={
            "mode": "rolling",
            "train_bars": 60,
            "test_bars": 20,
            "step_bars": 20,
        },
    )
    engine._laad_data = lambda asset, interval: frame.copy()

    engine_feature_calls = _capture_engine_plain_feature_calls(monkeypatch)

    engine.run(strategy, ["TEST"], interval="1d")
    report = engine.last_evaluation_report or {}
    trades = report["evaluation_streams"]["oos_trade_events"]
    assert trades, "fixture must produce OOS exits to validate decision alignment"

    diagnostic_features = _trend_pullback_features_by_timestamp(
        engine=engine,
        strategy_callable=strategy,
        candidate={"asset": "TEST", "interval": "1d"},
        evaluation_report=report,
    )

    global_features = build_features_for(strategy._feature_requirements, frame)
    verified_exit_timestamps: set[str] = set()
    verified_fold_starts = 0
    verified_no_global_contamination = 0

    folds = report["folds_by_asset"]["TEST"]
    for fold_index, fold in enumerate(folds):
        test_start, test_end = fold["test"]
        fold_frame = frame.iloc[test_start : test_end + 1].copy()
        engine_features = _captured_features_for_index(
            engine_feature_calls,
            tuple(fold_frame.index),
        )
        assert engine_features is not None

        fold_start_ts = engine._timestamp_to_utc_iso(fold_frame.index[0])
        _assert_diagnostic_row_matches_engine_features(
            diagnostic_features[fold_start_ts],
            engine_features,
            fold_frame.index[0],
        )
        verified_fold_starts += 1

        # Warmup is fold-local: the diagnostic row must preserve the
        # engine's NaN pullback-distance warmup at the start of each
        # test slice instead of borrowing pre-fold history.
        assert math.isnan(float(diagnostic_features[fold_start_ts]["pullback_distance"]))

        global_row = {
            alias: global_features[alias].get(fold_frame.index[0])
            for alias in ("ema_fast", "ema_slow", "pullback_distance")
        }
        if any(
            not _feature_values_equal(
                diagnostic_features[fold_start_ts][alias],
                global_row[alias],
            )
            for alias in ("ema_fast", "ema_slow", "pullback_distance")
        ):
            verified_no_global_contamination += 1

        fold_trade_decisions = [
            pd.Timestamp(trade["exit_decision_timestamp_utc"])
            for trade in trades
            if trade["fold_index"] == fold_index
        ]
        for decision_ts in fold_trade_decisions:
            decision_ts_utc = engine._timestamp_to_utc_iso(decision_ts)
            _assert_diagnostic_row_matches_engine_features(
                diagnostic_features[decision_ts_utc],
                engine_features,
                decision_ts,
            )
            verified_exit_timestamps.add(decision_ts_utc)

    assert verified_fold_starts == len(folds)
    assert verified_no_global_contamination == len(folds)
    assert verified_exit_timestamps == {
        trade["exit_decision_timestamp_utc"]
        for trade in trades
    }

    missing_timestamp_trade = dict(trades[0])
    missing_timestamp_trade["exit_decision_timestamp_utc"] = "2099-01-01T00:00:00+00:00"
    assert _trend_pullback_exit_reason_summary(
        trade_events=[missing_timestamp_trade],
        features_by_timestamp=diagnostic_features,
    )["signal_change_unknown_count"] == 1

def test_trend_break_invalidation_summary_aggregates_trend_break_only() -> None:
    trade_events = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-1",
            "exit_decision_timestamp_utc": "decision-1",
            "exit_timestamp_utc": "exit-1",
            "exit_kind": "signal_change",
            "pnl": -0.10,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-2",
            "exit_decision_timestamp_utc": "decision-2",
            "exit_timestamp_utc": "exit-2",
            "exit_kind": "signal_change",
            "pnl": 0.03,
        },
    ]
    features_by_timestamp = {
        "decision-1": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "decision-2": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    exit_diagnostics = {
        "per_window": [
            {
                "asset": "AMD",
                "fold_index": 0,
                "per_trade": [
                    {
                        "asset": "AMD",
                        "fold_index": 0,
                        "entry_timestamp_utc": "entry-1",
                        "exit_timestamp_utc": "exit-1",
                        "mae": 0.12,
                        "mfe": 0.02,
                        "capture_ratio": -5.0,
                        "holding_bars": 6,
                        "exit_lag_bars": 4,
                    },
                    {
                        "asset": "AMD",
                        "fold_index": 0,
                        "entry_timestamp_utc": "entry-2",
                        "exit_timestamp_utc": "exit-2",
                        "mae": 0.01,
                        "mfe": 0.05,
                        "capture_ratio": 0.6,
                        "holding_bars": 3,
                        "exit_lag_bars": 1,
                    },
                ],
            }
        ]
    }

    assert _trend_break_invalidation_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        exit_diagnostics=exit_diagnostics,
    ) == {
        "trade_count": 1,
        "avg_pnl": -0.1,
        "largest_loss": -0.1,
        "avg_mae": 0.12,
        "avg_mfe": 0.02,
        "avg_capture_ratio": -5.0,
        "avg_holding_bars": 6.0,
        "avg_exit_lag_bars": 4.0,
        "zero_mfe_count": 0,
        "adverse_dominant_count": 1,
    }

def test_trend_break_invalidation_simulation_estimates_rule_impact() -> None:
    trade_events = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-1",
            "exit_decision_timestamp_utc": "decision-1",
            "exit_timestamp_utc": "exit-1",
            "exit_kind": "signal_change",
            "pnl": -0.10,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-2",
            "exit_decision_timestamp_utc": "decision-2",
            "exit_timestamp_utc": "exit-2",
            "exit_kind": "signal_change",
            "pnl": 0.04,
        },
    ]
    features_by_timestamp = {
        "decision-1": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "decision-2": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    exit_diagnostics = {
        "per_window": [
            {
                "per_trade": [
                    {
                        "asset": "AMD",
                        "fold_index": 0,
                        "entry_timestamp_utc": "entry-1",
                        "exit_timestamp_utc": "exit-1",
                        "mae": 0.05,
                        "mfe": 0.0,
                        "holding_bars": 5,
                    },
                    {
                        "asset": "AMD",
                        "fold_index": 0,
                        "entry_timestamp_utc": "entry-2",
                        "exit_timestamp_utc": "exit-2",
                        "mae": 0.03,
                        "mfe": 0.0,
                        "holding_bars": 5,
                    },
                ]
            }
        ]
    }

    summary = _trend_break_invalidation_simulation_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        exit_diagnostics=exit_diagnostics,
    )

    assert summary["matched_trade_count"] == 2
    zero_mfe = summary["rules"]["zero_mfe_holding_ge_3"]
    assert zero_mfe == {
        "affected_trades": 2,
        "affected_trend_break_trades": 1,
        "affected_pullback_resolved_trades": 1,
        "affected_other_trades": 0,
        "trend_break_loss_at_risk": 0.1,
        "pullback_profit_at_risk": 0.04,
        "other_pnl_at_risk": 0.0,
        "net_loss_reduction_upper_bound": 0.060000000000000005,
    }

def test_trend_break_bar_path_simulation_estimates_timed_exit_delta() -> None:
    trade_events = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-1",
            "exit_decision_timestamp_utc": "decision-1",
            "exit_timestamp_utc": "exit-1",
            "exit_kind": "signal_change",
            "side": "long",
            "pnl": -0.10,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-2",
            "exit_decision_timestamp_utc": "decision-2",
            "exit_timestamp_utc": "exit-2",
            "exit_kind": "signal_change",
            "side": "long",
            "pnl": 0.04,
        },
    ]
    features_by_timestamp = {
        "decision-1": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "decision-2": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    bar_return_stream = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "entry-1",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "mid-1",
            "return": -0.03,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "exit-1",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "entry-2",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "mid-2",
            "return": -0.03,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "exit-2",
            "return": 0.0,
        },
    ]

    summary = _trend_break_bar_path_simulation_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        bar_return_stream=bar_return_stream,
    )

    assert summary["rule"] == "mae_gt_2pct_mfe_lt_025pct"
    assert summary["matched_trade_count"] == 2
    assert summary["triggered_trade_count"] == 2
    assert summary["triggered_trend_break_trades"] == 1
    assert summary["triggered_pullback_resolved_trades"] == 1
    assert summary["triggered_other_trades"] == 0
    assert summary["avoided_loss"] == pytest.approx(0.07)
    assert summary["sacrificed_profit"] == pytest.approx(0.07)
    assert summary["other_pnl_delta"] == pytest.approx(0.0)
    assert summary["net_pnl_delta"] == pytest.approx(0.0)
    assert summary["avg_bars_to_trigger"] == pytest.approx(1.0)

def test_trend_break_bar_path_threshold_comparison_ranks_multiple_rules() -> None:
    trade_events = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-1",
            "exit_decision_timestamp_utc": "decision-1",
            "exit_timestamp_utc": "exit-1",
            "exit_kind": "signal_change",
            "side": "long",
            "pnl": -0.10,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "entry_timestamp_utc": "entry-2",
            "exit_decision_timestamp_utc": "decision-2",
            "exit_timestamp_utc": "exit-2",
            "exit_kind": "signal_change",
            "side": "long",
            "pnl": 0.04,
        },
    ]
    features_by_timestamp = {
        "decision-1": {
            "pullback_distance": -1.0,
            "ema_fast": 99.0,
            "ema_slow": 100.0,
        },
        "decision-2": {
            "pullback_distance": 1.0,
            "ema_fast": 101.0,
            "ema_slow": 100.0,
        },
    }
    bar_return_stream = [
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "entry-1",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "mid-1",
            "return": -0.025,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "mid-1b",
            "return": -0.01,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "exit-1",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "entry-2",
            "return": 0.0,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "mid-2",
            "return": -0.025,
        },
        {
            "asset": "AMD",
            "fold_index": 0,
            "timestamp_utc": "exit-2",
            "return": 0.0,
        },
    ]

    summary = _trend_break_bar_path_threshold_comparison_summary(
        trade_events=trade_events,
        features_by_timestamp=features_by_timestamp,
        bar_return_stream=bar_return_stream,
    )

    assert summary["matched_trade_count"] == 2
    rules = summary["rules"]

    loose = rules["mae_gt_2pct_mfe_lt_025pct"]
    assert loose["triggered_trade_count"] == 2
    assert loose["triggered_trend_break_trades"] == 1
    assert loose["triggered_pullback_resolved_trades"] == 1
    assert loose["net_pnl_delta"] == pytest.approx(0.01)

    strict = rules["mae_gt_3pct_mfe_lt_025pct"]
    assert strict["triggered_trade_count"] == 1
    assert strict["triggered_trend_break_trades"] == 1
    assert strict["triggered_pullback_resolved_trades"] == 0
    assert strict["net_pnl_delta"] > loose["net_pnl_delta"]

    zero_mfe = rules["mae_gt_3pct_zero_mfe"]
    assert zero_mfe["triggered_trade_count"] == 1
    assert zero_mfe["triggered_trend_break_trades"] == 1
