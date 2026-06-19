from __future__ import annotations

from pathlib import Path

from research import qre_null_control_falsification_suite as suite
from research import qre_sampling_plan as sampling


def _sampling_plan(**overrides: object) -> dict[str, object]:
    payload = sampling.build_preregistered_sampling_plan(
        hypothesis_ref="trend_pullback_behavior_v1",
        behavior_id="trend_pullback",
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_lineage", "structured_oos"],
        null_control_definitions=[
            {
                "control_id": "buy_and_hold_baseline",
                "control_family": "buy_and_hold",
                "required_for_evidence_complete": True,
            },
            {
                "control_id": "shuffled_signal_surrogate",
                "control_family": "shuffled_signal",
                "required_for_evidence_complete": True,
            },
        ],
        window_definitions=[
            {
                "window_id": "window_01",
                "bounded_input_window": {"start": "2026-04-08", "end": "2026-05-07"},
                "oos_window": {"start": "2026-04-29", "end": "2026-05-07"},
                "role": "oos",
                "regime_label": "trend",
                "locked": True,
            }
        ],
        preregistration_timestamp="2026-06-19T10:00:00Z",
    )
    payload.update(overrides)
    return payload


def test_suite_is_deterministic_and_locked() -> None:
    first = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )
    second = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )

    assert first == second
    assert first["status"] == "suite_ready_preregistered_context"
    assert all(row["locked"] is True for row in first["control_definitions"])
    assert first["hash"] == suite.compute_suite_hash(first)


def test_unlocked_or_post_hoc_controls_are_blocked() -> None:
    report = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan(
            null_control_definitions=[
                {
                    "control_id": "buy_and_hold_baseline",
                    "control_family": "buy_and_hold",
                    "locked": False,
                    "selection_policy": "best_control_after_profit_review",
                }
            ]
        )
    )

    assert report["status"] == "blocked_post_hoc_control_selection"
    assert "control_not_locked:buy_and_hold_baseline" in report["blocked_reasons"]
    assert "post_hoc_control_selection:buy_and_hold_baseline" in report["blocked_reasons"]


def test_evaluation_fails_closed_when_controls_missing() -> None:
    report = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )
    evaluated = suite.evaluate_null_control_suite(
        report,
        candidate_context={"campaign_id": "camp-001", "sampling_plan_id": "plan-001"},
        control_results=[],
    )

    assert evaluated["evaluation"]["status"] == "controls_incomplete"
    assert evaluated["evaluation"]["missing_control_ids"] == [
        "buy_and_hold_baseline",
        "shuffled_signal_surrogate",
    ]
    assert evaluated["evaluation"]["recommended_next_action"] == "materialize_missing_preregistered_controls"


def test_evaluation_marks_failures_and_passes_without_promotion() -> None:
    report = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )
    failed = suite.evaluate_null_control_suite(
        report,
        control_results=[
            {"control_id": "buy_and_hold_baseline", "result_status": "completed", "passed": True},
            {
                "control_id": "shuffled_signal_surrogate",
                "result_status": "completed",
                "passed": False,
                "failure_reason": "candidate_not_separated_from_shuffled_signal",
            },
        ],
    )
    passed = suite.evaluate_null_control_suite(
        report,
        control_results=[
            {"control_id": "buy_and_hold_baseline", "result_status": "completed", "passed": True},
            {"control_id": "shuffled_signal_surrogate", "result_status": "completed", "passed": True},
        ],
    )

    assert failed["evaluation"]["status"] == "controls_failed"
    assert failed["evaluation"]["failed_control_ids"] == ["shuffled_signal_surrogate"]
    assert passed["evaluation"]["status"] == "controls_passed_context_only"
    assert passed["authority"]["can_promote_candidate"] is False


def test_write_outputs_and_core_module_have_no_symbol_hardcoding(tmp_path: Path) -> None:
    report = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )
    paths = suite.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_null_control_falsification_suite/latest.json"
    source = Path("research/qre_null_control_falsification_suite.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source


def test_status_reader_fails_closed_then_round_trips_ready(tmp_path: Path) -> None:
    missing = suite.read_null_control_suite_status(repo_root=tmp_path)
    assert missing["status"] == "missing_null_control_suite"
    assert missing["null_control_suite_ready"] is False

    report = suite.build_preregistered_null_control_suite(
        sampling_plan_payload=_sampling_plan()
    )
    suite.write_outputs(report, repo_root=tmp_path)

    ready = suite.read_null_control_suite_status(repo_root=tmp_path)
    assert ready["status"] == "ready"
    assert ready["null_control_suite_ready"] is True
    assert ready["path"] == "logs/qre_null_control_falsification_suite/latest.json"
