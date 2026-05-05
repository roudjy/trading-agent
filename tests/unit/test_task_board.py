"""Unit tests for ``reporting.task_board`` (v3.15.16.6).

Properties enforced:

* digest's ``safe_to_execute`` is always ``False``
* missing source artifact -> ``final_recommendation == not_available``
* malformed source artifact -> ``not_available``
* empty proposal list -> empty tasks list, ``final_recommendation == ok``
* state vocabulary is exactly the closed eight-state set
* owner-agent vocabulary is exactly the eight canonical roles
* state derivation precedence: merged > review > in_progress >
  human_needed > blocked > todo > refined > backlog
* deterministic ordering by item_id ascending
* two runs on the same input produce a byte-identical tasks list
* ``write_outputs`` is atomic (tmp + os.replace) and writes only
  under ``logs/task_board/``
* No subprocess / shell / gh / git / network in the module source
* No mutation of any input artifact
* The roadmap_priority, pr_lifecycle, approval_inbox sources are
  best-effort: a missing one does not flip ``final_recommendation``
  to ``not_available`` (only the proposal_queue source is required)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import task_board as tb


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "reporting" / "task_board.py"


@pytest.fixture
def isolated_digest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(tb, "DIGEST_DIR_JSON", tmp_path / "tb")
    return tmp_path


def _proposal(
    pid: str,
    *,
    title: str = "test item",
    summary: str = "test summary",
    proposal_type: str = "observability_addition",
    risk_class: str = "LOW",
    status: str = "proposed",
    suggested_release_id: str | None = None,
    affected_files: list[str] | None = None,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    if affected_files is None:
        affected_files = []
    return {
        "proposal_id": pid,
        "title": title,
        "summary": summary,
        "proposal_type": proposal_type,
        "risk_class": risk_class,
        "status": status,
        "suggested_release_id": suggested_release_id,
        "affected_files": affected_files,
        "blocked_reason": blocked_reason,
    }


def _pq(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "proposal_queue_digest",
        "module_version": "v3.15.15.19",
        "proposals": proposals,
    }


# ---------------------------------------------------------------------------
# Hard-coded digest invariants
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false_with_proposals() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["safe_to_execute"] is False


def test_safe_to_execute_is_false_when_not_available() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override={"not": "valid"},  # missing proposals field
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["final_recommendation"] == tb.REC_NOT_AVAILABLE
    assert snap["safe_to_execute"] is False


def test_module_version_pinned() -> None:
    assert tb.MODULE_VERSION == "v3.15.16.6"


def test_schema_version_pinned() -> None:
    assert tb.SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Source-availability handling
# ---------------------------------------------------------------------------


def test_missing_source_yields_not_available(tmp_path: Path) -> None:
    # No override and no real file -> reads SOURCE_PROPOSAL_QUEUE
    # which (in the test env) may or may not exist. We use the
    # "not an object" path via override.
    snap = tb.collect_snapshot(
        proposal_queue_override={"proposals": "not a list"},
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["final_recommendation"] == tb.REC_NOT_AVAILABLE
    assert snap["counts"]["tasks_total"] == 0
    assert snap["tasks"] == []


def test_proposal_queue_proposals_field_not_a_list_yields_not_available() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override={"proposals": 42},
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["final_recommendation"] == tb.REC_NOT_AVAILABLE


def test_empty_proposals_list_is_not_a_failure() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["final_recommendation"] == tb.REC_OK
    assert snap["tasks"] == []
    assert snap["counts"]["tasks_total"] == 0


def test_optional_sources_missing_does_not_flip_to_not_available() -> None:
    """Only the proposal_queue source is required. Missing
    roadmap_priority / pr_lifecycle / approval_inbox is fine."""
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        roadmap_priority_override=None,
        pr_lifecycle_override=None,
        approval_inbox_override=None,
        frozen_utc="2026-05-05T10:30:00Z",
    )
    assert snap["final_recommendation"] == tb.REC_OK
    assert snap["counts"]["tasks_total"] == 1


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_state_vocabulary_is_closed_eight_set() -> None:
    expected = {
        "backlog",
        "refined",
        "todo",
        "in_progress",
        "review",
        "done",
        "blocked",
        "human_needed",
    }
    assert set(tb.STATES) == expected
    assert len(tb.STATES) == 8


def test_owner_agent_vocabulary_matches_protocol_eight_canonical() -> None:
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
    assert set(tb.OWNER_AGENTS) == expected
    assert len(tb.OWNER_AGENTS) == 8


def test_every_state_has_a_canonical_owner() -> None:
    for s in tb.STATES:
        assert s in tb._STATE_TO_OWNER
        assert tb._STATE_TO_OWNER[s] in tb.OWNER_AGENTS


def test_every_state_has_a_next_state() -> None:
    for s in tb.STATES:
        assert s in tb._STATE_TO_NEXT
        assert tb._STATE_TO_NEXT[s] in tb.STATES


# ---------------------------------------------------------------------------
# State derivation precedence
# ---------------------------------------------------------------------------


def test_proposal_with_merged_pr_lands_in_done() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal(
                    "p_aaaaaaaa",
                    title="v3.15.16.6 task board",
                    suggested_release_id="v3.15.16.6",
                ),
            ]
        ),
        pr_lifecycle_override={
            "prs": [
                {
                    "number": 99,
                    "title": "feat(v3.15.16.6): task board",
                    "branch": "fix/v3.15.16.6-task-board",
                    "state": "merged",
                    "url": "https://example/99",
                },
            ],
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_DONE
    assert "merged_pr_detected" in task["transition_reason"]
    assert task["next_state"] == tb.STATE_DONE  # terminal
    assert task["owner_agent"] == tb.AGENT_OPERATOR


def test_open_pr_with_green_ci_clean_merge_lands_in_review() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal(
                    "p_aaaaaaaa",
                    title="v3.15.16.6 task board",
                    suggested_release_id="v3.15.16.6",
                ),
            ]
        ),
        pr_lifecycle_override={
            "prs": [
                {
                    "number": 99,
                    "title": "feat(v3.15.16.6): task board",
                    "branch": "fix/v3.15.16.6-task-board",
                    "checks_state": "passed",
                    "merge_state": "clean",
                    "url": "https://example/99",
                },
            ],
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_REVIEW
    assert task["next_state"] == tb.STATE_DONE
    assert task["owner_agent"] == tb.AGENT_CI_GUARDIAN


def test_open_pr_unknown_ci_lands_in_in_progress() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal(
                    "p_aaaaaaaa",
                    title="v3.15.16.6 task board",
                    suggested_release_id="v3.15.16.6",
                ),
            ]
        ),
        pr_lifecycle_override={
            "prs": [
                {
                    "number": 99,
                    "title": "feat(v3.15.16.6): task board",
                    "branch": "fix/v3.15.16.6-task-board",
                    "checks_state": "pending",
                    "merge_state": "behind",
                    "url": "https://example/99",
                },
            ],
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_IN_PROGRESS
    assert task["next_state"] == tb.STATE_REVIEW
    assert task["owner_agent"] == tb.AGENT_IMPLEMENTATION


def test_proposal_status_needs_human_lands_in_human_needed() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal(
                    "p_aaaaaaaa",
                    title="v3.15.17.0 web push bootstrap",
                    suggested_release_id="v3.15.17.0",
                    status="needs_human",
                    risk_class="HIGH",
                ),
            ]
        ),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_HUMAN_NEEDED
    assert task["next_state"] == tb.STATE_HUMAN_NEEDED  # terminal until cleared
    assert task["owner_agent"] == tb.AGENT_OPERATOR


def test_critical_inbox_row_overrides_to_human_needed() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        approval_inbox_override={
            "data": {
                "items": [
                    {
                        "item_id": "i_xxx",
                        "related_item": "p_aaaaaaaa",
                        "severity": "critical",
                        "status": "open",
                    },
                ],
            },
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_HUMAN_NEEDED
    assert "approval_inbox_severity_critical" == task["transition_reason"]


def test_proposal_status_blocked_lands_in_blocked() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal(
                    "p_aaaaaaaa",
                    status="blocked",
                    blocked_reason="blocked_protected_path: .claude/foo",
                ),
            ]
        ),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_BLOCKED
    assert "blocked_protected_path" in task["transition_reason"]


def test_filtered_by_priority_with_blocked_reason_lands_in_blocked() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        roadmap_priority_override={
            "candidates": [],
            "filtered_out": [
                {
                    "proposal_id": "p_aaaaaaaa",
                    "filter_reason": "risk_high_excluded",
                },
            ],
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_BLOCKED


def test_eligible_in_priority_lands_in_todo() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        roadmap_priority_override={
            "candidates": [{"proposal_id": "p_aaaaaaaa", "rank": 1}],
            "filtered_out": [],
        },
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_TODO
    assert task["next_state"] == tb.STATE_IN_PROGRESS
    assert task["owner_agent"] == tb.AGENT_IMPLEMENTATION


def test_classified_with_risk_lands_in_refined() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa", risk_class="MEDIUM")]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_REFINED
    assert "classified_with_risk_MEDIUM" == task["transition_reason"]


def test_unknown_risk_lands_in_backlog() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa", risk_class="UNKNOWN")]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    task = snap["tasks"][0]
    assert task["current_state"] == tb.STATE_BACKLOG
    assert task["owner_agent"] == tb.AGENT_PRODUCT_OWNER


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_runs_produce_identical_tasks_list() -> None:
    pq = _pq(
        [
            _proposal("p_zzzzzzzz", risk_class="LOW"),
            _proposal("p_aaaaaaaa", risk_class="LOW"),
            _proposal("p_mmmmmmmm", risk_class="LOW"),
        ]
    )
    s1 = tb.collect_snapshot(
        proposal_queue_override=pq, frozen_utc="2026-05-05T10:30:00Z"
    )
    s2 = tb.collect_snapshot(
        proposal_queue_override=pq, frozen_utc="2026-05-05T10:30:00Z"
    )
    assert s1["tasks"] == s2["tasks"]
    assert s1["counts"] == s2["counts"]


def test_tasks_are_sorted_by_item_id_ascending() -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq(
            [
                _proposal("p_zzzzzzzz", risk_class="LOW"),
                _proposal("p_aaaaaaaa", risk_class="LOW"),
                _proposal("p_mmmmmmmm", risk_class="LOW"),
            ]
        ),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    ids = [t["item_id"] for t in snap["tasks"]]
    assert ids == ["p_aaaaaaaa", "p_mmmmmmmm", "p_zzzzzzzz"]


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_outputs_atomic_and_scoped(
    isolated_digest_dir: Path,
) -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa", risk_class="LOW")]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    paths = tb.write_outputs(snap)
    base = isolated_digest_dir / "tb"
    assert (base / "latest.json").exists()
    assert (base / "history.jsonl").exists()
    payload = json.loads((base / "latest.json").read_text(encoding="utf-8"))
    assert payload["counts"]["tasks_total"] == 1
    assert paths["latest"].endswith("latest.json")
    leftover_tmps = list(base.glob("*.tmp"))
    assert leftover_tmps == [], f"leftover tmp files: {leftover_tmps}"


def test_write_outputs_appends_one_history_line(
    isolated_digest_dir: Path,
) -> None:
    snap = tb.collect_snapshot(
        proposal_queue_override=_pq([_proposal("p_aaaaaaaa")]),
        frozen_utc="2026-05-05T10:30:00Z",
    )
    tb.write_outputs(snap)
    tb.write_outputs(snap)
    history = isolated_digest_dir / "tb" / "history.jsonl"
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
        "from requests",
        "import urllib.request",
        "from urllib.request",
        "import urllib3",
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
    """Pinned: every ``"safe_to_execute":`` literal in the module
    source binds to ``False``."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = re.findall(r'"safe_to_execute":\s*([A-Za-z]+)', src)
    assert occurrences, "safe_to_execute key not found in module source"
    assert all(v == "False" for v in occurrences), (
        f"safe_to_execute is not hard-coded False everywhere: {occurrences!r}"
    )


# ---------------------------------------------------------------------------
# Non-mutation of input artifacts
# ---------------------------------------------------------------------------


def test_no_input_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The task_board must not mutate any of its source files."""
    pq_file = tmp_path / "proposal_queue.json"
    payload = _pq([_proposal("p_aaaaaaaa")])
    pq_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    before = pq_file.read_bytes()
    monkeypatch.setattr(tb, "DIGEST_DIR_JSON", tmp_path / "tb")
    monkeypatch.setattr(tb, "SOURCE_PROPOSAL_QUEUE", pq_file)
    snap = tb.collect_snapshot(frozen_utc="2026-05-05T10:30:00Z")
    tb.write_outputs(snap)
    after = pq_file.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_only_dry_run_mode_allowed() -> None:
    with pytest.raises(SystemExit):
        tb.main(["--mode", "execute-safe"])


def test_cli_status_returns_not_available_when_missing(
    isolated_digest_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = tb.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not_available" in out
