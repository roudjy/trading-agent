"""Unit tests for ``reporting.agent_flow`` (v3.15.16.7)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import agent_flow as af


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "reporting" / "agent_flow.py"


@pytest.fixture
def isolated_digest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(af, "DIGEST_DIR_JSON", tmp_path / "af")
    return tmp_path


def _task(
    item_id: str,
    *,
    current_state: str = "refined",
    owner_agent: str = "planner",
    title: str = "test item",
    transition_reason: str = "classified_with_risk_LOW",
    release_id: str | None = None,
    pr_url: str = "",
    pr_number: int | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "release_id": release_id,
        "current_state": current_state,
        "next_state": "todo",
        "transition_reason": transition_reason,
        "owner_agent": owner_agent,
        "retry_count": 0,
        "last_update": None,
        "evidence": {
            "pr_url": pr_url,
            "pr_number": pr_number,
            "affected_files": [],
        },
    }


def _tb(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "task_board_digest",
        "module_version": "v3.15.16.6",
        "tasks": tasks,
    }


# ---------------------------------------------------------------------------
# Hard-coded digest invariants
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false_with_handoffs() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb([_task("p_aaaaaaaa")]),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    assert snap["safe_to_execute"] is False


def test_safe_to_execute_is_false_when_not_available() -> None:
    snap = af.collect_snapshot(
        task_board_override={"not": "valid"},
        frozen_utc="2026-05-05T11:00:00Z",
    )
    assert snap["final_recommendation"] == af.REC_NOT_AVAILABLE
    assert snap["safe_to_execute"] is False


def test_module_version_pinned() -> None:
    assert af.MODULE_VERSION == "v3.15.16.7"


def test_schema_version_pinned() -> None:
    assert af.SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_action_vocabulary_is_closed_eight_set() -> None:
    expected = {
        "select_next_task",
        "generate_plan",
        "implement",
        "validate",
        "review",
        "merge",
        "escalate_human",
        "no_op",
    }
    assert set(af.ACTIONS) == expected
    assert len(af.ACTIONS) == 8


def test_owner_agent_vocabulary_matches_eight_canonical() -> None:
    expected = {
        "product_owner",
        "strategic_advisor",
        "planner",
        "implementation_agent",
        "architecture_guardian",
        "ci_guardian",
        "security_governance_guardian",
        "operator",
    }
    assert set(af.OWNER_AGENTS) == expected
    assert len(af.OWNER_AGENTS) == 8


def test_every_known_stage_maps_to_action_and_next_agent() -> None:
    stages = {
        "backlog",
        "refined",
        "todo",
        "in_progress",
        "review",
        "done",
        "blocked",
        "human_needed",
    }
    for s in stages:
        assert s in af._STAGE_TO_NEXT_AGENT
        assert s in af._STAGE_TO_ACTION
        assert af._STAGE_TO_NEXT_AGENT[s] in af.OWNER_AGENTS
        assert af._STAGE_TO_ACTION[s] in af.ACTIONS


# ---------------------------------------------------------------------------
# Source availability
# ---------------------------------------------------------------------------


def test_missing_source_yields_not_available() -> None:
    snap = af.collect_snapshot(
        task_board_override={"tasks": "not a list"},
        frozen_utc="2026-05-05T11:00:00Z",
    )
    assert snap["final_recommendation"] == af.REC_NOT_AVAILABLE


def test_empty_tasks_list_is_ok_with_zero_handoffs() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb([]), frozen_utc="2026-05-05T11:00:00Z"
    )
    assert snap["final_recommendation"] == af.REC_OK
    assert snap["counts"]["handoffs_total"] == 0


# ---------------------------------------------------------------------------
# Per-stage projections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage,expected_action,expected_next_agent,expected_handoff_eligible",
    [
        ("backlog", "select_next_task", "planner", True),
        ("refined", "generate_plan", "implementation_agent", True),
        ("todo", "implement", "implementation_agent", True),
        ("in_progress", "validate", "ci_guardian", True),
        ("review", "merge", "operator", True),
        ("done", "no_op", "operator", False),
        ("blocked", "escalate_human", "operator", False),
        ("human_needed", "escalate_human", "operator", False),
    ],
)
def test_each_stage_projects_correctly(
    stage: str,
    expected_action: str,
    expected_next_agent: str,
    expected_handoff_eligible: bool,
) -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb([_task("p_aaaaaaaa", current_state=stage)]),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    h = snap["handoffs"][0]
    assert h["current_stage"] == stage
    assert h["next_action_proposed"] == expected_action
    assert h["next_agent"] == expected_next_agent
    assert h["handoff_eligible"] is expected_handoff_eligible


def test_blocked_carries_blocking_reason() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb(
            [
                _task(
                    "p_aaaaaaaa",
                    current_state="blocked",
                    transition_reason="proposal_status_blocked: blocked_protected_path: .claude/foo",
                )
            ]
        ),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    h = snap["handoffs"][0]
    assert "blocked_protected_path" in (h["blocking_reason"] or "")


def test_human_needed_carries_blocking_reason() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb(
            [
                _task(
                    "p_aaaaaaaa",
                    current_state="human_needed",
                    transition_reason="approval_inbox_severity_critical",
                )
            ]
        ),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    h = snap["handoffs"][0]
    assert h["blocking_reason"] == "approval_inbox_severity_critical"


def test_unknown_stage_lands_in_escalate_human() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb(
            [_task("p_aaaaaaaa", current_state="not_a_real_stage")]
        ),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    h = snap["handoffs"][0]
    assert h["next_action_proposed"] == af.ACTION_ESCALATE_HUMAN
    assert "unknown_current_stage" in (h["blocking_reason"] or "")


def test_invalid_row_shape_is_skipped() -> None:
    snap = af.collect_snapshot(
        task_board_override={
            "tasks": [
                {"missing": "item_id"},
                _task("p_valid", current_state="refined"),
            ]
        },
        frozen_utc="2026-05-05T11:00:00Z",
    )
    assert snap["counts"]["handoffs_total"] == 1
    assert snap["source_task_board"]["skipped_invalid_rows"] == 1


def test_owner_agent_outside_closed_set_falls_back_to_operator() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb(
            [_task("p_aaaaaaaa", owner_agent="not_a_real_agent")]
        ),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    h = snap["handoffs"][0]
    assert h["responsible_agent"] == af.AGENT_OPERATOR


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_runs_produce_identical_handoffs() -> None:
    tb = _tb(
        [
            _task("p_zzzzzzzz", current_state="refined"),
            _task("p_aaaaaaaa", current_state="refined"),
            _task("p_mmmmmmmm", current_state="refined"),
        ]
    )
    s1 = af.collect_snapshot(
        task_board_override=tb, frozen_utc="2026-05-05T11:00:00Z"
    )
    s2 = af.collect_snapshot(
        task_board_override=tb, frozen_utc="2026-05-05T11:00:00Z"
    )
    assert s1["handoffs"] == s2["handoffs"]
    assert s1["counts"] == s2["counts"]


def test_handoffs_sorted_by_item_id_ascending() -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb(
            [
                _task("p_zzzzzzzz", current_state="refined"),
                _task("p_aaaaaaaa", current_state="refined"),
                _task("p_mmmmmmmm", current_state="refined"),
            ]
        ),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    ids = [h["item_id"] for h in snap["handoffs"]]
    assert ids == ["p_aaaaaaaa", "p_mmmmmmmm", "p_zzzzzzzz"]


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_outputs_atomic_and_scoped(isolated_digest_dir: Path) -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb([_task("p_aaaaaaaa", current_state="refined")]),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    paths = af.write_outputs(snap)
    base = isolated_digest_dir / "af"
    assert (base / "latest.json").exists()
    assert (base / "history.jsonl").exists()
    leftover = list(base.glob("*.tmp"))
    assert leftover == []
    assert paths["latest"].endswith("latest.json")


def test_history_appends_one_line_per_write(
    isolated_digest_dir: Path,
) -> None:
    snap = af.collect_snapshot(
        task_board_override=_tb([_task("p_aaaaaaaa")]),
        frozen_utc="2026-05-05T11:00:00Z",
    )
    af.write_outputs(snap)
    af.write_outputs(snap)
    history = isolated_digest_dir / "af" / "history.jsonl"
    lines = [
        ln for ln in history.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 2


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
        "from urllib.request",
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


def test_safe_to_execute_field_is_hard_coded_false() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = re.findall(r'"safe_to_execute":\s*([A-Za-z]+)', src)
    assert occurrences, "safe_to_execute key not found in module source"
    assert all(v == "False" for v in occurrences), (
        f"safe_to_execute is not hard-coded False everywhere: {occurrences!r}"
    )


def test_no_input_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tb_file = tmp_path / "task_board.json"
    payload = _tb([_task("p_aaaaaaaa")])
    tb_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    before = tb_file.read_bytes()
    monkeypatch.setattr(af, "DIGEST_DIR_JSON", tmp_path / "af")
    monkeypatch.setattr(af, "SOURCE_TASK_BOARD", tb_file)
    snap = af.collect_snapshot(frozen_utc="2026-05-05T11:00:00Z")
    af.write_outputs(snap)
    after = tb_file.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_only_dry_run_mode_allowed() -> None:
    with pytest.raises(SystemExit):
        af.main(["--mode", "execute-safe"])


def test_cli_status_returns_not_available_when_missing(
    isolated_digest_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = af.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not_available" in out
