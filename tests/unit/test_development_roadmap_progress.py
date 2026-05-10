"""Unit tests for A19 — Roadmap Progress Tracker."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_roadmap_progress as drp


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    intake = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    promo = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    adm = tmp_path / "logs" / "development_queue_admission_policy" / "latest.json"
    hist = tmp_path / "logs" / "step5_plan" / "history.jsonl"
    for p in (intake, promo, adm, hist):
        p.parent.mkdir(parents=True, exist_ok=True)
    return intake, promo, adm, hist


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )


def _intake_payload(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "development_roadmap_intake",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "candidates": candidates,
    }


def _promo_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "development_intake_promotion",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "rows": rows,
    }


def _adm_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "development_queue_admission_policy",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_phase_progress_states_pinned_exactly() -> None:
    assert drp.PHASE_PROGRESS_STATES == (
        "not_started",
        "intake_only",
        "promotion_active",
        "admission_active",
        "planning_active",
        "complete",
    )


def test_phase_row_keys_pinned_exactly_and_ordered() -> None:
    assert drp.PHASE_ROW_KEYS == (
        "roadmap_phase",
        "intake_candidate_count",
        "intake_eligible_count",
        "intake_blocked_count",
        "intake_human_needed_count",
        "promotion_total",
        "promotion_eligible_count",
        "promotion_blocked_count",
        "admission_total",
        "admission_admissible_count",
        "admission_blocked_count",
        "admission_needs_human_count",
        "step5_planned_count",
        "step5_halted_count",
        "phase_progress_state",
    )


def test_step5_invariants_pinned() -> None:
    assert drp.step5_implementation_allowed is False
    assert drp.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_progress_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        drp._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# A19 NEVER assigns `complete` autonomously
# ---------------------------------------------------------------------------


def test_a19_never_assigns_complete(tmp_path: Path) -> None:
    """Even with maximally rich upstream signal (intake + promotion +
    admission + Step 5.0 plan_emitted), A19 lands in
    `planning_active`, never `complete`. Operator-only marker."""
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(
        intake,
        _intake_payload([
            {
                "candidate_id": "c1",
                "roadmap_phase": "v3.15.16",
                "intake_status": "eligible",
            },
        ]),
    )
    _write_json(
        promo,
        _promo_payload([
            {
                "candidate_id": "c1",
                "roadmap_phase": "v3.15.16",
                "decision_state": "eligible",
            },
        ]),
    )
    _write_json(
        adm,
        _adm_payload([
            {
                "candidate_id": "c1",
                "roadmap_phase": "v3.15.16",
                "admission_decision": "admissible",
            },
        ]),
    )
    _write_jsonl(hist, [{"source_id": "c1", "outcome": "plan_emitted"}])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    rows = snap["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["phase_progress_state"] == "planning_active"
    assert row["phase_progress_state"] != "complete"


# ---------------------------------------------------------------------------
# Phase derivation
# ---------------------------------------------------------------------------


def test_intake_only_state(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(
        intake,
        _intake_payload([
            {"candidate_id": "c1", "roadmap_phase": "v3.15.17", "intake_status": "proposed"},
        ]),
    )
    _write_json(promo, _promo_payload([]))
    _write_json(adm, _adm_payload([]))
    _write_jsonl(hist, [])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    assert snap["rows"][0]["phase_progress_state"] == "intake_only"


def test_promotion_active_state(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(intake, _intake_payload([]))
    _write_json(
        promo,
        _promo_payload([
            {"candidate_id": "c1", "roadmap_phase": "v3.15.17", "decision_state": "eligible"},
        ]),
    )
    _write_json(adm, _adm_payload([]))
    _write_jsonl(hist, [])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    assert snap["rows"][0]["phase_progress_state"] == "promotion_active"


def test_admission_active_state(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(intake, _intake_payload([]))
    _write_json(promo, _promo_payload([]))
    _write_json(
        adm,
        _adm_payload([
            {"candidate_id": "c1", "roadmap_phase": "v3.15.17", "admission_decision": "admissible"},
        ]),
    )
    _write_jsonl(hist, [])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    assert snap["rows"][0]["phase_progress_state"] == "admission_active"


def test_planning_active_state_resolved_via_promotion_phase(
    tmp_path: Path,
) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(intake, _intake_payload([]))
    _write_json(
        promo,
        _promo_payload([
            {"candidate_id": "c1", "roadmap_phase": "v3.15.17", "decision_state": "eligible"},
        ]),
    )
    _write_json(adm, _adm_payload([]))
    _write_jsonl(hist, [{"source_id": "c1", "outcome": "plan_emitted"}])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    assert snap["rows"][0]["phase_progress_state"] == "planning_active"


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_intake_counts_per_phase(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(
        intake,
        _intake_payload([
            {"candidate_id": "a", "roadmap_phase": "p1", "intake_status": "eligible"},
            {"candidate_id": "b", "roadmap_phase": "p1", "intake_status": "blocked"},
            {"candidate_id": "c", "roadmap_phase": "p1", "intake_status": "human_needed"},
            {"candidate_id": "d", "roadmap_phase": "p2", "intake_status": "eligible"},
        ]),
    )
    _write_json(promo, _promo_payload([]))
    _write_json(adm, _adm_payload([]))
    _write_jsonl(hist, [])
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    by_phase = {r["roadmap_phase"]: r for r in snap["rows"]}
    assert by_phase["p1"]["intake_candidate_count"] == 3
    assert by_phase["p1"]["intake_eligible_count"] == 1
    assert by_phase["p1"]["intake_blocked_count"] == 1
    assert by_phase["p1"]["intake_human_needed_count"] == 1
    assert by_phase["p2"]["intake_candidate_count"] == 1


def test_step5_counts_planned_vs_halted(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(intake, _intake_payload([]))
    _write_json(
        promo,
        _promo_payload([
            {"candidate_id": "c1", "roadmap_phase": "p1", "decision_state": "eligible"},
        ]),
    )
    _write_json(adm, _adm_payload([]))
    _write_jsonl(
        hist,
        [
            {"source_id": "c1", "outcome": "plan_emitted"},
            {"source_id": "c1", "outcome": "halt_needs_human"},
            {"source_id": "c1", "outcome": "halt_permanently_denied"},
        ],
    )
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    by_phase = {r["roadmap_phase"]: r for r in snap["rows"]}
    assert by_phase["p1"]["step5_planned_count"] == 1
    assert by_phase["p1"]["step5_halted_count"] == 2


# ---------------------------------------------------------------------------
# Snapshot shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "sources_read",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "intake_module_version",
        "promotion_module_version",
        "admission_module_version",
        "step5_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["mutates_canonical_roadmap_status_fields"] is False
    assert inv["marks_any_phase_complete"] is False
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    _write_json(
        intake,
        _intake_payload([
            {"candidate_id": "c1", "roadmap_phase": "p1", "intake_status": "eligible"},
        ]),
    )
    _write_json(promo, _promo_payload([]))
    _write_json(adm, _adm_payload([]))
    _write_jsonl(hist, [])
    snap_a = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    snap_b = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert (
        json.dumps(snap_a, sort_keys=True, indent=2)
        == json.dumps(snap_b, sort_keys=True, indent=2)
    )


def test_no_upstream_artifacts_yields_clean_snapshot(tmp_path: Path) -> None:
    intake, promo, adm, hist = _make_paths(tmp_path)
    snap = drp.collect_snapshot(
        intake_artifact_path=intake,
        promotion_artifact_path=promo,
        admission_artifact_path=adm,
        step5_history_path=hist,
    )
    assert snap["rows"] == []
    assert snap["note"] == "no_upstream_artifacts"


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(drp.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_or_network_in_module() -> None:
    src = _module_source()
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    )
    for s in forbidden:
        assert s not in src, s


def test_no_dashboard_or_frontend_imports() -> None:
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


def test_module_imports_cleanly() -> None:
    importlib.reload(drp)
    assert callable(drp.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(drp)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_does_not_open_seed_jsonl_for_writing() -> None:
    src = _module_source()
    forbidden = (
        "seed.jsonl\", \"w",
        "seed.jsonl', 'w",
        "seed.jsonl\", \"a",
        "seed.jsonl', 'a",
        "delegation_seed.jsonl\", \"w",
        "GENERATED_SEED_PATH",
    )
    for s in forbidden:
        assert s not in src, s


def test_module_does_not_mutate_canonical_roadmap() -> None:
    """Defense in depth: A19 source must not contain code that writes
    to the canonical roadmap docs."""
    src = _module_source()
    forbidden = (
        "Roadmap v6.md\", \"w",
        "autonomous_development.txt\", \"w",
    )
    for s in forbidden:
        assert s not in src
