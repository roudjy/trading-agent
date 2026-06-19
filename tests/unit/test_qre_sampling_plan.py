from __future__ import annotations

from pathlib import Path

from research import qre_sampling_plan as sampling


def _windows() -> list[dict[str, object]]:
    return [
        {
            "window_id": "window_01",
            "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-08"},
            "oos_window": {"start": "2026-04-30", "end": "2026-05-08"},
            "role": "oos",
            "regime_label": "trend",
            "locked": True,
        },
        {
            "window_id": "window_02",
            "bounded_input_window": {"start": "2026-05-11", "end": "2026-06-08"},
            "oos_window": {"start": "2026-05-31", "end": "2026-06-08"},
            "role": "oos",
            "regime_label": "high_volatility",
            "locked": True,
        },
    ]


def test_sampling_plan_is_deterministic_and_context_only() -> None:
    first = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_lineage", "structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        window_definitions=_windows(),
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )
    second = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_lineage", "structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        window_definitions=_windows(),
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )

    assert first == second
    assert first["status"] == "sampling_plan_ready_context_only"
    assert first["authority"]["non_authoritative"] is True
    assert first["authority"]["can_authorize_execution"] is False
    assert first["authority"]["can_clear_evidence_blockers"] is False
    assert first["authority"]["can_promote_candidate"] is False
    assert sampling.validate_sampling_plan(first)["valid"] is True


def test_sampling_plan_blocks_outcome_based_selection() -> None:
    plan = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        window_definitions=_windows(),
        preregistration_timestamp="2026-06-19T10:00:00Z",
        selection_policy="choose highest sharpe windows",
    )

    assert plan["status"] == "blocked_outcome_based_selection"
    assert "outcome_based_selection_detected" in plan["blocked_reasons"]


def test_sampling_plan_blocks_invalid_and_overlapping_windows() -> None:
    plan = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        window_definitions=[
            {
                "window_id": "window_01",
                "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-08"},
                "oos_window": {"start": "2026-04-30", "end": "2026-05-08"},
                "role": "oos",
                "locked": True,
            },
            {
                "window_id": "window_02",
                "bounded_input_window": {"start": "2026-05-01", "end": "2026-06-08"},
                "oos_window": {"start": "2026-05-07", "end": "2026-05-20"},
                "role": "oos",
                "locked": True,
            },
        ],
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )

    assert plan["status"] == "blocked_overlapping_windows"
    assert any(reason.startswith("overlapping_oos_windows:") for reason in plan["blocked_reasons"])


def test_sampling_plan_requires_null_control_and_preserves_failed_windows() -> None:
    blocked = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_oos"],
        null_control_definitions=[],
        window_definitions=_windows(),
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )
    assert blocked["status"] == "blocked_missing_null_control"

    plan = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_oos"],
        null_control_definitions=[{"control_id": "null_daily_holdout", "required": True}],
        known_previous_failed_windows=[{"window_id": "window_00", "failure_class": "non_positive_oos_trade_count"}],
        window_definitions=_windows(),
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )

    assert plan["known_previous_failed_windows"][0]["window_id"] == "window_00"
    assert plan["window_definitions"][0]["window_id"] == "window_01"


def test_sampling_plan_can_derive_non_overlapping_windows() -> None:
    windows = sampling.derive_preregistered_windows(
        trading_dates=[
            "2026-04-08",
            "2026-04-09",
            "2026-04-10",
            "2026-04-13",
            "2026-04-14",
            "2026-04-15",
            "2026-04-16",
            "2026-04-17",
            "2026-04-20",
            "2026-04-21",
            "2026-04-22",
            "2026-04-23",
            "2026-04-24",
            "2026-04-27",
            "2026-04-28",
            "2026-04-29",
            "2026-04-30",
            "2026-05-01",
            "2026-05-04",
            "2026-05-05",
        ],
        window_count=2,
        minimum_window_length=10,
        minimum_warmup_period=5,
        regime_labels=["trend", "range"],
    )

    assert windows[0]["window_id"] == "window_01"
    assert windows[1]["regime_label"] == "range"
    assert windows[0]["oos_window"]["end"] < windows[1]["oos_window"]["start"]


def test_sampling_plan_core_has_no_symbol_hardcoding() -> None:
    source = Path("research/qre_sampling_plan.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
