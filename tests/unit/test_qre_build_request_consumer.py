from __future__ import annotations

import json
from pathlib import Path

from research import qre_build_request_consumer as consumer
from research.qre_build_request_writer import build_request_packet, write_build_request
from research.qre_next_action_classifier import classify_next_action


def _build_request(tmp_path: Path) -> Path:
    cycle = {
        "cycle_id": "cycle-1",
        "source_research_run_id": "research-run-2",
        "source_research_run_group_id": "research-group",
        "next_market_intake_seed": {"seed_id": "seed-1"},
        "result_analysis": {"content_blockers": ["safe_metric_runner_missing_or_cache_unavailable"]},
    }
    packet = build_request_packet(
        source_cycle=cycle,
        classification=classify_next_action("add_cache_only_metric_path"),
        created_at_utc="2026-06-13T00:00:00Z",
    )
    write_build_request(packet, output_dir=tmp_path)
    return tmp_path / "latest_build_request.json"


def test_consumer_reads_latest_build_request_and_fails_closed_without_backend(tmp_path: Path) -> None:
    snapshot = consumer.run_consumer(
        build_request_path=_build_request(tmp_path),
        output_dir=tmp_path / "out",
        write=True,
        env={},
    )

    assert snapshot["build_backend_available"] is False
    assert snapshot["build_request_consumed"] is False
    assert snapshot["missing_capability"] == "safe_build_backend"
    assert snapshot["execution_allowed"] is False
    assert (tmp_path / "out" / "latest.json").exists()


def test_consumer_uses_mocked_safe_backend_and_records_consumption(tmp_path: Path) -> None:
    def runner(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
        assert env["QRE_BUILD_REQUEST_PATH"].endswith("latest_build_request.json")
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

    snapshot = consumer.run_consumer(
        build_request_path=_build_request(tmp_path),
        env={
            "QRE_BUILD_BACKEND": "codex_cli",
            "QRE_BUILD_COMMAND": "codex exec %QRE_BUILD_REQUEST_PATH%",
            "QRE_AUTO_PR": "true",
        },
        command_runner=runner,
    )

    assert snapshot["build_backend_available"] is True
    assert snapshot["build_request_consumed"] is True
    assert snapshot["build_started"] is True
    assert snapshot["branch_created"] is True
    assert snapshot["code_changed"] is True
    assert snapshot["tests_run"] is True
    assert snapshot["pr_created"] is True
    assert snapshot["safe_for_auto_merge"] is True
    assert snapshot["pr_metadata"]["number"] == 524

