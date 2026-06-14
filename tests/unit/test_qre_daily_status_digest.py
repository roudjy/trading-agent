from __future__ import annotations

import json
from pathlib import Path

from research import qre_daily_status_digest as digest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_loop_latest(root: Path, *, protected_outputs_mutated: bool = False) -> Path:
    loop_dir = root / "loop"
    latest_path = loop_dir / "latest.json"
    _write_json(
        latest_path,
        {
            "schema_version": "1.0",
            "report_kind": "qre_autonomous_market_research_loop",
            "summary": {
                "controlled_research_inner_loop_count": 2,
                "market_intake_cycle_count": 1,
                "unsafe_actions_blocked": 0,
                "protected_outputs_mutated": protected_outputs_mutated,
            },
            "cycles": [
                {
                    "cycle_id": "cycle-1",
                    "market_intake": {"universe": ["AAPL", "MSFT"]},
                    "hypothesis_generation": {"statement": "test hypothesis"},
                    "preset_selection": {"preset_id": "trend_continuation_daily_v1"},
                    "metric_evidence": {"metric_mode": "bounded_metric_evidence"},
                    "result_analysis": {"content_blockers": ["safe_metric_runner_missing_or_cache_unavailable"]},
                    "next_action": {"recommended_action": "add_cache_only_metric_path"},
                }
            ],
        },
    )
    return latest_path


def _run_digest(root: Path, **overrides) -> dict:
    loop_latest_path = overrides.pop("loop_latest_path", None) or _write_loop_latest(root)
    kwargs = {
        "loop_latest_path": loop_latest_path,
        "build_request_latest_path": root / "loop" / "latest_build_request.json",
        "build_consumer_latest_path": root / "consumer" / "latest.json",
        "backend_results_dir": root / "consumer" / "backend_results",
        "pr_auto_merge_latest_path": root / "pr_gate" / "latest.json",
        "runtime_continuation_latest_path": root / "runtime" / "latest.json",
        "flywheel_latest_path": root / "flywheel" / "latest.json",
        "output_dir": root / "daily",
        "write": True,
    }
    kwargs.update(overrides)
    return digest.run_daily_status_digest(**kwargs)


def test_daily_digest_summarizes_many_cycles_and_build_lane(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path)
    _write_json(
        tmp_path / "loop" / "build_requests" / "build-request-1.json",
        {
            "request_id": "build-request-1",
            "next_action": "add_cache_only_metric_path",
            "safe_for_ade_build": True,
        },
    )

    packet = digest.run_daily_status_digest(
        loop_latest_path=loop_latest_path,
        build_request_latest_path=tmp_path / "loop" / "latest_build_request.json",
        build_consumer_latest_path=tmp_path / "consumer" / "latest.json",
        backend_results_dir=tmp_path / "consumer" / "backend_results",
        pr_auto_merge_latest_path=tmp_path / "pr_gate" / "latest.json",
        runtime_continuation_latest_path=tmp_path / "runtime" / "latest.json",
        flywheel_latest_path=tmp_path / "flywheel" / "latest.json",
        output_dir=tmp_path / "daily",
        write=True,
    )

    assert packet["summary"]["autonomous_cycles"] == 1
    assert packet["summary"]["market_intake_cycles"] == 1
    assert packet["summary"]["controlled_research_inner_loops"] == 2
    assert packet["summary"]["build_requests_created"] == 1
    assert packet["summary"]["build_requests_pending"] == 1
    assert packet["summary"]["trading_status"] == "disabled"
    assert packet["safety"]["paper_shadow_live_allowed"] is False
    assert packet["safety"]["broker_risk_allowed"] is False
    assert packet["safety"]["execution_allowed"] is False

    daily = (tmp_path / "daily" / "daily_status.md").read_text(encoding="utf-8")
    assert "# QRE Daily Status" in daily
    assert "Research intelligence progress:" in daily
    assert "ADE/build progress:" in daily
    assert "Flywheel progress:" in daily
    assert "Artifact sources used:" in daily
    assert "Latest recommendation: add_cache_only_metric_path" in daily
    assert "The system does not rotate assets" in daily
    assert (tmp_path / "daily" / "scheduler_setup.md").exists()


