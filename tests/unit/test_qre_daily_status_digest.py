from __future__ import annotations

import json
from pathlib import Path

from research import qre_autonomous_market_research_loop as loop
from research import qre_daily_status_digest as digest
from tests.unit.test_qre_autonomous_market_research_loop import _controlled_packet


def test_daily_digest_summarizes_many_cycles_and_build_lane(tmp_path: Path) -> None:
    loop.run_autonomous_loop(
        controlled_packet=_controlled_packet(),
        output_dir=tmp_path / "loop",
        max_cycles=40,
        write=True,
    )

    packet = digest.run_daily_status_digest(
        loop_latest_path=tmp_path / "loop" / "latest.json",
        output_dir=tmp_path / "daily",
        write=True,
    )

    assert packet["summary"]["autonomous_cycles"] == 40
    assert packet["summary"]["market_intake_cycles"] == 40
    assert packet["summary"]["controlled_research_inner_loops"] == 80
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
    assert "Latest recommendation: add_cache_only_metric_path" in daily
    assert "The system does not rotate assets" in daily
    assert (tmp_path / "daily" / "scheduler_setup.md").exists()


def test_daily_digest_recognizes_merged_build_result(tmp_path: Path) -> None:
    loop_packet = loop.run_autonomous_loop(
        controlled_packet=_controlled_packet(),
        output_dir=tmp_path / "loop",
        max_cycles=1,
        write=True,
    )
    request_id = loop_packet["_artifact_paths"]["build_request"]["request_id"]
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

    packet = digest.build_daily_status_packet(loop_latest_path=tmp_path / "loop" / "latest.json")

    assert packet["summary"]["build_requests_pending"] == 0
    assert packet["summary"]["build_requests_completed_or_merged"] == 1
    assert packet["next_system_action"] == "Continue bounded autonomous market-research cycles."

