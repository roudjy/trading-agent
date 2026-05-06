"""Unit tests for v3.15.16.10 PR-5 / A7 — Autonomous Development
Track readiness gate.

All synthetic deterministic fixtures. No runtime ``/tmp`` baselines
committed. CI marker absence yields ``UNKNOWN`` (never a fake OK).
"""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from reporting import autonomous_dev_readiness as adr
from reporting import autonomous_dev_readiness_blockers as adr_blockers


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_result_and_state_vocabularies_are_closed() -> None:
    assert adr.RESULT_VALUES == ("OK", "FAIL", "UNKNOWN")
    assert adr.STATE_OK == "OK"
    assert adr.STATE_BLOCKED == "BLOCKED"
    assert adr.STATE_UNKNOWN == "UNKNOWN"


def test_artifact_path_is_under_logs_not_research() -> None:
    assert adr.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in adr.ARTIFACT_RELATIVE_PATH


def test_obsolete_top_level_names_are_exactly_four() -> None:
    """The four obsolete top-level roadmap docs that PR-1 archived."""
    assert set(adr.OBSOLETE_TOP_LEVEL_NAMES) == {
        "qre_roadmap_v6_1.md",
        "qre_roadmap_v3_post_v3_15.md",
        "qre_roadmap_v4.md",
        "qre_prompt_guidelines_v2.md",
    }


def test_prohibited_top_level_dirs_are_trading_execution_paths() -> None:
    """The dirs whose presence indicates trading-execution work."""
    assert set(adr.PROHIBITED_TOP_LEVEL_DIRS) == {
        "broker",
        "live",
        "paper",
        "shadow",
        "trading",
    }


def test_next_product_phase_phrase_is_canonical() -> None:
    """Verbatim — the readiness gate insists on this exact phrase
    appearing in the canonical product roadmap."""
    assert adr.NEXT_PRODUCT_PHASE_PHRASE == "v3.15.16 — Intelligent Routing Layer"


def test_known_false_positive_blockers_set_is_closed() -> None:
    """Closed deliberate corpus, not a runtime baseline. Adding an
    entry must be a code change, not a copy from logs."""
    assert isinstance(
        adr_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS, frozenset
    )
    # The historical blocker the operator surfaced when scoping A5.
    assert "p_1f81cb23" in adr_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS


def test_collect_snapshot_top_level_keys() -> None:
    snap = adr.collect_snapshot()
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "state",
        "failing_criteria",
        "unknown_criteria",
        "criteria",
        "next_product_phase",
        "canonical_product_roadmap",
        "canonical_autonomous_development_doc",
        "handoff_lines",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "autonomous_dev_readiness"
    assert snap["schema_version"] == "1.0"
    assert snap["state"] in adr.RESULT_VALUES
    assert isinstance(snap["criteria"], list)
    # Eleven criteria, in order, mirroring autonomous_development.txt §A7.
    assert len(snap["criteria"]) == 11
    seen = [c["criterion"] for c in snap["criteria"]]
    assert seen == [
        "policy_doc_present",
        "classifier_present",
        "classifier_tests_passing",
        "reporting_read_only_visibility",
        "autonomous_development_doc_present",
        "qre_roadmap_doc_present",
        "obsolete_roadmaps_archived",
        "known_false_positive_blockers_resolved",
        "governance_health_visible",
        "no_live_paper_shadow_mutation",
        "next_product_phase_named",
    ]


# ---------------------------------------------------------------------------
# CI marker semantics — UNKNOWN locally; OK only from a real marker.
# ---------------------------------------------------------------------------


def test_classifier_tests_passing_is_unknown_when_marker_absent(
    tmp_path: Path,
) -> None:
    crit = adr._criterion_classifier_tests_passing(
        ci_marker_path=tmp_path / "no_such_marker.json"
    )
    assert crit["result"] == "UNKNOWN"
    assert crit["marker_present"] is False
    assert "ci_remains_authoritative" in crit["reason"]


def test_classifier_tests_passing_ok_only_when_marker_says_zero_failed(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"passed": 274, "failed": 0}), encoding="utf-8")
    crit = adr._criterion_classifier_tests_passing(ci_marker_path=marker)
    assert crit["result"] == "OK"
    assert crit["marker_present"] is True
    assert crit["passed"] == 274
    assert crit["failed"] == 0


def test_classifier_tests_passing_fail_when_marker_records_failures(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"passed": 100, "failed": 1}), encoding="utf-8")
    crit = adr._criterion_classifier_tests_passing(ci_marker_path=marker)
    assert crit["result"] == "FAIL"


# ---------------------------------------------------------------------------
# Path-based criteria (against the real repo — these reflect the live
# state after PR-1..PR-4 merged).
# ---------------------------------------------------------------------------


def test_canonical_docs_present_in_repo() -> None:
    snap = adr.collect_snapshot()
    by_name = {c["criterion"]: c for c in snap["criteria"]}
    assert by_name["policy_doc_present"]["result"] == "OK"
    assert by_name["classifier_present"]["result"] == "OK"
    assert by_name["autonomous_development_doc_present"]["result"] == "OK"
    assert by_name["qre_roadmap_doc_present"]["result"] == "OK"


def test_obsolete_roadmaps_archived_post_pr1() -> None:
    snap = adr.collect_snapshot()
    by_name = {c["criterion"]: c for c in snap["criteria"]}
    crit = by_name["obsolete_roadmaps_archived"]
    assert crit["result"] == "OK"
    assert crit["leaked_at_top_level"] == []
    assert crit["missing_from_archive"] == []


def test_no_live_paper_shadow_mutation_post_pr1() -> None:
    snap = adr.collect_snapshot()
    by_name = {c["criterion"]: c for c in snap["criteria"]}
    crit = by_name["no_live_paper_shadow_mutation"]
    assert crit["result"] == "OK"
    assert crit["present_at_top_level"] == []


