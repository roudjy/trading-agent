"""Unit tests for A11 — Bounded Roadmap Implementation Delegation.

Synthetic deterministic fixtures only. The pure marker parser
consumes only:

* explicit ``<!-- ade_delegation ... -->`` markers in the canonical
  roadmap docs;
* operator-authored entries in the sidecar
  ``docs/development_work_queue/delegation_seed.jsonl``.

Plain headings, prose, lists, and bullet points must produce zero
delegation entries. Archive paths are excluded. No fuzzy parsing.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_delegation as ddl
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_repo_root(tmp_path: Path) -> Path:
    """Create a synthetic repo-root with the two canonical roadmap
    paths so the parser can read them. Tests then write only the
    files they need; missing files become roadmap_paths_missing."""
    (tmp_path / "docs" / "roadmap").mkdir(parents=True)
    (tmp_path / "docs" / "development_work_queue").mkdir(parents=True)
    return tmp_path


def _write_canonical_doc(
    root: Path, name: str, body: str
) -> Path:
    p = root / "docs" / "roadmap" / name
    p.write_text(body, encoding="utf-8")
    return p


def _marker(**fields: Any) -> str:
    base = {
        "delegation_id": "syn_001",
        "title": "Add a synthetic ADE doc improvement",
        "category": "docs",
        "required_agent_role": "implementation_agent",
        "risk_level": "LOW",
        "human_needed": "false",
        "human_needed_reason": "none",
    }
    base.update({k: v for k, v in fields.items() if k != "acceptance_criteria"})
    ac = fields.get("acceptance_criteria", ["doc lands and lints clean"])
    lines = ["<!-- ade_delegation"]
    for key, val in base.items():
        lines.append(f"{key}: {val}")
    lines.append("acceptance_criteria:")
    for item in ac:
        lines.append(f"  - {item}")
    lines.append("-->")
    return "\n".join(lines)


def _seed_path(root: Path) -> Path:
    return root / "docs" / "development_work_queue" / "delegation_seed.jsonl"


def _write_sidecar(root: Path, lines: list[str]) -> Path:
    p = _seed_path(root)
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_canonical_roadmap_paths_match_doctrine() -> None:
    assert set(ddl.CANONICAL_ROADMAP_PATHS) == {
        "docs/roadmap/autonomous_development.txt",
        "docs/roadmap/Roadmap v6.md",
    }


def test_marker_required_fields_are_closed() -> None:
    assert ddl.MARKER_REQUIRED_FIELDS == frozenset(
        {
            "delegation_id",
            "title",
            "category",
            "required_agent_role",
            "risk_level",
            "acceptance_criteria",
            "human_needed",
            "human_needed_reason",
        }
    )


def test_entry_schema_keys_are_exact_and_ordered() -> None:
    assert ddl.ENTRY_SCHEMA_KEYS == (
        "delegation_id",
        "title",
        "source_document",
        "source_section_or_anchor",
        "roadmap_track",
        "category",
        "required_agent_role",
        "supporting_agent_roles",
        "execution_authority_decision",
        "execution_authority_reason",
        "status",
        "human_needed",
        "human_needed_reason",
        "risk_level",
        "protected_surface",
        "acceptance_criteria",
        "validation_requirements",
        "notes",
        "created_at_placeholder",
        "updated_at_placeholder",
    )


def test_artifact_path_is_under_logs_not_research() -> None:
    assert ddl.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in ddl.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        ddl._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    snap = ddl.collect_snapshot(
        repo_root=root,
        sidecar_seed_path=_seed_path(root),
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "canonical_roadmap_paths",
        "roadmap_paths_used",
        "roadmap_paths_missing",
        "sidecar_seed_path",
        "sidecar_seed_present",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "entries",
        "execution_authority_module_version",
        "queue_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_delegation"


def test_discipline_invariants_block_is_present(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_bugfix_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["fuzzy_parsing"] is False
    assert inv["operator_promotion_required"] is True


# ---------------------------------------------------------------------------
# False-positive guards (load-bearing)
# ---------------------------------------------------------------------------


def test_plain_markdown_headings_produce_zero_entries(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    body = """# Roadmap

## §A11

- some bullet
- another bullet

### Sub-section

