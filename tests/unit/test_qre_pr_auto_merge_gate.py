from __future__ import annotations

from pathlib import Path

from research import qre_pr_auto_merge_gate as gate
from tests.unit.test_qre_build_request_consumer import _build_request


def _safe_pr() -> dict:
    return {
        "number": 524,
        "branch": "feat/qre-add-cache-only-metric-path",
        "title": "feat: add cache only metric path",
        "ci_status": "green",
        "mergeable": True,
        "changed_files": [
            "research/qre_cache_only_metric_path.py",
            "tests/unit/test_qre_cache_only_metric_path.py",
        ],
    }


def test_pr_gate_blocks_unsafe_path_changes(tmp_path: Path) -> None:
    pr = _safe_pr()
    pr["changed_files"] = ["broker/live_adapter.py"]

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=pr,
        env={"QRE_AUTO_MERGE_GREEN": "true"},
    )

    assert snapshot["auto_merge_allowed"] is False
    assert snapshot["manual_governance_required"] is True
    assert "forbidden_paths_touched" in snapshot["blocked_reasons"]


def test_pr_gate_blocks_non_green_ci(tmp_path: Path) -> None:
    pr = _safe_pr()
    pr["ci_status"] = "failure"

    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=pr,
        env={"QRE_AUTO_MERGE_GREEN": "true"},
    )

    assert snapshot["auto_merge_allowed"] is False
    assert "ci_not_green" in snapshot["blocked_reasons"]


def test_pr_gate_allows_auto_merge_only_for_safe_mocked_green_pr(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(cmd)
        return (0, "merged", "")

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
    assert calls == [["gh", "pr", "merge", "524", "--squash", "--delete-branch"]]
    assert (tmp_path / "gate" / "latest.json").exists()


def test_pr_gate_requires_explicit_auto_merge_flag(tmp_path: Path) -> None:
    snapshot = gate.run_gate(
        build_request_path=_build_request(tmp_path),
        pr_metadata=_safe_pr(),
        env={},
    )

    assert snapshot["auto_merge_allowed"] is False
    assert "auto_merge_not_enabled" in snapshot["blocked_reasons"]

