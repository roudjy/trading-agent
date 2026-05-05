"""Unit tests for ``reporting.human_needed`` (v3.15.16.8)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import human_needed as hn


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "reporting" / "human_needed.py"


@pytest.fixture
def isolated_digest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(hn, "DIGEST_DIR_JSON", tmp_path / "hn")
    return tmp_path


def _task(
    item_id: str,
    *,
    current_state: str = "blocked",
    title: str = "test item",
    transition_reason: str = "blocked_protected_path: .claude/foo",
    affected_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "current_state": current_state,
        "transition_reason": transition_reason,
        "evidence": {"affected_files": affected_files or []},
    }


def _tb(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "task_board_digest",
        "module_version": "v3.15.16.6",
        "tasks": tasks,
    }


def _make_api_dir(tmp: Path, modules: list[tuple[str, str]]) -> Path:
    """Build a fake dashboard/api_*.py tree containing the given
    register_*_routes definitions."""
    api_dir = tmp / "dashboard"
    api_dir.mkdir(parents=True, exist_ok=True)
    for module_basename, fn_name in modules:
        (api_dir / f"{module_basename}.py").write_text(
            f"def {fn_name}(app):\n    return None\n",
            encoding="utf-8",
        )
    return api_dir


def _make_dashboard_py(tmp: Path, body: str) -> Path:
    p = tmp / "dashboard.py"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Hard-coded digest invariants
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false_with_events(
    tmp_path: Path,
) -> None:
    api_dir = _make_api_dir(tmp_path, [("api_xyz", "register_xyz_routes")])
    dash_py = _make_dashboard_py(tmp_path, "from foo import bar\n")
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    assert snap["safe_to_execute"] is False


def test_module_version_pinned() -> None:
    assert hn.MODULE_VERSION == "v3.15.16.8"


def test_schema_version_pinned() -> None:
    assert hn.SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_reason_vocabulary_is_closed_six_set() -> None:
    expected = {
        "governance_bootstrap_required",
        "no_touch_path_blocks_wiring",
        "allowlist_blocks_completion",
        "release_gate_blocks_progression",
        "system_cannot_proceed_safely",
        "decision_cannot_be_inferred",
    }
    assert set(hn.REASONS) == expected
    assert len(hn.REASONS) == 6


def test_impact_priority_vocabulary_is_closed() -> None:
    expected = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert set(hn.IMPACTS) == expected
    assert set(hn.PRIORITIES) == expected


# ---------------------------------------------------------------------------
# Wiring-gap detection (the canonical v3.15.16.5 use case)
# ---------------------------------------------------------------------------


def test_wiring_gap_detection_emits_governance_bootstrap_event(
    tmp_path: Path,
) -> None:
    api_dir = _make_api_dir(
        tmp_path,
        [("api_roadmap_priority", "register_roadmap_priority_routes")],
    )
    dash_py = _make_dashboard_py(
        tmp_path, "# dashboard.py with no roadmap_priority import\n"
    )
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    events = [e for e in snap["events"] if e["reason"] == hn.REASON_GOVERNANCE_BOOTSTRAP]
    assert len(events) == 1
    e = events[0]
    assert "register_roadmap_priority_routes" in e["blocking_component"]
    assert e["proposed_patch"] is not None
    assert (
        "from dashboard.api_roadmap_priority import register_roadmap_priority_routes"
        in e["proposed_patch"]
    )
    assert "register_roadmap_priority_routes(app)" in e["proposed_patch"]
    assert e["priority"] in hn.PRIORITIES


def test_wiring_gap_clears_when_module_is_wired(tmp_path: Path) -> None:
    api_dir = _make_api_dir(
        tmp_path,
        [("api_roadmap_priority", "register_roadmap_priority_routes")],
    )
    dash_py = _make_dashboard_py(
        tmp_path,
        "from dashboard.api_roadmap_priority import register_roadmap_priority_routes\n"
        "register_roadmap_priority_routes(app)\n",
    )
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    events = [
        e for e in snap["events"] if e["reason"] == hn.REASON_GOVERNANCE_BOOTSTRAP
    ]
    assert events == []


def test_wiring_gap_handles_multi_line_imports(tmp_path: Path) -> None:
    """The detector must NOT emit a false positive when the import
    is multi-line (parenthesised)."""
    api_dir = _make_api_dir(
        tmp_path,
        [("api_research_intelligence", "register_research_intelligence_routes")],
    )
    dash_py = _make_dashboard_py(
        tmp_path,
        "from dashboard.api_research_intelligence import (\n"
        "    register_research_intelligence_routes,\n"
        ")\n"
        "register_research_intelligence_routes(app)\n",
    )
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    events = [
        e for e in snap["events"] if e["reason"] == hn.REASON_GOVERNANCE_BOOTSTRAP
    ]
    assert events == []


def test_execute_safe_routes_is_intentionally_not_detected(
    tmp_path: Path,
) -> None:
    """v3.15.15.27 invariant: register_execute_safe_routes is
    intentionally NOT wired. The detector must skip api_execute_safe_controls
    so it never auto-suggests wiring it."""
    api_dir = _make_api_dir(
        tmp_path,
        [
            ("api_execute_safe_controls", "register_execute_safe_routes"),
        ],
    )
    dash_py = _make_dashboard_py(tmp_path, "# nothing\n")
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    assert snap["counts"]["events_total"] == 0


# ---------------------------------------------------------------------------
# Task-board derived events
# ---------------------------------------------------------------------------


def test_blocked_task_with_protected_path_emits_no_touch_event(
    tmp_path: Path,
) -> None:
    api_dir = _make_api_dir(tmp_path, [])
    dash_py = _make_dashboard_py(tmp_path, "# nothing\n")
    snap = hn.collect_snapshot(
        task_board_override=_tb(
            [
                _task(
                    "p_aaaaaaaa",
                    current_state="blocked",
                    transition_reason="proposal_status_blocked: blocked_protected_path: .claude/agents/foo",
                ),
            ]
        ),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    events = [
        e for e in snap["events"] if e["reason"] == hn.REASON_NO_TOUCH_PATH
    ]
    assert len(events) == 1
    assert events[0]["related_item"] == "p_aaaaaaaa"


def test_human_needed_task_emits_decision_unclear_event(
    tmp_path: Path,
) -> None:
    api_dir = _make_api_dir(tmp_path, [])
    dash_py = _make_dashboard_py(tmp_path, "# nothing\n")
    snap = hn.collect_snapshot(
        task_board_override=_tb(
            [
                _task(
                    "p_aaaaaaaa",
                    current_state="human_needed",
                    transition_reason="approval_inbox_severity_critical",
                ),
            ]
        ),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    events = [
        e for e in snap["events"] if e["reason"] == hn.REASON_DECISION_UNCLEAR
    ]
    assert len(events) == 1
    assert events[0]["priority"] in hn.PRIORITIES


# ---------------------------------------------------------------------------
# Determinism + ordering
# ---------------------------------------------------------------------------


def test_two_runs_produce_identical_events(tmp_path: Path) -> None:
    api_dir = _make_api_dir(
        tmp_path,
        [
            ("api_a", "register_a_routes"),
            ("api_b", "register_b_routes"),
        ],
    )
    dash_py = _make_dashboard_py(tmp_path, "# nothing\n")
    s1 = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    s2 = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    assert s1["events"] == s2["events"]


def test_event_id_deterministic() -> None:
    a = hn._event_id(hn.REASON_GOVERNANCE_BOOTSTRAP, "x", "y")
    b = hn._event_id(hn.REASON_GOVERNANCE_BOOTSTRAP, "x", "y")
    assert a == b
    assert a.startswith("h_")


# ---------------------------------------------------------------------------
# Module-source guarantees
# ---------------------------------------------------------------------------


def test_module_source_no_subprocess_no_network() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "shell=True",
        "os.system(",
        "Popen(",
        "import requests",
        "import urllib.request",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden token: {tok!r}"


def test_module_source_no_gh_or_git_invocation() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen", "gh pr ", "git checkout ")
    for tok in forbidden:
        assert tok not in src, f"forbidden gh/git token: {tok!r}"


def test_module_source_no_branch_or_pr_creation() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "git checkout -b",
        "git push",
        "gh pr create",
        "gh pr merge",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden action: {tok!r}"


def test_module_source_does_not_apply_patches() -> None:
    """The proposed_patch field must be text only — the module
    source must NOT contain any `git apply`, `patch -`, or other
    patch-application call."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "git apply",
        "patch -",
        "subprocess.run",
        "subprocess.Popen",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden patch-application token: {tok!r}"