prose explaining the section that contains the words `delegation` and `marker`
but is not inside a marker.
"""
    _write_canonical_doc(root, "autonomous_development.txt", body)
    _write_canonical_doc(root, "Roadmap v6.md", body)
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert snap["note"] == ddl.NOTE_NO_ENTRIES


def test_html_comment_without_ade_delegation_keyword_is_ignored(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    body = """<!-- this is a regular html comment -->
<!-- ade_delegation_lookalike: not the real opener -->
<!-- ade -->
"""
    _write_canonical_doc(root, "autonomous_development.txt", body)
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []


def test_archive_roadmap_paths_are_excluded(tmp_path: Path) -> None:
    """A roadmap path starting with docs/roadmap/archive/ must never
    be parsed even if the operator passes it explicitly."""
    root = _make_repo_root(tmp_path)
    archive_path = "docs/roadmap/archive/qre_roadmap_v6_1.md"
    (root / "docs" / "roadmap" / "archive").mkdir(parents=True)
    (root / archive_path).write_text(_marker(), encoding="utf-8")
    # Pass the archive path as a roadmap path; the module must
    # refuse it.
    snap = ddl.collect_snapshot(
        roadmap_paths=(archive_path,),
        sidecar_seed_path=_seed_path(root),
        repo_root=root,
    )
    assert snap["entries"] == []
    assert any("archive_path_excluded" in w for w in snap["validation_warnings"])


def test_non_canonical_roadmap_path_is_excluded(tmp_path: Path) -> None:
    """Any roadmap path outside the closed canonical set must be
    refused (defence in depth against accidental misuse)."""
    root = _make_repo_root(tmp_path)
    other_path = "docs/operator/some_other_doc.md"
    (root / "docs" / "operator").mkdir(parents=True)
    (root / other_path).write_text(_marker(), encoding="utf-8")
    snap = ddl.collect_snapshot(
        roadmap_paths=(other_path,),
        sidecar_seed_path=_seed_path(root),
        repo_root=root,
    )
    assert snap["entries"] == []
    assert any(
        "non_canonical_roadmap_path_excluded" in w
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Marker happy path
# ---------------------------------------------------------------------------


def test_valid_marker_in_canonical_doc_produces_entry(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        "## Some heading\n\n" + _marker() + "\n\nmore prose\n",
    )
    snap = ddl.collect_snapshot(
        repo_root=root,
        sidecar_seed_path=_seed_path(root),
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    assert snap["counts"]["total"] == 1
    entry = snap["entries"][0]
    assert set(entry.keys()) == set(ddl.ENTRY_SCHEMA_KEYS)
    assert entry["delegation_id"] == "syn_001"
    assert entry["roadmap_track"] == "autonomous_development"
    assert entry["status"] == ddl.DEFAULT_STATUS
    assert entry["category"] == "docs"
    assert entry["required_agent_role"] == "implementation_agent"
    assert entry["acceptance_criteria"] == ["doc lands and lints clean"]
    # Editing autonomous_development.txt is canonical_roadmap → NEEDS_HUMAN.
    assert entry["execution_authority_decision"] == ea.DECISION_NEEDS_HUMAN
    assert entry["protected_surface"] is True


def test_marker_in_qre_feature_build_track_uses_correct_track(
    tmp_path: Path,
) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(root, "Roadmap v6.md", _marker(delegation_id="syn_002"))
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"][0]["roadmap_track"] == "qre_feature_build"


# ---------------------------------------------------------------------------
# Marker validation — required fields and closed vocabularies
# ---------------------------------------------------------------------------


def test_missing_required_field_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    # Build a marker missing acceptance_criteria.
    body = (
        "<!-- ade_delegation\n"
        "delegation_id: syn_003\n"
        "title: missing AC\n"
        "category: docs\n"
        "required_agent_role: implementation_agent\n"
        "risk_level: LOW\n"
        "human_needed: false\n"
        "human_needed_reason: none\n"
        "-->\n"
    )
    _write_canonical_doc(root, "autonomous_development.txt", body)
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any("marker_missing_fields" in w for w in snap["validation_warnings"])


def test_invalid_category_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(category="not_a_category"),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any("invalid_category" in w for w in snap["validation_warnings"])


def test_invalid_role_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(required_agent_role="not_a_role"),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any(
        "invalid_required_agent_role" in w for w in snap["validation_warnings"]
    )


def test_invalid_risk_level_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root, "autonomous_development.txt", _marker(risk_level="EXTREME")
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any("invalid_risk_level" in w for w in snap["validation_warnings"])


def test_human_needed_consistency_with_reason_is_enforced(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(human_needed="true", human_needed_reason="none"),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any(
        "human_needed_true_but_reason_none" in w
        for w in snap["validation_warnings"]
    )


def test_invalid_delegation_id_drops_marker(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(delegation_id="bad id with spaces!"),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any("invalid_delegation_id" in w for w in snap["validation_warnings"])


# ---------------------------------------------------------------------------
# Sidecar seed
# ---------------------------------------------------------------------------


def test_empty_sidecar_seed_yields_zero_entries(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_sidecar(root, [])
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []


def test_valid_sidecar_seed_entry_round_trips(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    payload = {
        "delegation_id": "syn_sidecar_001",
        "title": "Synthetic sidecar work item",
        "category": "test",
        "required_agent_role": "test_agent",
        "risk_level": "LOW",
        "acceptance_criteria": ["test added", "ci green"],
        "human_needed": False,
        "human_needed_reason": "none",
    }
    _write_sidecar(root, [json.dumps(payload)])
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["counts"]["total"] == 1
    entry = snap["entries"][0]
    assert entry["roadmap_track"] == "sidecar_seed"
    assert entry["source_document"] == "delegation_seed"
    assert entry["status"] == ddl.DEFAULT_STATUS


def test_sidecar_seed_strict_jsonl_no_comments(tmp_path: Path) -> None:
    """Markdown headings or `#` comment lines in the sidecar are
    invalid JSONL; they must be reported and dropped."""
    root = _make_repo_root(tmp_path)
    _write_sidecar(
        root,
        [
            "# this is not valid JSONL",
            "## also not",
            "[just a bracket",
        ],
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["entries"] == []
    assert any("invalid_json" in w for w in snap["validation_warnings"])


def test_duplicate_delegation_id_is_dropped(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    payload = {
        "delegation_id": "dup_001",
        "title": "x",
        "category": "docs",
        "required_agent_role": "implementation_agent",
        "risk_level": "LOW",
        "acceptance_criteria": ["a"],
        "human_needed": False,
        "human_needed_reason": "none",
    }
    _write_sidecar(root, [json.dumps(payload), json.dumps(payload)])
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    assert snap["counts"]["total"] == 1
    assert any("duplicate_delegation_id" in w for w in snap["validation_warnings"])


def test_committed_repo_sidecar_is_strict_jsonl_or_absent() -> None:
    """The committed `docs/development_work_queue/delegation_seed.jsonl`
    must be either absent or strict JSONL — every non-blank line
    parses as JSON."""
    p = ddl.DEFAULT_SIDECAR_SEED_PATH
    if not p.is_file():
        return
    raw = p.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        assert not s.startswith("#"), "JSONL must not contain `#` comments"
        json.loads(s)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(root, "autonomous_development.txt", _marker())
    snap_a = ddl.collect_snapshot(
        repo_root=root,
        sidecar_seed_path=_seed_path(root),
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    snap_b = ddl.collect_snapshot(
        repo_root=root,
        sidecar_seed_path=_seed_path(root),
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    assert json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8") == json.dumps(
        snap_b, sort_keys=True, indent=2
    ).encode("utf-8")


def test_entries_sort_deterministically(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        "\n\n".join([_marker(delegation_id=f"id_{i}") for i in ("003", "001", "002")]),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    ids = [e["delegation_id"] for e in snap["entries"]]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_and_close_vocabularies(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(delegation_id="a"),
    )
    _write_canonical_doc(
        root,
        "Roadmap v6.md",
        _marker(
            delegation_id="b",
            human_needed="true",
            human_needed_reason="architecture_crossroads",
        ),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    counts = snap["counts"]
    assert counts["total"] == 2
    assert counts["human_needed"] == 1
    assert counts["protected_surface"] == 2
    assert sum(counts["by_roadmap_track"].values()) == 2
    assert sum(counts["by_required_agent_role"].values()) == 2


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(ddl.__file__).read_text(encoding="utf-8")


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
    importlib.reload(ddl)
    assert callable(ddl.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(ddl.SCHEMA_VERSION, str) and ddl.SCHEMA_VERSION
    assert isinstance(ddl.MODULE_VERSION, str) and ddl.MODULE_VERSION
    assert "A11" in ddl.MODULE_VERSION


def test_human_needed_reasons_used_are_subset_of_a8(tmp_path: Path) -> None:
    """Every reason A11 emits must be in the A8 closed vocabulary."""
    root = _make_repo_root(tmp_path)
    _write_canonical_doc(
        root,
        "autonomous_development.txt",
        _marker(
            human_needed="true",
            human_needed_reason="protected_governance_change",
        ),
    )
    snap = ddl.collect_snapshot(
        repo_root=root, sidecar_seed_path=_seed_path(root)
    )
    for e in snap["entries"]:
        assert e["human_needed_reason"] in dwq.HUMAN_NEEDED_REASONS
