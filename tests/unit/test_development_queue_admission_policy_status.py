"""Unit tests for A17 — Queue Admission Policy status summary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_queue_admission_policy as qap
from reporting import development_queue_admission_policy_status as qaps


def _write_policy_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "development_queue_admission_policy" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic(rows_total: int, by_decision: dict[str, int]) -> dict[str, Any]:
    counts = {
        "total": rows_total,
        "admissible": by_decision.get("admissible", 0),
        "needs_human": by_decision.get("needs_human", 0),
        "blocked": by_decision.get("blocked", 0),
        "duplicate_of_existing": by_decision.get("duplicate_of_existing", 0),
        "not_eligible_upstream": by_decision.get("not_eligible_upstream", 0),
        "by_admission_decision": {d: 0 for d in qap.ADMISSION_DECISIONS},
        "by_admission_reason": {r: 0 for r in qap.ADMISSION_REASONS},
    }
    for d, n in by_decision.items():
        if d in counts["by_admission_decision"]:
            counts["by_admission_decision"][d] = n
    return {
        "schema_version": "1.0",
        "module_version": qap.MODULE_VERSION,
        "report_kind": "development_queue_admission_policy",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "policy_version": qap.MODULE_VERSION,
        "note": "admission_records_present" if rows_total else "no_promotion_records_to_evaluate",
        "validation_warnings": [],
        "counts": counts,
        "rows": [],
    }


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        qaps._atomic_write_json(bad, {"x": 1})


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "development_queue_admission_policy" / "latest.json"
    snap = qaps.collect_status(
        policy_artifact_path=missing,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["policy_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["note"] == "policy_artifact_absent"
    assert snap["step5_implementation_allowed"] is False


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    payload = _synthetic(
        rows_total=4,
        by_decision={
            "admissible": 1,
            "needs_human": 1,
            "blocked": 1,
            "duplicate_of_existing": 1,
        },
    )
    artifact = _write_policy_artifact(tmp_path, payload)
    snap = qaps.collect_status(
        policy_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["policy_artifact_available"] is True
    assert snap["counts"]["total"] == 4
    assert snap["counts"]["admissible"] == 1
    assert snap["counts"]["needs_human"] == 1
    assert snap["counts"]["blocked"] == 1
    assert snap["counts"]["duplicate_of_existing"] == 1
    assert snap["policy_module_version"] == qap.MODULE_VERSION


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_queue_admission_policy" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = qaps.collect_status(
        policy_artifact_path=bad,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["policy_artifact_available"] is False


def test_status_module_imports_cleanly() -> None:
    importlib.reload(qaps)
    assert callable(qaps.collect_status)


def _module_source() -> str:
    return Path(qaps.__file__).read_text(encoding="utf-8")


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


def test_no_forbidden_imports_in_status_module() -> None:
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
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"
