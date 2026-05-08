"""Unit tests for Step 5.0.1 — Roadmap Intake Bridge.

Synthetic deterministic fixtures only. The pure marker parser
consumes only explicit ``<!-- ade_roadmap_intake ... -->`` markers
inside the four canonical source documents:

* ``docs/roadmap/Roadmap v6.md``
* ``docs/roadmap/Roadmap v6 Addendum.md``
* ``docs/roadmap/qre_roadmap_v6_phase_prompts.md``
* ``docs/roadmap/qre_roadmap_v6_ade_operating_manual.md``

Plain Markdown headings, prose, lists, and bullet points must produce
zero candidates. Archive paths are excluded. No fuzzy parsing, no
LLM, no network, no subprocess.

Step 5 implementation remains BLOCKED:
``step5_implementation_allowed`` is ``False`` and
``STEP5_ENABLED_SUBSTAGE`` is ``"none"``.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_roadmap_intake as dri
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_repo_root(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "roadmap").mkdir(parents=True)
    return tmp_path


def _write_source_doc(root: Path, name: str, body: str) -> Path:
    p = root / "docs" / "roadmap" / name
    p.write_text(body, encoding="utf-8")
    return p


def _marker(**fields: Any) -> str:
    base = {
        "candidate_id": "syn_intake_001",
        "phase": "v3.15.16",
        "title": "Add a synthetic ADE intake doc improvement",
        "category": "docs",
        "required_agent_role": "implementation_agent",
        "risk_level": "LOW",
        "target_path": "docs/governance/agent_run_summaries/syn_intake.md",
        "human_needed": "false",
        "human_needed_reason": "none",
    }
    base.update({k: v for k, v in fields.items() if k != "acceptance_criteria"})
    ac = fields.get("acceptance_criteria", ["candidate appears in latest.json"])
    lines = ["<!-- ade_roadmap_intake"]
    for key, val in base.items():
        lines.append(f"{key}: {val}")
    lines.append("acceptance_criteria:")
    for item in ac:
        lines.append(f"  - {item}")
    lines.append("-->")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_source_kinds_are_closed() -> None:
    assert dri.SOURCE_KINDS == (
        "roadmap_v6",
        "roadmap_v6_addendum",
        "phase_prompt",
        "operating_manual",
    )


def test_candidate_kinds_are_closed() -> None:
    assert dri.CANDIDATE_KINDS == (
        "docs",
        "reporting",
        "governance",
        "observability",
        "test",
    )


def test_intake_statuses_are_closed() -> None:
    assert dri.INTAKE_STATUSES == (
        "proposed",
        "eligible",
        "blocked",
        "human_needed",
        "rejected",
    )


def test_promotion_targets_are_closed() -> None:
    assert dri.PROMOTION_TARGETS == (
        "development_delegation",
        "development_work_queue",
        "none",
    )


def test_canonical_source_paths_match_doctrine() -> None:
    assert set(dri.SOURCE_PATH_TO_KIND.keys()) == {
        "docs/roadmap/Roadmap v6.md",
        "docs/roadmap/Roadmap v6 Addendum.md",
        "docs/roadmap/qre_roadmap_v6_phase_prompts.md",
        "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
    }


def test_default_source_paths_are_sorted_and_complete() -> None:
    assert dri.DEFAULT_SOURCE_PATHS == tuple(sorted(dri.SOURCE_PATH_TO_KIND.keys()))


def test_marker_required_fields_are_closed() -> None:
    assert dri.MARKER_REQUIRED_FIELDS == frozenset(
        {
            "candidate_id",
            "phase",
            "title",
            "category",
            "required_agent_role",
            "risk_level",
            "target_path",
            "human_needed",
            "human_needed_reason",
            "acceptance_criteria",
        }
    )


def test_candidate_schema_keys_are_exact_and_ordered() -> None:
    assert dri.CANDIDATE_SCHEMA_KEYS == (
        "candidate_id",
        "title",
        "source_document",
        "source_anchor",
        "roadmap_phase",
        "source_kind",
        "candidate_kind",
        "category",
        "required_agent_role",
        "risk_level",
        "target_path",
        "execution_authority_decision",
        "execution_authority_reason",
        "human_needed",
        "human_needed_reason",
        "intake_status",
        "acceptance_criteria",
        "validation_requirements",
        "promotion_target",
        "notes",
    )


def test_artifact_path_is_under_logs_not_research() -> None:
    assert dri.ARTIFACT_RELATIVE_PATH.startswith(
        "logs/development_roadmap_intake/"
    )
    assert "research/" not in dri.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_intake_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dri._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_non_intake_logs_path_within_logs(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "logs" / "some_other_module" / "latest.json"
    with pytest.raises(ValueError):
        dri._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Step 5 invariants on every snapshot
# ---------------------------------------------------------------------------


def test_step5_invariants_pinned() -> None:
    assert dri.step5_implementation_allowed is False
    assert dri.STEP5_ENABLED_SUBSTAGE == "none"


def test_snapshot_carries_step5_invariants(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["step5_enabled_substage"] == "none"
    assert snap["step5_implementation_allowed"] is False


def test_discipline_invariants_block_is_present(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    snap = dri.collect_snapshot(repo_root=root)
    inv = snap["discipline_invariants"]
    assert inv["actually_modifies_target"] is False
    assert inv["creates_real_branches"] is False
    assert inv["opens_real_prs"] is False
    assert inv["mergeable_by_agent"] is False
    assert inv["deployable_by_agent"] is False
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["fuzzy_parsing"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["calls_llm_or_external_api"] is False
    assert inv["mutates_research_artifacts"] is False
    assert inv["mutates_roadmap_status_fields"] is False
    assert inv["marks_phase_complete"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["diagnostics_do_not_trade"] is True


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "canonical_source_paths",
        "source_paths_used",
        "source_paths_missing",
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
    assert snap["report_kind"] == "development_roadmap_intake"


# ---------------------------------------------------------------------------
# False-positive guards (load-bearing)
# ---------------------------------------------------------------------------


def test_plain_markdown_headings_produce_zero_candidates(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    body = """# Roadmap

