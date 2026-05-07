"""Unit tests for A8 — Development Work Queue status summary.

Synthetic deterministic fixtures only. The status module reads the
queue artifact at ``logs/development_work_queue/latest.json`` and
emits a compact operator-facing summary; it does not mutate the
queue artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_work_queue as dwq
from reporting import development_work_queue_status as dwqs


def _write_queue_artifact(
    tmp_path: Path, payload: dict[str, Any]
) -> Path:
    p = tmp_path / "queue.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_artifact_path_is_under_logs_not_research() -> None:
    assert dwqs.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in dwqs.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dwqs._atomic_write_json(bad, {"x": 1})


def test_status_top_level_keys_when_queue_artifact_absent(tmp_path: Path) -> None:
    qp = tmp_path / "missing.json"
    snap = dwqs.collect_status(queue_artifact_path=qp)
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "queue_artifact_path",
        "queue_artifact_available",
        "queue_module_version",
        "schema_pinned",
        "counts",
        "validation_warnings",
        "note",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_work_queue_status"
    assert snap["queue_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["note"] == "queue_artifact_absent"
    # The status module exposes the closed schema even when the
    # queue artifact is missing — useful for operator visibility.
    assert set(snap["schema_pinned"]) == {
        "agent_roles",
        "statuses",
        "categories",
        "human_needed_reasons",
    }


# ---------------------------------------------------------------------------
# Counts pass-through and bucket completeness
# ---------------------------------------------------------------------------


def test_counts_pass_through_when_queue_artifact_present(tmp_path: Path) -> None:
    fake_queue = {
        "schema_version": "1.0",
        "module_version": dwq.MODULE_VERSION,
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": dwq.NOTE_ITEMS_PRESENT,
        "counts": {
            "total": 3,
            "human_needed": 1,
            "blocked": 1,
            "protected_surface": 1,
            "ready_for_autonomous_action": 1,
            "requiring_human_operator": 1,
            "by_status": {s: 0 for s in dwq.STATUSES},
            "by_role": {r: 0 for r in dwq.AGENT_ROLES},
            "by_category": {c: 0 for c in dwq.CATEGORIES},
        },
        "validation_warnings": ["item_x_missing_acceptance_criteria"],
    }
    fake_queue["counts"]["by_status"]["ready"] = 1
    fake_queue["counts"]["by_status"]["blocked"] = 1
    fake_queue["counts"]["by_status"]["human_needed"] = 1
    fake_queue["counts"]["by_role"]["implementation_agent"] = 1
    fake_queue["counts"]["by_role"]["test_agent"] = 1
    fake_queue["counts"]["by_role"]["human_operator"] = 1
    fake_queue["counts"]["by_category"]["docs"] = 2
    fake_queue["counts"]["by_category"]["governance"] = 1

    qp = _write_queue_artifact(tmp_path, fake_queue)
    snap = dwqs.collect_status(queue_artifact_path=qp)

    assert snap["queue_artifact_available"] is True
    assert snap["counts"]["total"] == 3
    assert snap["counts"]["human_needed"] == 1
    assert snap["counts"]["blocked"] == 1
    assert snap["counts"]["protected_surface"] == 1
    assert snap["counts"]["ready_for_autonomous_action"] == 1
    assert snap["counts"]["requiring_human_operator"] == 1
    assert snap["counts"]["by_status"]["ready"] == 1
    assert sum(snap["counts"]["by_status"].values()) == 3
    assert sum(snap["counts"]["by_role"].values()) == 3
    assert sum(snap["counts"]["by_category"].values()) == 3
    # Validation warnings carry through verbatim.
    assert "item_x_missing_acceptance_criteria" in snap["validation_warnings"]


def test_status_buckets_cover_all_closed_vocabularies(tmp_path: Path) -> None:
    """Even sparse input artifacts are projected onto the full closed
    vocabularies — operators see zero counts for unused categories,
    not missing buckets."""
    sparse_queue = {
        "schema_version": "1.0",
        "module_version": dwq.MODULE_VERSION,
        "note": dwq.NOTE_NO_ITEMS,
        "counts": {"total": 0},
        "validation_warnings": [],
    }
    qp = _write_queue_artifact(tmp_path, sparse_queue)
    snap = dwqs.collect_status(queue_artifact_path=qp)
    assert set(snap["counts"]["by_status"]) == set(dwq.STATUSES)
    assert set(snap["counts"]["by_role"]) == set(dwq.AGENT_ROLES)
    assert set(snap["counts"]["by_category"]) == set(dwq.CATEGORIES)
    assert all(v == 0 for v in snap["counts"]["by_status"].values())


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


def test_status_does_not_mutate_queue_artifact(tmp_path: Path) -> None:
    """Reading the queue artifact must never mutate it. We snapshot
    the bytes before and after a status read and assert byte equality."""
    fake_queue = {
        "schema_version": "1.0",
        "module_version": dwq.MODULE_VERSION,
        "note": dwq.NOTE_NO_ITEMS,
        "counts": {"total": 0},
        "validation_warnings": [],
    }
    qp = _write_queue_artifact(tmp_path, fake_queue)
    before = qp.read_bytes()
    dwqs.collect_status(queue_artifact_path=qp)
    after = qp.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    p = Path(dwqs.__file__)
    return p.read_text(encoding="utf-8")


def test_no_subprocess_in_status_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_status_module() -> None:
    src = _module_source()
    for forbidden in ("import socket", "import urllib", "import http.client", "import requests"):
        assert forbidden not in src
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src
    assert "from requests" not in src


def test_no_dashboard_or_live_path_imports_in_status_module() -> None:
    src = _module_source()
    for forbidden in (
        "import dashboard",
        "from dashboard",
        "import automation",
        "from automation",
        "import broker",
        "from broker",
        "import agent.risk",
        "import agent.execution",
        "from agent.risk",
        "from agent.execution",
        "from research",
        "import research",
    ):
        assert forbidden not in src, forbidden


def test_status_module_imports_cleanly() -> None:
    import importlib

    importlib.reload(dwqs)
    assert callable(dwqs.collect_status)
