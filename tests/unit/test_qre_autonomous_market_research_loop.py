from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_autonomous_market_research_loop as loop
from research.qre_controlled_research_run import CONTROLLED_ASSETS


def _controlled_packet(next_action: str = "add_cache_only_metric_path") -> dict:
    run_group_id = "controlled-research-test"
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_research_run",
        "run_group_id": run_group_id,
        "summary": {
            "loop_count": 2,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "validation_executed": False,
            "execution_performed": False,
            "paper_shadow_live_allowed": False,
            "research_latest_mutated": False,
            "strategy_matrix_mutated": False,
            "final_recommendation": next_action,
        },
        "runs": [
            {
                "run_id": f"{run_group_id}__loop__2",
                "hypothesis": {
                    "statement": "controlled hypothesis",
                    "not_alpha_claim": True,
                    "not_trade_signal": True,
                },
                "preset_selection": {
                    "preset_id": "trend_continuation_daily_v1",
                    "timeframe": "1d",
                    "preset_mutated": False,
                },
                "controlled_campaign_intent": {
                    "campaign_intent_id": "campaign-intent",
                    "campaign_launcher_called": False,
                    "campaign_registry_mutated": False,
                    "candidate_promotion_allowed": False,
                    "controlled_universe": list(CONTROLLED_ASSETS),
                },
                "metric_evidence": {
                    "metric_mode": "bounded_metric_evidence",
                    "true_metrics_available": False,
                    "bounded_metric_evidence_available": True,
                    "per_asset": [
                        {
                            "symbol": symbol,
                            "metric_readiness": "blocked",
                            "blocker": "safe_metric_runner_missing_or_cache_unavailable",
                            "next_action": next_action,
                        }
                        for symbol in CONTROLLED_ASSETS
                    ],
                },
                "analysis": {
                    "analysis_id": "analysis-2",
                    "analysis_statement": "metrics blocked",
                    "metric_evidence_mode": "bounded_metric_evidence",
                    "true_metrics_available": False,
                    "content_blockers": ["safe_metric_runner_missing_or_cache_unavailable"],
                    "safety_blockers": [],
                },
                "learning_feedback": {
                    "learning_feedback_id": "learning-2",
                    "learning_statement": "do not rotate assets",
                },
                "next_hypothesis_or_action": {
                    "recommended_action": next_action,
                    "operator_command_after_next_pr": (
                        "python -m research.qre_controlled_research_run --write --loops 2"
                    ),
                },
            }
        ],
    }


def test_controller_can_run_bounded_max_cycles_and_preserve_full_flow() -> None:
    packet = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet(),
        max_cycles=3,
    )

    assert packet["summary"]["cycle_count"] == 3
    assert packet["summary"]["market_intake_cycle_count"] == 3
    assert packet["summary"]["controlled_research_inner_loop_count"] == 6
    cycle = packet["cycles"][0]
    assert cycle["flow"] == [
        "market_intake",
        "market_analysis",
        "hypothesis_generation",
        "preset_selection",
        "controlled_campaign_intent",
        "metric_evidence",
        "result_analysis",
        "learning_feedback",
        "next_market_intake_seed",
        "next_action",
    ]
    assert cycle["safety"]["paper_shadow_live_allowed"] is False
    assert cycle["safety"]["broker_risk_allowed"] is False
    assert cycle["safety"]["execution_allowed"] is False
    assert cycle["safety"]["run_research_called"] is False
    assert cycle["safety"]["campaign_launcher_called"] is False


def test_next_cycle_consumes_prior_next_market_intake_seed() -> None:
    packet = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet(),
        max_cycles=2,
    )
    first, second = packet["cycles"]

    assert second["market_intake"]["source"] == "previous_learning_seed"
    assert second["market_intake"]["previous_seed_id"] == first["next_market_intake_seed"]["seed_id"]
    assert "infrastructure/metric evidence" in second["market_intake"]["statement"]


def test_controller_creates_build_request_without_manual_copy_paste(tmp_path: Path) -> None:
    packet = loop.run_autonomous_loop(
        controlled_packet=_controlled_packet(),
        output_dir=tmp_path,
        max_cycles=3,
        write=True,
    )

    paths = packet["_artifact_paths"]["build_request"]
    assert paths["request_id"].startswith("build-request-")
    latest = json.loads((tmp_path / "latest_build_request.json").read_text(encoding="utf-8"))
    assert latest["next_action"] == "add_cache_only_metric_path"
    assert latest["build_executed_by_this_controller"] is False
    assert (tmp_path / "operator_summary.md").exists()
    assert (tmp_path / "latest.json").exists()
    assert len(list((tmp_path / "runs").glob("*.json"))) == 3


def test_until_build_request_stops_after_first_code_required_action() -> None:
    packet = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet(),
        max_cycles=40,
        until_build_request=True,
    )

    assert packet["summary"]["cycle_count"] == 1
    assert packet["summary"]["build_request_required_count"] == 1


def test_can_model_forty_cycles_without_infinite_loop() -> None:
    packet = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet(),
        max_cycles=40,
    )

    assert packet["summary"]["cycle_count"] == 40
    assert packet["cycles"][-1]["cycle_index"] == 40


def test_unsafe_action_is_blocked_and_unknown_fails_closed() -> None:
    unsafe = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet("enable_paper_runtime"),
        max_cycles=1,
    )
    unknown = loop.build_autonomous_loop_packet(
        controlled_packet=_controlled_packet("invent_future_action"),
        max_cycles=1,
    )

    assert unsafe["cycles"][0]["next_action"]["classification"]["action_class"] == "blocked"
    assert unsafe["summary"]["unsafe_actions_blocked"] == 1
    assert unknown["cycles"][0]["next_action"]["classification"]["action_class"] == "unknown"
    assert unknown["summary"]["unknown_actions"] == 1


def test_invalid_cycle_count_rejected() -> None:
    with pytest.raises(loop.AutonomousMarketResearchLoopError, match="between 1 and 1000"):
        loop.build_autonomous_loop_packet(controlled_packet=_controlled_packet(), max_cycles=0)


def test_report_only_rewrites_summary_from_existing_latest(tmp_path: Path) -> None:
    loop.run_autonomous_loop(
        controlled_packet=_controlled_packet(),
        output_dir=tmp_path,
        max_cycles=1,
        write=True,
    )

    packet = loop.run_autonomous_loop(output_dir=tmp_path, write=True, report_only=True)

    assert packet["summary"]["cycle_count"] == 1
    assert "# QRE Autonomous Market-Research Loop" in (
        tmp_path / "operator_summary.md"
    ).read_text(encoding="utf-8")