## v3.15.16

- some bullet
- another bullet

### Sub-section

prose explaining the section that contains the words `roadmap_intake`,
`candidate`, and `marker` but is not inside a marker.
"""
    _write_source_doc(root, "Roadmap v6.md", body)
    _write_source_doc(root, "Roadmap v6 Addendum.md", body)
    _write_source_doc(root, "qre_roadmap_v6_phase_prompts.md", body)
    _write_source_doc(root, "qre_roadmap_v6_ade_operating_manual.md", body)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert snap["note"] == dri.NOTE_NO_CANDIDATES


def test_html_comment_without_intake_keyword_is_ignored(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    body = """<!-- this is a regular html comment -->
<!-- ade_roadmap_intake_lookalike: not the real opener -->
<!-- ade_delegation
delegation_id: not_intake
title: not the right marker
-->
<!-- ade_intake -->
"""
    _write_source_doc(root, "Roadmap v6.md", body)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []


def test_archive_source_paths_are_excluded(tmp_path: Path) -> None:
    """A roadmap path under docs/roadmap/archive/ must never be parsed
    even if the operator passes it explicitly."""
    root = _make_repo_root(tmp_path)
    archive_path = "docs/roadmap/archive/qre_roadmap_v6_1.md"
    (root / "docs" / "roadmap" / "archive").mkdir(parents=True)
    (root / archive_path).write_text(_marker(), encoding="utf-8")
    snap = dri.collect_snapshot(
        source_paths=(archive_path,),
        repo_root=root,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["candidates"] == []
    assert any(
        "archive_path_excluded" in w for w in snap["validation_warnings"]
    )


def test_non_canonical_source_path_is_excluded(tmp_path: Path) -> None:
    """Any source path outside the closed canonical set must be
    refused (defence in depth against accidental misuse)."""
    root = _make_repo_root(tmp_path)
    other_path = "docs/operator/some_other_doc.md"
    (root / "docs" / "operator").mkdir(parents=True)
    (root / other_path).write_text(_marker(), encoding="utf-8")
    snap = dri.collect_snapshot(
        source_paths=(other_path,),
        repo_root=root,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["candidates"] == []
    assert any(
        "non_canonical_source_path_excluded" in w
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Marker happy path
# ---------------------------------------------------------------------------


def test_valid_marker_in_addendum_produces_eligible_candidate(
    tmp_path: Path,
) -> None:
    """An AUTO_ALLOWED target_path on a non-protected docs path
    classifies as eligible."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        "## Some heading\n\n" + _marker() + "\n\nmore prose\n",
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["counts"]["total"] == 1
    cand = snap["candidates"][0]
    assert set(cand.keys()) == set(dri.CANDIDATE_SCHEMA_KEYS)
    assert cand["candidate_id"] == "syn_intake_001"
    assert cand["source_kind"] == "roadmap_v6_addendum"
    assert cand["roadmap_phase"] == "v3.15.16"
    assert cand["candidate_kind"] == "docs"
    assert cand["category"] == "docs"
    assert cand["required_agent_role"] == "implementation_agent"
    assert cand["risk_level"] == "LOW"
    assert cand["target_path"] == "docs/governance/agent_run_summaries/syn_intake.md"
    assert cand["execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED
    assert cand["intake_status"] == "eligible"
    assert cand["human_needed"] is False
    assert cand["human_needed_reason"] == "none"
    assert cand["acceptance_criteria"] == ["candidate appears in latest.json"]
    assert cand["promotion_target"] == "none"


def test_marker_in_phase_prompts_uses_correct_source_kind(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "qre_roadmap_v6_phase_prompts.md",
        _marker(candidate_id="syn_phase_001"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"][0]["source_kind"] == "phase_prompt"


def test_marker_in_operating_manual_uses_correct_source_kind(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "qre_roadmap_v6_ade_operating_manual.md",
        _marker(candidate_id="syn_om_001"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"][0]["source_kind"] == "operating_manual"


def test_marker_in_roadmap_v6_uses_correct_source_kind(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6.md",
        _marker(candidate_id="syn_v6_001"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"][0]["source_kind"] == "roadmap_v6"


# ---------------------------------------------------------------------------
# Authority classification edges
# ---------------------------------------------------------------------------


def test_protected_target_path_becomes_human_needed(tmp_path: Path) -> None:
    """A canonical roadmap target_path classifies as NEEDS_HUMAN, so
    intake_status must be human_needed (not eligible)."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(
            candidate_id="syn_protected_001",
            target_path="docs/roadmap/Roadmap v6.md",
            risk_level="MEDIUM",
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    cand = snap["candidates"][0]
    assert cand["execution_authority_decision"] == ea.DECISION_NEEDS_HUMAN
    assert cand["intake_status"] == "human_needed"


def test_frozen_contract_target_path_becomes_blocked(tmp_path: Path) -> None:
    """A frozen-contract target_path classifies as PERMANENTLY_DENIED,
    so intake_status must be blocked."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(
            candidate_id="syn_blocked_001",
            target_path="research/research_latest.json",
            risk_level="HIGH",
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    cand = snap["candidates"][0]
    assert cand["execution_authority_decision"] == ea.DECISION_PERMANENTLY_DENIED
    assert cand["intake_status"] == "blocked"


def test_human_needed_true_overrides_auto_allowed(tmp_path: Path) -> None:
    """If the operator marked human_needed=true, intake_status must
    be human_needed regardless of the authority decision."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(
            candidate_id="syn_hn_001",
            human_needed="true",
            human_needed_reason="architecture_crossroads",
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    cand = snap["candidates"][0]
    assert cand["intake_status"] == "human_needed"
    assert cand["human_needed"] is True
    # The underlying authority decision can still be AUTO_ALLOWED on
    # a non-protected docs target — but the status flips on
    # operator-explicit human_needed=true.
    assert cand["execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED


# ---------------------------------------------------------------------------
# Marker validation — required fields and closed vocabularies
# ---------------------------------------------------------------------------


def test_missing_required_field_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    body = (
        "<!-- ade_roadmap_intake\n"
        "candidate_id: syn_missing_ac\n"
        "phase: v3.15.16\n"
        "title: missing AC\n"
        "category: docs\n"
        "required_agent_role: implementation_agent\n"
        "risk_level: LOW\n"
        "target_path: docs/governance/x.md\n"
        "human_needed: false\n"
        "human_needed_reason: none\n"
        "-->\n"
    )
    _write_source_doc(root, "Roadmap v6 Addendum.md", body)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "marker_missing_fields" in w for w in snap["validation_warnings"]
    )


def test_invalid_category_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(category="not_a_kind"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any("invalid_category" in w for w in snap["validation_warnings"])


def test_invalid_role_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(required_agent_role="not_a_role"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "invalid_required_agent_role" in w for w in snap["validation_warnings"]
    )


def test_invalid_risk_level_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root, "Roadmap v6 Addendum.md", _marker(risk_level="EXTREME")
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "invalid_risk_level" in w for w in snap["validation_warnings"]
    )


def test_human_needed_consistency_with_reason_is_enforced(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(human_needed="true", human_needed_reason="none"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "human_needed_true_but_reason_none" in w
        for w in snap["validation_warnings"]
    )


def test_invalid_candidate_id_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(candidate_id="bad id with spaces!"),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "invalid_candidate_id" in w for w in snap["validation_warnings"]
    )


def test_missing_target_path_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(target_path=""),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert any(
        "missing_target_path" in w for w in snap["validation_warnings"]
    )


def test_invalid_marker_does_not_crash(tmp_path: Path) -> None:
    """A wholly malformed marker must produce a validation_warning
    rather than raising an exception."""
    root = _make_repo_root(tmp_path)
    body = (
        "<!-- ade_roadmap_intake\n"
        "this line has no colon\n"
        "neither does this one\n"
        "-->\n"
    )
    _write_source_doc(root, "Roadmap v6 Addendum.md", body)
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["candidates"] == []
    assert snap["validation_warnings"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(root, "Roadmap v6 Addendum.md", _marker())
    snap_a = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    snap_b = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    a_bytes = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    b_bytes = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert a_bytes == b_bytes


def test_candidates_sort_deterministically(tmp_path: Path) -> None:
    """Order is (source_kind, candidate_id) ascending."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        "\n\n".join(
            [
                _marker(candidate_id=f"id_{i}")
                for i in ("003", "001", "002")
            ]
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    ids = [c["candidate_id"] for c in snap["candidates"]]
    assert ids == sorted(ids)


def test_duplicate_candidate_id_within_same_doc_is_dropped(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        "\n\n".join([_marker(candidate_id="dup_001")] * 2),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    assert snap["counts"]["total"] == 1
    assert any(
        "duplicate_candidate_id" in w for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_and_close_vocabularies(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6.md",
        _marker(candidate_id="a"),
    )
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(
            candidate_id="b",
            human_needed="true",
            human_needed_reason="architecture_crossroads",
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    counts = snap["counts"]
    assert counts["total"] == 2
    assert counts["human_needed"] == 1
    assert sum(counts["by_source_kind"].values()) == 2
    assert sum(counts["by_candidate_kind"].values()) == 2
    assert sum(counts["by_intake_status"].values()) == 2
    assert sum(counts["by_execution_authority_decision"].values()) == 2
    # Eligible (auto-allowed, not human_needed) vs human_needed.
    assert counts["eligible"] == 1
    assert counts["by_intake_status"]["human_needed"] == 1


def test_human_needed_reasons_are_subset_of_a8(tmp_path: Path) -> None:
    """Every reason emitted must be in the A8 closed vocabulary."""
    root = _make_repo_root(tmp_path)
    _write_source_doc(
        root,
        "Roadmap v6 Addendum.md",
        _marker(
            human_needed="true",
            human_needed_reason="protected_governance_change",
        ),
    )
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    for c in snap["candidates"]:
        assert c["human_needed_reason"] in dwq.HUMAN_NEEDED_REASONS


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dri.__file__).read_text(encoding="utf-8")


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
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
        "shell=True",
    ):
        assert forbidden not in src, forbidden


def test_no_llm_or_external_api_calls() -> None:
    """No anthropic / openai / requests / httpx imports."""
    src = _module_source()
    for forbidden in (
        "anthropic",
        "openai",
        "import requests",
        "import httpx",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(dri)
    assert callable(dri.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(dri.SCHEMA_VERSION, str) and dri.SCHEMA_VERSION
    assert isinstance(dri.MODULE_VERSION, str) and dri.MODULE_VERSION


# ---------------------------------------------------------------------------
# Roadmap v6 Addendum extension framing preserved in docs
# ---------------------------------------------------------------------------


def test_governance_doc_preserves_addendum_extension_framing() -> None:
    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "governance"
        / "development_roadmap_intake.md"
    )
    text = doc.read_text(encoding="utf-8").lower()
    assert "extension" in text
    assert "roadmap v6" in text
    assert "addendum" in text
    assert "canonical" in text


def test_governance_doc_pins_no_step5_escalation() -> None:
    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "governance"
        / "development_roadmap_intake.md"
    )
    text = doc.read_text(encoding="utf-8").lower()
    assert "step5_implementation_allowed" in text
    assert "step5_enabled_substage" in text
    assert "no step 5.1" in text or "no step 5.1, no step 5.2" in text


# ---------------------------------------------------------------------------
# Production-doc safety (the committed canonical sources must not yet
# contain explicit intake markers — we want this PR's diff to be
# deterministic and to land without polluting roadmap docs).
# ---------------------------------------------------------------------------


def test_committed_canonical_sources_have_no_unparseable_markers() -> None:
    """If any of the four canonical sources happen to contain real
    `<!-- ade_roadmap_intake ... -->` markers, every one must parse
    cleanly. This test is tolerant of zero markers (the default) and
    strict on validation warnings only when markers exist."""
    root = Path(__file__).resolve().parents[2]
    snap = dri.collect_snapshot(
        repo_root=root, generated_at_utc="2026-05-08T00:00:00Z"
    )
    parse_warns = [
        w
        for w in snap["validation_warnings"]
        if "marker" in w
        and "non_canonical_source_path_excluded" not in w
        and "archive_path_excluded" not in w
    ]
    if snap["candidates"]:
        # If we've already begun seeding markers, none of them may be
        # malformed.
        assert not parse_warns, parse_warns
