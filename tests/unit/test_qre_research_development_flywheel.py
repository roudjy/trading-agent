from __future__ import annotations

import json
from pathlib import Path

from research import qre_daily_status_digest as digest
from research import qre_research_development_flywheel as flywheel
from tests.unit.test_qre_autonomous_market_research_loop import _controlled_packet


def _build_runner(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    return (
        0,
        json.dumps(
            {
                "build_request_consumed": True,
                "build_started": True,
                "branch_created": True,
                "code_changed": True,
                "tests_run": True,
                "pr_created": True,
                "safe_for_auto_merge": True,
                "pr_metadata": {
                    "number": 524,
                    "branch": "feat/qre-add-cache-only-metric-path",
                    "title": "feat: add cache only metric path",
                    "ci_status": "green",
                    "mergeable": True,
                    "changed_files": [
                        "research/qre_cache_only_metric_path.py",
                        "tests/unit/test_qre_cache_only_metric_path.py",
                    ],
                },
            }
        ),
        "",
    )


def _merge_runner(cmd: list[str]) -> tuple[int, str, str]:
    if cmd[:3] == ["gh", "pr", "view"]:
        return (
            0,
            json.dumps(
                {
                    "number": 524,
                    "title": "feat: add cache only metric path",
                    "state": "OPEN",
                    "mergeCommit": None,
                    "headRefName": "feat/qre-add-cache-only-metric-path",
                    "baseRefName": "main",
                    "statusCheckRollup": [
                        {"name": "lint/ruff", "status": "COMPLETED", "conclusion": "SUCCESS"},
                        {"name": "unit smoke + unit", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ],
                    "changedFiles": 2,
                    "url": "https://github.com/roudjy/trading-agent/pull/524",
                    "mergeable": "MERGEABLE",
                }
            ),
            "",
        )
    return (0, "merged", "")


def _runtime_runner(cmd: list[str]) -> tuple[int, str, str]:
    return (0, "ok", "")


def test_flywheel_no_backend_fails_closed_at_build_consumption(tmp_path: Path) -> None:
    packet = flywheel.run_flywheel(
        output_dir=tmp_path / "flywheel",
        max_cycles=3,
        max_builds=1,
        write=True,
        env={},
        controlled_packet=_controlled_packet(),
    )

    assert packet["states"]["build_request_created"] is True
    assert packet["states"]["build_request_consumed"] is False
    assert packet["summary"]["build_requests_created"] == 1
    assert packet["summary"]["build_requests_consumed"] == 0
    assert "no_safe_build_backend_configured" in packet["summary"]["manual_governance_blockers"]
    assert packet["summary"]["protected_outputs_mutated"] is False


def test_flywheel_full_mocked_research_build_merge_continuation_path(tmp_path: Path) -> None:
    packet = flywheel.run_flywheel(
        output_dir=tmp_path / "flywheel",
        max_cycles=3,
        max_builds=1,
        write=True,
        env={
            "QRE_BUILD_BACKEND": "codex_cli",
            "QRE_BUILD_COMMAND": "codex exec %QRE_BUILD_REQUEST_PATH%",
            "QRE_AUTO_PR": "true",
            "QRE_AUTO_MERGE_GREEN": "true",
            "QRE_RUNTIME_UPDATE": "true",
        },
        build_command_runner=_build_runner,
        merge_command_runner=_merge_runner,
        runtime_command_runner=_runtime_runner,
        controlled_packet=_controlled_packet(),
    )

    assert packet["states"] == {
        "build_request_created": True,
        "build_request_consumed": True,
        "build_started": True,
        "branch_created": True,
        "code_changed": True,
        "tests_run": True,
        "pr_created": True,
        "ci_observed": True,
        "pr_green": True,
        "pr_auto_merged": True,
        "runtime_updated": True,
        "research_continuation_started": True,
        "research_blocked": False,
        "unsafe_action_blocked": False,
    }
    assert packet["summary"]["prs_merged"] == 1
    assert packet["summary"]["research_continuations_started"] == 1
    assert packet["summary"]["execution_allowed"] is False
    assert packet["summary"]["paper_shadow_live_allowed"] is False
    assert packet["summary"]["broker_risk_allowed"] is False


def test_flywheel_respects_zero_max_builds(tmp_path: Path) -> None:
    packet = flywheel.run_flywheel(
        output_dir=tmp_path / "flywheel",
        max_cycles=2,
        max_builds=0,
        write=True,
        controlled_packet=_controlled_packet(),
    )

    assert packet["summary"]["research_cycles_completed"] == 2
    assert packet["states"]["build_request_created"] is True
    assert packet["states"]["build_request_consumed"] is False


def test_daily_digest_includes_flywheel_state(tmp_path: Path) -> None:
    flywheel.run_flywheel(
        output_dir=tmp_path / "flywheel",
        max_cycles=3,
        max_builds=1,
        write=True,
        env={},
        controlled_packet=_controlled_packet(),
    )
    packet = digest.run_daily_status_digest(
        loop_latest_path=Path("logs/qre_autonomous_market_research_loop/latest.json"),
        build_request_latest_path=tmp_path / "missing" / "latest_build_request.json",
        build_consumer_latest_path=tmp_path / "missing" / "consumer_latest.json",
        backend_results_dir=tmp_path / "missing" / "backend_results",
        pr_auto_merge_latest_path=tmp_path / "missing" / "pr_gate_latest.json",
        runtime_continuation_latest_path=tmp_path / "missing" / "runtime_latest.json",
        flywheel_latest_path=tmp_path / "flywheel" / "latest.json",
        output_dir=tmp_path / "daily",
        write=True,
    )
    text = (tmp_path / "daily" / "daily_status.md").read_text(encoding="utf-8")

    assert packet["summary"]["build_requests_consumed"] == 0
    assert packet["summary"]["prs_opened"] == 0
    assert "Build requests consumed:" in text
    assert "PRs merged:" in text
    assert "Manual governance blockers:" in text