def test_next_product_phase_named_in_canonical_roadmap() -> None:
    snap = adr.collect_snapshot()
    by_name = {c["criterion"]: c for c in snap["criteria"]}
    crit = by_name["next_product_phase_named"]
    assert crit["result"] == "OK"
    assert crit["phrase_present"] is True


# ---------------------------------------------------------------------------
# Known false-positive blocker resolution
# ---------------------------------------------------------------------------


def test_known_fp_blockers_ok_when_human_needed_absent(tmp_path: Path) -> None:
    crit = adr._criterion_known_false_positive_blockers_resolved(
        human_needed_path=tmp_path / "no_such_human_needed.json"
    )
    assert crit["result"] == "OK"
    assert crit["human_needed_available"] is False
    assert crit["still_present_ids"] == []


def test_known_fp_blockers_ok_when_id_absent_from_events(
    tmp_path: Path,
) -> None:
    hn = tmp_path / "human_needed.json"
    hn.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "h_irrelevant",
                        "related_item": "p_unrelated",
                        "blocking_component": "x",
                        "reason": "y",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    crit = adr._criterion_known_false_positive_blockers_resolved(
        human_needed_path=hn
    )
    assert crit["result"] == "OK"
    assert crit["still_present_ids"] == []
    assert crit["current_event_count"] == 1


def test_known_fp_blockers_fail_when_id_still_present(
    tmp_path: Path,
) -> None:
    hn = tmp_path / "human_needed.json"
    hn.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "h_xxxxxxxxxx",
                        "related_item": "p_1f81cb23",
                        "blocking_component": "task_board",
                        "reason": "decision_cannot_be_inferred",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    crit = adr._criterion_known_false_positive_blockers_resolved(
        human_needed_path=hn
    )
    assert crit["result"] == "FAIL"
    assert "p_1f81cb23" in crit["still_present_ids"]


# ---------------------------------------------------------------------------
# State summarisation
# ---------------------------------------------------------------------------


def test_state_ok_when_all_criteria_ok() -> None:
    criteria = [
        {"criterion": "a", "result": "OK"},
        {"criterion": "b", "result": "OK"},
    ]
    assert adr._summarise_state(criteria) == "OK"


def test_state_blocked_when_any_fail() -> None:
    criteria = [
        {"criterion": "a", "result": "OK"},
        {"criterion": "b", "result": "FAIL"},
        {"criterion": "c", "result": "UNKNOWN"},
    ]
    assert adr._summarise_state(criteria) == "BLOCKED"


def test_state_unknown_when_no_fail_and_any_unknown() -> None:
    criteria = [
        {"criterion": "a", "result": "OK"},
        {"criterion": "b", "result": "UNKNOWN"},
    ]
    assert adr._summarise_state(criteria) == "UNKNOWN"


def test_handoff_lines_for_each_state() -> None:
    ok = adr._handoff_lines("OK")
    assert ok[0] == "Autonomous Development Track complete."
    assert any("v3.15.16 — Intelligent Routing Layer" in line for line in ok)
    assert any("Roadmap v6.md" in line for line in ok)
    blocked = adr._handoff_lines("BLOCKED")
    assert blocked[0] == "Autonomous Development Track BLOCKED."
    unknown = adr._handoff_lines("UNKNOWN")
    assert unknown[0].startswith("Autonomous Development Track readiness UNKNOWN")
    assert "CI is authoritative" in unknown[0]


# ---------------------------------------------------------------------------
# No mutation / no I/O guarantees
# ---------------------------------------------------------------------------


def test_collect_snapshot_does_not_invoke_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*a: Any, **kw: Any) -> Any:
        raise AssertionError("autonomous_dev_readiness invoked subprocess")

    monkeypatch.setattr(subprocess, "run", _raise)
    monkeypatch.setattr(subprocess, "Popen", _raise)
    snap = adr.collect_snapshot()
    assert snap["report_kind"] == "autonomous_dev_readiness"


def test_collect_snapshot_does_not_open_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*a: Any, **kw: Any) -> Any:
        raise AssertionError("autonomous_dev_readiness opened socket/url")

    monkeypatch.setattr(socket, "socket", _raise)
    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    adr.collect_snapshot()


def test_module_has_no_subprocess_or_gh_or_git_tokens() -> None:
    src = Path(adr.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for tok in forbidden:
        assert tok not in src, tok


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "research" / "leaked.json"
    with pytest.raises(ValueError, match="non-logs/"):
        adr._atomic_write_json(bad, {"x": 1})


def test_atomic_write_under_logs_succeeds(tmp_path: Path) -> None:
    out = tmp_path / "logs" / "autonomous_dev_readiness" / "latest.json"
    adr._atomic_write_json(out, {"hello": "world"})
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload == {"hello": "world"}


# ---------------------------------------------------------------------------
# End-to-end against the live repo (post-PR-4 state).
# ---------------------------------------------------------------------------


def test_live_readiness_state_is_ok_or_unknown_never_blocked() -> None:
    """In the post-PR-4 repo state, every criterion either passes
    or is informational-UNKNOWN. None should be BLOCKED. The CI
    marker is the only source of UNKNOWN locally."""
    snap = adr.collect_snapshot()
    assert snap["state"] in ("OK", "UNKNOWN"), snap["failing_criteria"]
    # If the state is UNKNOWN, the only acceptable contributor is the
    # classifier_tests_passing criterion (no local CI marker).
    if snap["state"] == "UNKNOWN":
        assert set(snap["unknown_criteria"]).issubset(
            {"classifier_tests_passing"}
        ), snap["unknown_criteria"]
