from __future__ import annotations

import json
from pathlib import Path

from research import qre_runtime_update_and_continue as cont


def _merge_result(tmp_path: Path) -> Path:
    path = tmp_path / "merge.json"
    path.write_text(
        json.dumps(
            {
                "report_kind": "qre_pr_auto_merge_gate",
                "pr_number": 524,
                "pr_auto_merged": True,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_runtime_continuation_runs_research_after_mocked_merge_update(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(cmd)
        return (0, "ok", "")

    snapshot = cont.run_continuation(
        merge_result_path=_merge_result(tmp_path),
        output_dir=tmp_path / "out",
        max_cycles=1,
        write=True,
        command_runner=runner,
    )

    assert snapshot["runtime_updated"] is True
    assert snapshot["research_continuation_started"] is True
    assert snapshot["research_cycles_started"] == 1
    assert calls == [["git", "checkout", "main"], ["git", "pull", "--ff-only", "origin", "main"]]
    assert snapshot["paper_shadow_live_allowed"] is False
    assert snapshot["broker_risk_allowed"] is False
    assert snapshot["execution_allowed"] is False


def test_runtime_continuation_fails_closed_without_merge_result(tmp_path: Path) -> None:
    snapshot = cont.run_continuation(
        merge_result_path=tmp_path / "missing.json",
        output_dir=tmp_path / "out",
        write=True,
    )

    assert snapshot["runtime_updated"] is False
    assert snapshot["research_continuation_started"] is False
    assert "merge_result_missing" in snapshot["blocked_reasons"]

