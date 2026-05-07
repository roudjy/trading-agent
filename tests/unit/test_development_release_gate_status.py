"""Unit tests for A9 — release-gate status summary.

Synthetic deterministic fixtures only. The module reads
``logs/development_release_gate/latest.json`` and emits a compact
operator-facing summary; it does not mutate the gate artifact.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_release_gate as drg
from reporting import development_release_gate_status as drgs


def _write_gate_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "gate.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_artifact_path_is_under_logs_not_research() -> None:
    assert drgs.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in drgs.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        drgs._atomic_write_json(bad, {"x": 1})


def test_status_top_level_keys_when_gate_artifact_absent(tmp_path: Path) -> None:
    qp = tmp_path / "missing.json"
    snap = drgs.collect_status(gate_artifact_path=qp, generated_at_utc="2026-05-07T00:00:00Z")
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "gate_artifact_path",
        "gate_artifact_available",
        "gate_module_version",
        "schema_pinned",
        "counts",
        "validation_warnings",
        "note",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_release_gate_status"
    assert snap["gate_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["note"] == "gate_artifact_absent"
    assert set(snap["schema_pinned"]) == {
        "verdicts",
        "verdict_reasons",
        "evidence_keys",
    }


# ---------------------------------------------------------------------------
# Counts pass-through and bucket completeness
# ---------------------------------------------------------------------------


def test_counts_pass_through_when_gate_artifact_present(tmp_path: Path) -> None:
    fake_gate = {
        "schema_version": "1.0",
        "module_version": drg.MODULE_VERSION,
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": drg.NOTE_VERDICTS_PRESENT,
        "evidence_input_present": True,
        "queue_artifact_present": True,
        "counts": {
            "total": 4,
            "human_needed": 1,
            "protected_surface": 1,
            "by_verdict": {v: 0 for v in drg.VERDICTS},
            "by_verdict_reason": {r: 0 for r in drg.VERDICT_REASONS},
        },
        "validation_warnings": ["item_x_missing_acceptance_criteria"],
    }
    fake_gate["counts"]["by_verdict"][drg.VERDICT_GO] = 2
    fake_gate["counts"]["by_verdict"][drg.VERDICT_GO_WITH_FOLLOWUPS] = 1
    fake_gate["counts"]["by_verdict"][drg.VERDICT_NO_GO_HUMAN_NEEDED] = 1
    fake_gate["counts"]["by_verdict_reason"]["all_required_evidence_clean"] = 2
    fake_gate["counts"]["by_verdict_reason"]["clean_with_advisory_followups"] = 1
    fake_gate["counts"]["by_verdict_reason"]["protected_surface_present"] = 1

    qp = _write_gate_artifact(tmp_path, fake_gate)
    snap = drgs.collect_status(gate_artifact_path=qp)

    assert snap["gate_artifact_available"] is True
    assert snap["counts"]["total"] == 4
    assert snap["counts"]["human_needed"] == 1
    assert snap["counts"]["protected_surface"] == 1
    assert snap["counts"]["by_verdict"][drg.VERDICT_GO] == 2
    assert snap["counts"]["by_verdict"][drg.VERDICT_GO_WITH_FOLLOWUPS] == 1
    assert snap["counts"]["by_verdict"][drg.VERDICT_NO_GO_HUMAN_NEEDED] == 1
    assert snap["counts"]["ready_for_merge"] == 3
    assert snap["counts"]["requiring_human_operator"] == 1
    assert "item_x_missing_acceptance_criteria" in snap["validation_warnings"]


def test_status_buckets_cover_all_closed_vocabularies(tmp_path: Path) -> None:
    sparse_gate = {
        "schema_version": "1.0",
        "module_version": drg.MODULE_VERSION,
        "note": drg.NOTE_NO_QUALIFYING_ITEMS,
        "counts": {"total": 0},
        "validation_warnings": [],
    }
    qp = _write_gate_artifact(tmp_path, sparse_gate)
    snap = drgs.collect_status(gate_artifact_path=qp)
    assert set(snap["counts"]["by_verdict"]) == set(drg.VERDICTS)
    assert set(snap["counts"]["by_verdict_reason"]) == set(drg.VERDICT_REASONS)
    assert all(v == 0 for v in snap["counts"]["by_verdict"].values())
    assert snap["counts"]["ready_for_merge"] == 0
    assert snap["counts"]["requiring_human_operator"] == 0


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


def test_status_does_not_mutate_gate_artifact(tmp_path: Path) -> None:
    fake_gate = {
        "schema_version": "1.0",
        "module_version": drg.MODULE_VERSION,
        "note": drg.NOTE_NO_QUALIFYING_ITEMS,
        "counts": {"total": 0},
        "validation_warnings": [],
    }
    qp = _write_gate_artifact(tmp_path, fake_gate)
    before = qp.read_bytes()
    drgs.collect_status(gate_artifact_path=qp)
    after = qp.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(drgs.__file__).read_text(encoding="utf-8")


def test_no_subprocess_in_status_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_status_module() -> None:
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


def _imported_module_names() -> set[str]:
    """Return the set of fully-qualified module names imported by
    the status module, parsed via ``ast`` so that docstring/comment
    mentions of forbidden modules do not produce false positives."""
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


def test_no_dashboard_or_live_path_or_qre_imports_in_status_module() -> None:
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


def test_status_module_imports_cleanly() -> None:
    importlib.reload(drgs)
    assert callable(drgs.collect_status)
