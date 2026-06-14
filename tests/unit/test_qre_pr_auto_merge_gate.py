from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research import qre_pr_auto_merge_gate as gate
from tests.unit.test_qre_build_request_consumer import _build_request


def _safe_pr() -> dict[str, Any]:
    return {
        "number": 527,
        "branch": "feat/qre-add-cache-only-metric-path",
        "title": "feat: add cache only metric path",
        "ci_status": "pending",
        "mergeable": True,
        "safe_for_auto_merge": True,
        "changed_files": [
            "research/qre_cache_only_metric_path.py",
            "research/qre_controlled_research_run.py",
            "tests/unit/test_qre_cache_only_metric_path.py",
        ],
    }


def _check(name: str, *, status: str = "COMPLETED", conclusion: str = "SUCCESS") -> dict[str, str]:
    return {"name": name, "status": status, "conclusion": conclusion}


def _live_pr(*, checks: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "number": 527,
        "title": "feat: add cache only metric path",
        "state": "OPEN",
        "mergeCommit": None,
        "headRefName": "feat/qre-add-cache-only-metric-path",
        "baseRefName": "main",
        "statusCheckRollup": checks
        if checks is not None
        else [
            _check("path-classifier"),
            _check("lint/ruff"),
            _check("secret-scan/gitleaks"),
            _check("mypy narrow"),
            _check("unit smoke + unit"),
            _check("regression-fast"),
            _check("architecture-boundary"),
            _check("hook-tests"),
            _check("governance-lint"),
        ],
        "changedFiles": 3,
        "url": "https://github.com/roudjy/trading-agent/pull/527",
        "mergeable": "MERGEABLE",
    }


def _runner(
    live_pr: dict[str, Any] | None = None,
    *,
    view_returncode: int = 0,
) -> tuple[list[list[str]], gate.CommandRunner]:
    calls: list[list[str]] = []

    def run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            if view_returncode != 0:
                return (view_returncode, "", "gh failed")
            return (0, json.dumps(live_pr or _live_pr()), "")
        if cmd[:3] == ["gh", "pr", "merge"]:
            return (0, "merged", "")
        return (1, "", "unexpected command")

    return calls, run


def test_stale_pending_artifact_allows_when_live_github_status_is_green(tmp_path: Path) -> None:
    calls, runner = _runner()

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
        write=True,
        output_dir=tmp_path / "gate",
    )

    assert snapshot["auto_merge_allowed"] is True
    assert snapshot["pr_auto_merged"] is True
    assert snapshot["pr_green"] is True
    assert snapshot["ci_source"] == "live_gh_pr_view"
    assert snapshot["live_pr_status_queried"] is True
    assert calls == [
        ["gh", "pr", "view", "527", "--json", gate.GH_PR_VIEW_FIELDS],
        ["gh", "pr", "merge", "527", "--squash", "--delete-branch"],
    ]
    assert (tmp_path / "gate" / "latest.json").exists()


def test_live_github_failed_check_blocks_auto_merge(tmp_path: Path) -> None:
    calls, runner = _runner(_live_pr(checks=[_check("lint/ruff", conclusion="FAILURE")]))

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert snapshot["pr_auto_merged"] is False
    assert "ci_not_green" in snapshot["blocked_reasons"]
    assert snapshot["live_check_summary"]["failed"] == 1
    assert calls == [["gh", "pr", "view", "527", "--json", gate.GH_PR_VIEW_FIELDS]]


def test_live_github_pending_required_check_blocks_auto_merge(tmp_path: Path) -> None:
    _, runner = _runner(_live_pr(checks=[_check("unit smoke + unit", status="IN_PROGRESS", conclusion="")]))

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert "ci_not_green" in snapshot["blocked_reasons"]
    assert snapshot["live_check_summary"]["pending"] == 1


def test_frontend_vitest_skipped_remains_non_blocking(tmp_path: Path) -> None:
    _, runner = _runner(
        _live_pr(
            checks=[
                _check("lint/ruff"),
                _check("frontend/vitest", conclusion="SKIPPED"),
            ]
        )
    )

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is True
    assert snapshot["live_check_summary"]["skipped"] == 1
    assert snapshot["live_check_summary"]["blocking"] == []


def test_forbidden_path_still_blocks_even_if_ci_green(tmp_path: Path) -> None:
    pr = _safe_pr()
    pr["changed_files"] = ["broker/live_adapter.py"]
    _, runner = _runner()

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=pr,
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert "forbidden_paths_touched" in snapshot["blocked_reasons"]


def test_protected_artifact_path_still_blocks(tmp_path: Path) -> None:
    pr = _safe_pr()
    pr["changed_files"] = ["research/research_latest.json"]
    _, runner = _runner()

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=pr,
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert snapshot["protected_outputs_mutated"] is True
    assert "protected_outputs_mutated" in snapshot["blocked_reasons"]


def test_gh_pr_view_failure_blocks_closed(tmp_path: Path) -> None:
    _, runner = _runner(view_returncode=1)

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={"QRE_AUTO_MERGE_GREEN": "true"},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert snapshot["live_pr_status_queried"] is True
    assert "live_pr_status_unavailable" in snapshot["blocked_reasons"]


def test_pr_gate_requires_explicit_auto_merge_flag(tmp_path: Path) -> None:
    calls, runner = _runner()

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={},
        command_runner=runner,
    )

    assert snapshot["auto_merge_allowed"] is False
    assert snapshot["pr_auto_merged"] is False
    assert "auto_merge_not_enabled" in snapshot["blocked_reasons"]
    assert calls == [["gh", "pr", "view", "527", "--json", gate.GH_PR_VIEW_FIELDS]]
