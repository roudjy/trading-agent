from __future__ import annotations

from pathlib import Path

from research import qre_failure_to_action_mapper as mapper


def test_non_positive_oos_trade_count_maps_to_next_window_when_available() -> None:
    report = mapper.map_failure_to_action(
        failure_class="non_positive_oos_trade_count",
        remaining_preregistered_window_count=2,
    )

    assert report["recommended_action"] == "run_next_preregistered_window"
    assert report["action_authority"] == "approval_required"
    assert report["can_execute"] is False
    assert mapper.validate_failure_action_mapping(report)["valid"] is True


def test_final_failed_window_maps_to_hypothesis_rejection() -> None:
    report = mapper.map_failure_to_action(
        failure_class="non_positive_oos_trade_count",
        remaining_preregistered_window_count=0,
        remaining_preregistered_regime_count=0,
    )

    assert report["recommended_action"] == "reject_hypothesis"
    assert "no_remaining_preregistered_windows" in report["reason_codes"]


def test_no_action_clears_blockers_executes_or_tunes() -> None:
    report = mapper.map_failure_to_action(failure_class="missing_oos_metrics")

    assert report["can_execute"] is False
    assert report["can_mutate_queue"] is False
    assert report["can_clear_blocker"] is False
    assert report["can_redefine_window"] is False
    assert report["can_tune_strategy"] is False


def test_unknown_failure_fails_closed() -> None:
    report = mapper.map_failure_to_action(failure_class="mystery_failure")

    assert report["recommended_action"] == "route_to_operator_review"
    assert report["reason_codes"] == ["unknown_failure_fail_closed"]


def test_mapping_is_deterministic() -> None:
    first = mapper.map_failure_to_action(
        failure_class="all_preregistered_windows_failed",
    )
    second = mapper.map_failure_to_action(
        failure_class="all_preregistered_windows_failed",
    )

    assert first == second
    assert first["hash"] == mapper.compute_failure_action_hash(first)


def test_mapper_core_has_no_symbol_hardcoding() -> None:
    source = Path("research/qre_failure_to_action_mapper.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