def test_daily_digest_recognizes_merged_build_result(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path)
    request_id = "build-request-1"
    _write_json(
        tmp_path / "loop" / "build_requests" / f"{request_id}.json",
        {"request_id": request_id, "next_action": "add_cache_only_metric_path", "safe_for_ade_build": True},
    )
    results_dir = tmp_path / "loop" / "build_results"
    results_dir.mkdir()
    (results_dir / f"{request_id}.json").write_text(
        json.dumps(
            {
                "request_id": request_id,
                "pr_number": 524,
                "merge_commit": "abc123",
                "status": "merged",
                "created_at_utc": "2026-06-13T00:00:00Z",
                "updated_main_commit": "abc123",
                "post_merge_research_required": True,
                "blocker_to_check": "safe_metric_runner_missing_or_cache_unavailable",
            }
        ),
        encoding="utf-8",
    )

    packet = digest.build_daily_status_packet(
        loop_latest_path=loop_latest_path,
        build_request_latest_path=tmp_path / "loop" / "latest_build_request.json",
        build_consumer_latest_path=tmp_path / "consumer" / "latest.json",
        backend_results_dir=tmp_path / "consumer" / "backend_results",
        pr_auto_merge_latest_path=tmp_path / "pr_gate" / "latest.json",
        runtime_continuation_latest_path=tmp_path / "runtime" / "latest.json",
        flywheel_latest_path=tmp_path / "flywheel" / "latest.json",
    )

    assert packet["summary"]["build_requests_pending"] == 0
    assert packet["summary"]["build_requests_completed_or_merged"] == 1
    assert packet["next_system_action"] == "Continue bounded autonomous market-research cycles."


def test_digest_reads_build_consumer_latest_and_counts_consumed_build_request(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_request_consumed": True,
            "pr_created": False,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 1
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["build_request_consumed"] == "yes"


def test_digest_reads_backend_result_and_counts_pr_opened(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "backend_results" / "build-request-1.json",
        {
            "created_at_utc": "2026-06-14T15:34:41Z",
            "build_request_consumed": True,
            "pr_created": True,
            "pr_number": 527,
            "pr_url": "https://github.com/roudjy/trading-agent/pull/527",
            "safe_for_auto_merge": True,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 1
    assert packet["summary"]["prs_opened"] == 1
    assert packet["summary"]["flywheel_progress"]["pr_opened"] == "#527"


def test_digest_reads_pr_gate_latest_and_counts_pr_green_and_merged(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "pr_gate" / "latest.json",
        {
            "pr_number": 527,
            "pr_green": True,
            "pr_auto_merged": True,
            "auto_merge_allowed": True,
            "blocked_reasons": [],
            "manual_governance_required": False,
            "live_pr_status_queried": True,
            "ci_source": "live_gh_pr_view",
            "live_check_summary": {"success": 2, "failed": 0, "pending": 0},
            "merge_result": {"returncode": 0, "stdout": "merged", "stderr": ""},
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["prs_green"] == 1
    assert packet["summary"]["prs_merged"] == 1
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["pr_green"] == "yes"
    assert packet["summary"]["flywheel_progress"]["pr_merged"] == "yes"


def test_digest_reads_runtime_latest_and_counts_update_and_continuation(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "runtime" / "latest.json",
        {
            "runtime_updated": True,
            "research_continuation_started": True,
            "research_cycles_started": 3,
            "blocked_reasons": [],
            "final_recommendation": "research_continuation_started",
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["runtime_updates_completed"] == 1
    assert packet["summary"]["research_continuations_started"] == 1
    assert packet["summary"]["latest_recommendation"] == "research_continuation_started"
    assert packet["summary"]["flywheel_progress"]["runtime_updated"] == "yes"
    assert packet["summary"]["flywheel_progress"]["research_continuation_started"] == "yes"


def test_stale_no_safe_build_backend_configured_is_suppressed_after_successful_backend_result(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_backend_available": False,
            "build_request_consumed": False,
            "pr_created": False,
            "blocked_reason": "no_safe_build_backend_configured",
            "missing_capability": "safe_build_backend",
            "protected_outputs_mutated": False,
        },
    )
    _write_json(
        tmp_path / "consumer" / "backend_results" / "build-request-1.json",
        {
            "created_at_utc": "2026-06-14T15:34:41Z",
            "build_backend_available": True,
            "build_request_consumed": True,
            "pr_created": True,
            "pr_number": 527,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["prs_opened"] == 1


def test_active_blockers_are_still_shown_when_latest_artifact_has_real_blocked_reason(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_request_consumed": False,
            "pr_created": False,
            "blocked_reason": "build_backend_failed",
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["manual_governance_blockers"] == ["build_backend_failed"]
    assert packet["summary"]["latest_blocker"] == "build_backend_failed"


def test_protected_artifact_mutation_remains_surfaced_if_present(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path, protected_outputs_mutated=True)

    packet = _run_digest(tmp_path, loop_latest_path=loop_latest_path)

    assert packet["summary"]["protected_artifact_mutation"] == "detected"


def test_trading_status_remains_disabled(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    assert packet["summary"]["trading_status"] == "disabled"
    assert packet["safety"]["paper_shadow_live_allowed"] is False
    assert packet["safety"]["broker_risk_allowed"] is False
    assert packet["safety"]["execution_allowed"] is False


def test_missing_artifacts_fail_gracefully_with_unknown_pending_status(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 0
    assert packet["summary"]["prs_opened"] == 0
    assert packet["summary"]["prs_green"] == 0
    assert packet["summary"]["prs_merged"] == 0
    assert packet["summary"]["runtime_updates_completed"] == 0
    assert packet["summary"]["research_continuations_started"] == 0
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["build_request_consumed"] == "unknown"
    assert packet["summary"]["flywheel_progress"]["pr_opened"] == "unknown"

