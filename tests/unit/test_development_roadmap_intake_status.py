"""Unit tests for Step 5.0.1 — Roadmap Intake Bridge status summary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_roadmap_intake as dri
from reporting import development_roadmap_intake_status as dris
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_intake_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic_intake_payload(
    *,
    counts_total: int = 2,
    human_needed: int = 1,
    eligible: int = 1,
    blocked: int = 0,
    by_intake_status: dict[str, int] | None = None,
    by_source_kind: dict[str, int] | None = None,
    by_candidate_kind: dict[str, int] | None = None,
    by_decision: dict[str, int] | None = None,
    note: str = "intake_candidates_present",
    validation_warnings: list[str] | None = None,
) -> dict[str, Any]:
    statuses = {s: 0 for s in dri.INTAKE_STATUSES}
    if by_intake_status:
        statuses.update(by_intake_status)
    sources = {k: 0 for k in dri.SOURCE_KINDS}
    if by_source_kind:
        sources.update(by_source_kind)
    kinds = {k: 0 for k in dri.CANDIDATE_KINDS}
    if by_candidate_kind:
        kinds.update(by_candidate_kind)
    decisions = {
        ea.DECISION_AUTO_ALLOWED: 0,
        ea.DECISION_NEEDS_HUMAN: 0,
        ea.DECISION_PERMANENTLY_DENIED: 0,
    }
    if by_decision:
        decisions.update(by_decision)
    return {
        "schema_version": "1.0",
        "module_version": dri.MODULE_VERSION,
        "report_kind": "development_roadmap_intake",
        "generated_at_utc": "2026-05-08T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "canonical_source_paths": list(dri.DEFAULT_SOURCE_PATHS),
        "source_paths_used": [],
        "source_paths_missing": [],
        "note": note,
        "validation_warnings": list(validation_warnings or []),
        "vocabularies": {
            "source_kinds": list(dri.SOURCE_KINDS),
            "candidate_kinds": list(dri.CANDIDATE_KINDS),
            "intake_statuses": list(dri.INTAKE_STATUSES),
            "promotion_targets": list(dri.PROMOTION_TARGETS),
            "agent_roles": list(dwq.AGENT_ROLES),
            "risk_levels": list(ea.RISK_CLASSES),
            "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
            "marker_required_fields": sorted(dri.MARKER_REQUIRED_FIELDS),
        },
        "counts": {
            "total": counts_total,
            "by_source_kind": sources,
            "by_candidate_kind": kinds,
            "by_intake_status": statuses,
            "by_execution_authority_decision": decisions,
            "by_required_agent_role": {r: 0 for r in dwq.AGENT_ROLES},
            "by_promotion_target": {t: 0 for t in dri.PROMOTION_TARGETS},
            "human_needed": human_needed,
            "eligible": eligible,
            "blocked": blocked,
        },
        "candidates": [],
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": dwq.MODULE_VERSION,
        "discipline_invariants": {},
    }


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_artifact_path_under_logs_only() -> None:
    assert dris.ARTIFACT_RELATIVE_PATH.startswith(
        "logs/development_roadmap_intake_status/"
    )
    assert "research/" not in dris.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dris._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    with pytest.raises(ValueError):
        dris._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Status when upstream artifact is absent
# ---------------------------------------------------------------------------


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    snap = dris.collect_status(
        intake_artifact_path=missing,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["intake_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["counts"]["human_needed"] == 0
    assert snap["counts"]["eligible"] == 0
    assert snap["counts"]["blocked"] == 0
    assert snap["note"] == "intake_artifact_absent"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    # The schema_pinned block must echo the closed vocabularies.
    sp = snap["schema_pinned"]
    assert sp["source_kinds"] == list(dri.SOURCE_KINDS)
    assert sp["candidate_kinds"] == list(dri.CANDIDATE_KINDS)
    assert sp["intake_statuses"] == list(dri.INTAKE_STATUSES)
    assert sp["promotion_targets"] == list(dri.PROMOTION_TARGETS)


# ---------------------------------------------------------------------------
# Status with synthetic upstream payload
# ---------------------------------------------------------------------------


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    payload = _synthetic_intake_payload(
        counts_total=3,
        human_needed=1,
        eligible=1,
        blocked=1,
        by_intake_status={
            "eligible": 1,
            "blocked": 1,
            "human_needed": 1,
        },
        by_source_kind={
            "roadmap_v6": 1,
            "roadmap_v6_addendum": 1,
            "phase_prompt": 1,
        },
        by_candidate_kind={
            "docs": 2,
            "reporting": 1,
        },
        by_decision={
            ea.DECISION_AUTO_ALLOWED: 1,
            ea.DECISION_NEEDS_HUMAN: 1,
            ea.DECISION_PERMANENTLY_DENIED: 1,
        },
    )
    artifact = _write_intake_artifact(tmp_path, payload)
    snap = dris.collect_status(
        intake_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["intake_artifact_available"] is True
    assert snap["counts"]["total"] == 3
    assert snap["counts"]["human_needed"] == 1
    assert snap["counts"]["eligible"] == 1
    assert snap["counts"]["blocked"] == 1
    assert snap["counts"]["by_intake_status"]["eligible"] == 1
    assert snap["counts"]["by_intake_status"]["blocked"] == 1
    assert snap["counts"]["by_intake_status"]["human_needed"] == 1
    assert snap["counts"]["by_source_kind"]["roadmap_v6"] == 1
    assert snap["counts"]["by_source_kind"]["roadmap_v6_addendum"] == 1
    assert snap["counts"]["by_source_kind"]["phase_prompt"] == 1
    assert snap["counts"]["by_candidate_kind"]["docs"] == 2
    assert snap["counts"]["by_candidate_kind"]["reporting"] == 1
    assert snap["counts"]["by_execution_authority_decision"][
        ea.DECISION_AUTO_ALLOWED
    ] == 1
    assert snap["counts"]["by_execution_authority_decision"][
        ea.DECISION_NEEDS_HUMAN
    ] == 1
    assert snap["counts"]["by_execution_authority_decision"][
        ea.DECISION_PERMANENTLY_DENIED
    ] == 1
    assert snap["intake_module_version"] == dri.MODULE_VERSION
    assert snap["intake_note"] == "intake_candidates_present"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_status_validation_warnings_pass_through(tmp_path: Path) -> None:
    payload = _synthetic_intake_payload(
        validation_warnings=["docs/roadmap/Foo.md#marker1:invalid_category"],
    )
    artifact = _write_intake_artifact(tmp_path, payload)
    snap = dris.collect_status(
        intake_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["validation_warnings"] == [
        "docs/roadmap/Foo.md#marker1:invalid_category"
    ]


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json at all", encoding="utf-8")
    snap = dris.collect_status(
        intake_artifact_path=bad,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["intake_artifact_available"] is False
    assert snap["note"] == "intake_artifact_absent"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_status_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    payload = _synthetic_intake_payload()
    artifact = _write_intake_artifact(tmp_path, payload)
    snap_a = dris.collect_status(
        intake_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_b = dris.collect_status(
        intake_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    a_bytes = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    b_bytes = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert a_bytes == b_bytes


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dris.__file__).read_text(encoding="utf-8")


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


def test_no_forbidden_imports_in_status_module() -> None:
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


def test_status_module_imports_cleanly() -> None:
    importlib.reload(dris)
    assert callable(dris.collect_status)