def test_safe_to_execute_field_is_hard_coded_false() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = re.findall(r'"safe_to_execute":\s*([A-Za-z]+)', src)
    assert occurrences, "safe_to_execute key not found in module source"
    assert all(v == "False" for v in occurrences), (
        f"safe_to_execute is not hard-coded False everywhere: {occurrences!r}"
    )


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_outputs_atomic_and_scoped(
    isolated_digest_dir: Path, tmp_path: Path
) -> None:
    api_dir = _make_api_dir(tmp_path, [])
    dash_py = _make_dashboard_py(tmp_path, "# nothing\n")
    snap = hn.collect_snapshot(
        task_board_override=_tb([]),
        api_dir_override=api_dir,
        dashboard_py_override=dash_py,
        frozen_utc="2026-05-05T11:30:00Z",
    )
    paths = hn.write_outputs(snap)
    base = isolated_digest_dir / "hn"
    assert (base / "latest.json").exists()
    assert (base / "history.jsonl").exists()
    assert paths["latest"].endswith("latest.json")
    leftover = list(base.glob("*.tmp"))
    assert leftover == []


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_only_dry_run_mode_allowed() -> None:
    with pytest.raises(SystemExit):
        hn.main(["--mode", "execute-safe"])


def test_cli_status_returns_not_available_when_missing(
    isolated_digest_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = hn.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not_available" in out
