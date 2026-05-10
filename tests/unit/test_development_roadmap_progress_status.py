"""Unit tests for A19 — Roadmap Progress Tracker status summary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_roadmap_progress as drp
from reporting import development_roadmap_progress_status as drps


def _write_progress(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "development_roadmap_progress" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic(by_state: dict[str, int]) -> dict[str, Any]:
    counts = {
        "phase_count": sum(by_state.values()),
        "by_phase_progress_state": {s: 0 for s in drp.PHASE_PROGRESS_STATES},
    }
    for s, n in by_state.items():
        if s in counts["by_phase_progress_state"]:
            counts["by_phase_progress_state"][s] = n
    return {
        "schema_version": "1.0",
        "module_version": drp.MODULE_VERSION,
        "report_kind": "development_roadmap_progress",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "note": "roadmap_phases_present",
        "validation_warnings": [],
        "counts": counts,
        "rows": [],
    }


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        drps._atomic_write_json(bad, {"x": 1})


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "development_roadmap_progress" / "latest.json"
    snap = drps.collect_status(
        progress_artifact_path=missing,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["progress_artifact_available"] is False
    assert snap["counts"]["phase_count"] == 0
    assert snap["note"] == "progress_artifact_absent"
    assert snap["step5_implementation_allowed"] is False


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    payload = _synthetic({"intake_only": 1, "promotion_active": 1, "planning_active": 1})
    artifact = _write_progress(tmp_path, payload)
    snap = drps.collect_status(
        progress_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["progress_artifact_available"] is True
    assert snap["counts"]["phase_count"] == 3
    assert snap["counts"]["by_phase_progress_state"]["intake_only"] == 1
    assert snap["counts"]["by_phase_progress_state"]["promotion_active"] == 1
    assert snap["counts"]["by_phase_progress_state"]["planning_active"] == 1
    # complete count must always be 0 — A19 never assigns it.
    assert snap["counts"]["by_phase_progress_state"]["complete"] == 0


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_roadmap_progress" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = drps.collect_status(
        progress_artifact_path=bad,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["progress_artifact_available"] is False


def test_status_module_imports_cleanly() -> None:
    importlib.reload(drps)
    assert callable(drps.collect_status)


def test_no_forbidden_imports_in_status_module() -> None:
    import ast

    src = Path(drps.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in names:
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"
