"""Unit tests for A10 — Agentic Bugfix Loop.

Synthetic deterministic fixtures only. The pure intake module reads
a structured failure-summary contract and emits bugfix-candidate
proposals to ``logs/development_bugfix_loop/latest.json``. The
module never writes to ``seed.jsonl`` or ``bugfix_seed.jsonl``;
operator promotion is a separate manual action.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_bugfix_loop as dbl
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _input_path(tmp_path: Path) -> Path:
    return tmp_path / "failures.json"


def _failure(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "failure_class": "unit_test",
        "target_path": "reporting/foo.py",
        "message_digest": "abc123",
        "severity": "low",
        "occurrence_count": 1,
        "first_seen_utc": "2026-05-07T00:00:00Z",
        "last_seen_utc": "2026-05-07T00:00:00Z",
        "detail": "AssertionError: 1 != 2",
    }
    base.update(overrides)
    return base


def _write_input(tmp_path: Path, failures: list[dict[str, Any]]) -> Path:
    p = _input_path(tmp_path)
    p.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at_utc": "2026-05-07T00:00:00Z",
                "failures": failures,
            }
        ),
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Vocabulary integrity
# ---------------------------------------------------------------------------


def test_failure_classes_vocabulary_is_closed_and_ordered() -> None:
    assert dbl.FAILURE_CLASSES == (
        "unit_test",
        "smoke_test",
        "regression_test",
        "lint",
        "typecheck",
        "governance_lint",
        "frozen_hash",
        "hook",
        "ci_workflow",
        "unknown",
    )
    assert len(dbl.FAILURE_CLASSES) == 10


def test_bugfix_scopes_vocabulary_is_closed_and_ordered() -> None:
    assert dbl.BUGFIX_SCOPES == (
        "bounded_in_repo",
        "protected_path",
        "live_path",
        "frozen_contract",
        "ci_only",
        "requires_architecture_review",
        "out_of_scope",
    )
    assert len(dbl.BUGFIX_SCOPES) == 7


def test_input_severities_vocabulary_is_closed() -> None:
    assert dbl.INPUT_SEVERITIES == ("low", "medium", "high", "unknown")


def test_suggested_statuses_subset_of_a8_kanban() -> None:
    assert set(dbl.SUGGESTED_STATUSES).issubset(set(dwq.STATUSES))


def test_role_and_category_maps_cover_all_failure_classes() -> None:
    assert set(dbl.ROLE_BY_FAILURE_CLASS) == set(dbl.FAILURE_CLASSES)
    assert set(dbl.CATEGORY_BY_FAILURE_CLASS) == set(dbl.FAILURE_CLASSES)
    for v in dbl.ROLE_BY_FAILURE_CLASS.values():
        assert v in dwq.AGENT_ROLES
    for v in dbl.CATEGORY_BY_FAILURE_CLASS.values():
        assert v in dwq.CATEGORIES


def test_acceptance_templates_cover_all_failure_classes() -> None:
    assert set(dbl.ACCEPTANCE_TEMPLATES) == set(dbl.FAILURE_CLASSES)


def test_candidate_schema_keys_are_exact_and_ordered() -> None:
    assert dbl.CANDIDATE_SCHEMA_KEYS == (
        "candidate_id",
        "failure_class",
        "target_path",
        "target_path_category",
        "bugfix_scope",
        "suggested_status",
        "suggested_required_agent_role",
        "suggested_category",
        "human_needed",
        "human_needed_reason",
        "execution_authority_decision",
        "execution_authority_reason",
        "repeat_count",
        "first_seen_utc",
        "last_seen_utc",
        "severity",
        "acceptance_criteria_template",
        "notes",
        "created_at_placeholder",
        "updated_at_placeholder",
    )


# ---------------------------------------------------------------------------
# Test-weakening discipline (pinned)
# ---------------------------------------------------------------------------


def test_acceptance_templates_never_contain_test_weakening_tokens() -> None:
    """No safe template may contain skip/xfail/pin removal/weaken/
    relax/disable. This is the core test-weakening invariant."""
    for fc, templates in dbl.ACCEPTANCE_TEMPLATES.items():
        for line in templates:
            lowered = line.lower()
            for forbidden in dbl.FORBIDDEN_ACCEPTANCE_TOKENS:
                assert forbidden not in lowered, (
                    f"failure_class={fc!r}: template contains "
                    f"forbidden token {forbidden!r}: {line!r}"
                )


def test_forbidden_acceptance_tokens_set_is_meaningful() -> None:
    assert "skip" in dbl.FORBIDDEN_ACCEPTANCE_TOKENS
    assert "xfail" in dbl.FORBIDDEN_ACCEPTANCE_TOKENS
    assert "remove pin" in dbl.FORBIDDEN_ACCEPTANCE_TOKENS
    assert "weaken" in dbl.FORBIDDEN_ACCEPTANCE_TOKENS


# ---------------------------------------------------------------------------
# Artifact path discipline
# ---------------------------------------------------------------------------


def test_artifact_path_is_under_logs_not_research() -> None:
    assert dbl.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in dbl.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dbl._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_seed_jsonl_paths(tmp_path: Path) -> None:
    """The bugfix loop must never write to either seed.jsonl or
    bugfix_seed.jsonl, even by mistake. The atomic write enforces a
    logs/-only whitelist; these paths fall outside logs/."""
    seed = tmp_path / "docs" / "development_work_queue" / "seed.jsonl"
    bugfix_seed = tmp_path / "docs" / "development_work_queue" / "bugfix_seed.jsonl"
    with pytest.raises(ValueError):
        dbl._atomic_write_json(seed, {"x": 1})
    with pytest.raises(ValueError):
        dbl._atomic_write_json(bugfix_seed, {"x": 1})


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [_failure()])
    snap = dbl.collect_snapshot(
        failure_input_path=fp, generated_at_utc="2026-05-07T00:00:00Z"
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "failure_input_path",
        "failure_input_present",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "candidates",
        "execution_authority_module_version",
        "queue_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_bugfix_loop"
    assert snap["failure_input_present"] is True


def test_input_absent_yields_empty_snapshot(tmp_path: Path) -> None:
    fp = tmp_path / "missing.json"
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["failure_input_present"] is False
    assert snap["note"] == dbl.NOTE_INPUT_ABSENT
    assert snap["candidates"] == []


def test_empty_failures_list_yields_input_empty_note(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["failure_input_present"] is True
    assert snap["note"] == dbl.NOTE_INPUT_EMPTY
    assert snap["candidates"] == []


def test_discipline_invariants_block_is_present(tmp_path: Path) -> None:
    """The wrapper carries an explicit discipline-invariants block so
    operators can audit at a glance that the module did not violate
    its own rules."""
    fp = _write_input(tmp_path, [_failure()])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_bugfix_seed_jsonl"] is False
    assert inv["auto_creates_branches"] is False
    assert inv["auto_opens_prs"] is False
    assert inv["auto_modifies_code"] is False
    assert inv["operator_promotion_required"] is True


# ---------------------------------------------------------------------------
# Classification — happy paths and overrides
# ---------------------------------------------------------------------------


def test_unit_test_failure_in_reporting_module_is_bounded_in_repo(
    tmp_path: Path,
) -> None:
    fp = _write_input(tmp_path, [_failure(target_path="reporting/foo.py")])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["failure_class"] == "unit_test"
    assert cand["target_path_category"] == "reporting_module"
    assert cand["bugfix_scope"] == "bounded_in_repo"
    assert cand["human_needed"] is False
    assert cand["suggested_status"] == "proposed"
    assert cand["suggested_required_agent_role"] == "test_agent"
    assert cand["suggested_category"] == "test"


def test_frozen_contract_failure_always_human_needed(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(
                failure_class="frozen_hash",
                target_path="research/research_latest.json",
            )
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["bugfix_scope"] == "frozen_contract"
    assert cand["human_needed"] is True
    assert cand["human_needed_reason"] == "frozen_contract_change"


def test_live_path_failure_always_human_needed(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [_failure(failure_class="lint", target_path="broker/whatever.py")],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["bugfix_scope"] == "live_path"
    assert cand["human_needed"] is True
    assert cand["human_needed_reason"] == "capital_or_live_execution_related"


def test_canonical_policy_doc_failure_is_protected_path(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(
                failure_class="governance_lint",
                target_path="docs/governance/execution_authority.md",
            )
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["bugfix_scope"] == "protected_path"
    assert cand["human_needed"] is True
    assert cand["human_needed_reason"] == "protected_governance_change"


def test_claude_governance_hook_failure_is_protected_path(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [_failure(failure_class="hook", target_path=".claude/hooks/foo.py")],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["bugfix_scope"] == "protected_path"
    assert cand["human_needed"] is True


def test_ci_workflow_failure_is_ci_only_human_needed(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(
                failure_class="ci_workflow",
                target_path=".github/workflows/tests.yml",
            )
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["bugfix_scope"] == "ci_only"
    assert cand["human_needed"] is True
    assert cand["suggested_required_agent_role"] == "ci_guardian"


def test_other_target_falls_back_to_requires_architecture_review(
    tmp_path: Path,
) -> None:
    fp = _write_input(
        tmp_path,
        [_failure(target_path="some/random/script.py")],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["target_path_category"] == "other"
    assert cand["bugfix_scope"] == "requires_architecture_review"
    assert cand["human_needed"] is True
    assert cand["human_needed_reason"] == "ambiguous_scope"


# ---------------------------------------------------------------------------
# Repeated failure escalation
# ---------------------------------------------------------------------------


def test_repeated_failure_escalates_to_human_needed(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(
                target_path="reporting/foo.py",
                occurrence_count=dbl.REPEATED_FAILURE_THRESHOLD,
            )
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["human_needed"] is True
    assert cand["human_needed_reason"] == "repeated_validation_failure"
    assert cand["repeat_count"] == dbl.REPEATED_FAILURE_THRESHOLD
    assert cand["suggested_status"] == "human_needed"


def test_below_threshold_repeat_count_does_not_escalate(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(
                target_path="reporting/foo.py",
                occurrence_count=dbl.REPEATED_FAILURE_THRESHOLD - 1,
            )
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    cand = snap["candidates"][0]
    assert cand["human_needed"] is False
    assert cand["suggested_status"] == "proposed"


# ---------------------------------------------------------------------------
# Invalid input handling
# ---------------------------------------------------------------------------


def test_invalid_failure_class_is_dropped_with_warning(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [_failure(failure_class="not_a_class")])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["candidates"] == []
    assert any("invalid_failure_class" in w for w in snap["validation_warnings"])


def test_failure_record_not_an_object_is_dropped(tmp_path: Path) -> None:
    fp = _input_path(tmp_path)
    fp.write_text(
        json.dumps({"schema_version": "1.0", "failures": ["not-an-object"]}),
        encoding="utf-8",
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["candidates"] == []
    assert any("not_an_object" in w for w in snap["validation_warnings"])


def test_failures_not_a_list_emits_warning(tmp_path: Path) -> None:
    fp = _input_path(tmp_path)
    fp.write_text(
        json.dumps({"schema_version": "1.0", "failures": "oops"}),
        encoding="utf-8",
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["candidates"] == []
    assert any(
        "input_failures_not_a_list" in w for w in snap["validation_warnings"]
    )


def test_unknown_severity_coerces_to_unknown(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [_failure(severity="critical")])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert snap["candidates"][0]["severity"] == "unknown"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_candidate_id_is_deterministic_for_same_failure(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [_failure()])
    snap_a = dbl.collect_snapshot(
        failure_input_path=fp, generated_at_utc="2026-05-07T00:00:00Z"
    )
    snap_b = dbl.collect_snapshot(
        failure_input_path=fp, generated_at_utc="2026-05-07T00:00:00Z"
    )
    assert snap_a["candidates"][0]["candidate_id"] == snap_b["candidates"][0]["candidate_id"]
    assert snap_a["candidates"][0]["candidate_id"].startswith("bug_")


def test_artifact_bytes_are_deterministic_with_injected_timestamp(
    tmp_path: Path,
) -> None:
    fp = _write_input(tmp_path, [_failure(), _failure(message_digest="def456")])
    snap_a = dbl.collect_snapshot(
        failure_input_path=fp, generated_at_utc="2026-05-07T00:00:00Z"
    )
    snap_b = dbl.collect_snapshot(
        failure_input_path=fp, generated_at_utc="2026-05-07T00:00:00Z"
    )
    assert json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8") == json.dumps(
        snap_b, sort_keys=True, indent=2
    ).encode("utf-8")


def test_duplicate_candidates_collapse_keeping_max_repeat_count(
    tmp_path: Path,
) -> None:
    """Same failure_class + target_path + message_digest yields the
    same candidate_id; the loop collapses duplicates and keeps the
    higher repeat_count."""
    fp = _write_input(
        tmp_path,
        [
            _failure(occurrence_count=2),
            _failure(occurrence_count=5),
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    assert len(snap["candidates"]) == 1
    assert snap["candidates"][0]["repeat_count"] == 5


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_and_close_vocabularies(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(target_path="reporting/foo.py", message_digest="a"),
            _failure(
                failure_class="frozen_hash",
                target_path="research/strategy_matrix.csv",
                message_digest="b",
            ),
            _failure(
                failure_class="ci_workflow",
                target_path=".github/workflows/tests.yml",
                message_digest="c",
            ),
            _failure(
                target_path="reporting/bar.py",
                message_digest="d",
                occurrence_count=10,
            ),
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    counts = snap["counts"]
    assert counts["total"] == 4
    assert sum(counts["by_failure_class"].values()) == 4
    assert sum(counts["by_bugfix_scope"].values()) == 4
    assert sum(counts["by_suggested_status"].values()) == 4
    assert counts["human_needed"] >= 3
    assert counts["repeated_failure"] >= 1
    assert counts["ready_for_operator_promotion"] + counts["requiring_human_operator"] == 4
    assert set(counts["by_failure_class"]) == set(dbl.FAILURE_CLASSES)
    assert set(counts["by_bugfix_scope"]) == set(dbl.BUGFIX_SCOPES)


# ---------------------------------------------------------------------------
# Candidate sorting
# ---------------------------------------------------------------------------


def test_candidates_sort_deterministically(tmp_path: Path) -> None:
    fp = _write_input(
        tmp_path,
        [
            _failure(message_digest="zzz"),
            _failure(message_digest="aaa"),
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    ids = [c["candidate_id"] for c in snap["candidates"]]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dbl.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
    ):
        assert forbidden not in src
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src
    assert "from requests" not in src


def test_no_test_runner_imports_in_module() -> None:
    """A10 must not import pytest or other test runners — it consumes
    structured failure summaries, never runs tests itself."""
    forbidden_modules = ("pytest", "_pytest", "unittest")
    for module in _imported_module_names():
        assert module.split(".")[0] not in forbidden_modules, module


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (module == prefix or module.startswith(prefix + ".")), (
                f"forbidden import: {module}"
            )


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(dbl)
    assert callable(dbl.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(dbl.SCHEMA_VERSION, str) and dbl.SCHEMA_VERSION
    assert isinstance(dbl.MODULE_VERSION, str) and dbl.MODULE_VERSION
    assert "A10" in dbl.MODULE_VERSION


# ---------------------------------------------------------------------------
# Cross-module sanity: A10 vocabularies do not overlap A8 vocabularies
# in incompatible ways
# ---------------------------------------------------------------------------


def test_human_needed_reasons_used_are_subset_of_a8(tmp_path: Path) -> None:
    """Every reason A10 emits must be in the A8 closed vocabulary."""
    fp = _write_input(
        tmp_path,
        [
            _failure(failure_class="frozen_hash", target_path="research/research_latest.json"),
            _failure(failure_class="lint", target_path="broker/x.py", message_digest="b"),
            _failure(failure_class="governance_lint", target_path="docs/governance/execution_authority.md", message_digest="c"),
            _failure(failure_class="lint", target_path="other/x.py", message_digest="d"),
            _failure(target_path="reporting/foo.py", occurrence_count=5, message_digest="e"),
        ],
    )
    snap = dbl.collect_snapshot(failure_input_path=fp)
    for c in snap["candidates"]:
        assert c["human_needed_reason"] in dwq.HUMAN_NEEDED_REASONS


def test_execution_authority_decision_is_classifier_value(tmp_path: Path) -> None:
    fp = _write_input(tmp_path, [_failure()])
    snap = dbl.collect_snapshot(failure_input_path=fp)
    decisions = {c["execution_authority_decision"] for c in snap["candidates"]}
    assert decisions.issubset(set(ea.DECISIONS))
