"""Unit tests for A12 — Operational Digest / Observability Loop.

Synthetic deterministic fixtures only. The pure aggregator reads
the four upstream ADE artifacts (A8 queue, A9 release gate, A10
bugfix loop, A11 delegation) and emits a compact operator-facing
snapshot plus a bounded append-only history.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_operational_digest as dod
from reporting import development_release_gate as drg
from reporting import development_work_queue as dwq


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _queue_payload(
    *,
    total: int = 1,
    human_needed: int = 0,
    blocked: int = 0,
    protected_surface: int = 0,
    ready_for_autonomous_action: int = 0,
    requiring_human_operator: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": dwq.MODULE_VERSION,
        "report_kind": "development_work_queue",
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": "explicit_seed_items_present",
        "counts": {
            "total": total,
            "human_needed": human_needed,
            "blocked": blocked,
            "protected_surface": protected_surface,
            "ready_for_autonomous_action": ready_for_autonomous_action,
            "requiring_human_operator": requiring_human_operator,
            "by_role": {r: 0 for r in dwq.AGENT_ROLES},
            "by_status": {s: 0 for s in dwq.STATUSES},
        },
    }


def _release_gate_payload(
    *,
    total: int = 1,
    human_needed: int = 0,
    protected_surface: int = 0,
    by_verdict_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    by_verdict = {v: 0 for v in drg.VERDICTS}
    if by_verdict_overrides:
        by_verdict.update(by_verdict_overrides)
    return {
        "schema_version": "1.0",
        "module_version": drg.MODULE_VERSION,
        "report_kind": "development_release_gate",
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": drg.NOTE_VERDICTS_PRESENT,
        "evidence_input_present": True,
        "queue_artifact_present": True,
        "counts": {
            "total": total,
            "human_needed": human_needed,
            "protected_surface": protected_surface,
            "by_verdict": by_verdict,
            "by_verdict_reason": {r: 0 for r in drg.VERDICT_REASONS},
        },
    }


def _bugfix_loop_payload(
    *,
    total: int = 1,
    human_needed: int = 0,
    repeated_failure: int = 0,
    out_of_scope: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": dbl.MODULE_VERSION,
        "report_kind": "development_bugfix_loop",
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": dbl.NOTE_CANDIDATES_PRESENT,
        "counts": {
            "total": total,
            "by_failure_class": {fc: 0 for fc in dbl.FAILURE_CLASSES},
            "by_bugfix_scope": {s: 0 for s in dbl.BUGFIX_SCOPES},
            "human_needed": human_needed,
            "repeated_failure": repeated_failure,
            "out_of_scope": out_of_scope,
        },
        "discipline_invariants": {
            "writes_to_seed_jsonl": False,
            "writes_to_bugfix_seed_jsonl": False,
            "auto_creates_branches": False,
            "auto_opens_prs": False,
            "auto_modifies_code": False,
            "operator_promotion_required": True,
        },
    }


def _delegation_payload(
    *,
    total: int = 1,
    human_needed: int = 0,
    protected_surface: int = 0,
    ready_for_operator_promotion: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": ddl.MODULE_VERSION,
        "report_kind": "development_delegation",
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "note": ddl.NOTE_ENTRIES_PRESENT,
        "counts": {
            "total": total,
            "by_roadmap_track": {
                "autonomous_development": 0,
                "qre_feature_build": 0,
                "sidecar_seed": 0,
            },
            "by_category": {c: 0 for c in dwq.CATEGORIES},
            "by_required_agent_role": {r: 0 for r in dwq.AGENT_ROLES},
            "by_status": {ddl.DEFAULT_STATUS: 0},
            "by_execution_authority_decision": {},
            "human_needed": human_needed,
            "protected_surface": protected_surface,
            "ready_for_operator_promotion": ready_for_operator_promotion,
        },
        "discipline_invariants": {
            "writes_to_seed_jsonl": False,
            "writes_to_bugfix_seed_jsonl": False,
            "writes_to_delegation_seed_jsonl": False,
            "fuzzy_parsing": False,
            "operator_promotion_required": True,
        },
    }


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_step5_criteria_vocabulary_is_closed_and_ordered() -> None:
    assert dod.STEP5_CRITERIA == (
        "release_gate_artifact_present",
        "release_gate_no_protected_surface_leakage",
        "bugfix_loop_artifact_present",
        "bugfix_loop_no_test_weakening_proposals",
        "delegation_artifact_present",
        "delegation_no_fuzzy_parsing_evidence",
        "queue_artifact_present",
        "queue_human_needed_signal_meaningful",
        "ade_qre_loose_coupling_clean",
        "no_protected_path_violations",
    )
    assert len(dod.STEP5_CRITERIA) == 10


def test_artifact_path_is_under_logs_not_research() -> None:
    assert dod.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert dod.HISTORY_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in dod.ARTIFACT_RELATIVE_PATH
    assert "research/" not in dod.HISTORY_RELATIVE_PATH


def test_max_history_entries_is_operator_approved_90() -> None:
    """Operator approved 90 entries during plan amendment review."""
    assert dod.MAX_HISTORY_ENTRIES == 90


def test_max_operator_actions_is_bounded() -> None:
    assert dod.MAX_OPERATOR_ACTIONS > 0
    assert dod.MAX_OPERATOR_ACTIONS <= 50


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dod._atomic_write_json(bad, {"x": 1})


def test_history_append_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "history.jsonl"
    with pytest.raises(ValueError):
        dod._append_history(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys_when_no_inputs(tmp_path: Path) -> None:
    snap = dod.collect_snapshot(
        queue_path=tmp_path / "missing_queue.json",
        release_gate_path=tmp_path / "missing_rg.json",
        bugfix_loop_path=tmp_path / "missing_bl.json",
        delegation_path=tmp_path / "missing_del.json",
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "note",
        "presence_count",
        "sources",
        "operator_action_list",
        "step5_readiness",
        "vocabularies",
        "queue_module_version",
        "release_gate_module_version",
        "bugfix_loop_module_version",
        "delegation_module_version",
        "max_history_entries",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_operational_digest"
    assert snap["presence_count"] == 0
    assert snap["note"] == dod.NOTE_NO_INPUT
    assert snap["operator_action_list"] == []
    assert snap["step5_readiness"]["step5_ready"] is False
    assert snap["step5_readiness"]["step5_implementation_allowed"] is False


def test_partial_inputs_yields_partial_note(tmp_path: Path) -> None:
    qp = _write(tmp_path / "q.json", _queue_payload())
    snap = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=tmp_path / "missing_rg.json",
        bugfix_loop_path=tmp_path / "missing_bl.json",
        delegation_path=tmp_path / "missing_del.json",
    )
    assert snap["presence_count"] == 1
    assert snap["note"] == dod.NOTE_PARTIAL_INPUT


def test_full_inputs_yields_full_note(tmp_path: Path) -> None:
    qp = _write(tmp_path / "q.json", _queue_payload())
    rgp = _write(tmp_path / "rg.json", _release_gate_payload())
    blp = _write(tmp_path / "bl.json", _bugfix_loop_payload())
    dp = _write(tmp_path / "del.json", _delegation_payload())
    snap = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
    )
    assert snap["presence_count"] == 4
    assert snap["note"] == dod.NOTE_FULL_INPUT


# ---------------------------------------------------------------------------
# Operator action list
# ---------------------------------------------------------------------------


def test_operator_action_list_aggregates_from_each_source(tmp_path: Path) -> None:
    qp = _write(
        tmp_path / "q.json",
        _queue_payload(total=3, human_needed=1, blocked=1),
    )
    rgp = _write(
        tmp_path / "rg.json",
        _release_gate_payload(
            total=2,
            human_needed=1,
            by_verdict_overrides={
                drg.VERDICT_NO_GO_HUMAN_NEEDED: 1,
                drg.VERDICT_GO: 1,
            },
        ),
    )
    blp = _write(
        tmp_path / "bl.json",
        _bugfix_loop_payload(total=2, human_needed=1, repeated_failure=1),
    )
    dp = _write(
        tmp_path / "del.json",
        _delegation_payload(total=2, human_needed=1, ready_for_operator_promotion=1),
    )
    snap = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
    )
    actions = snap["operator_action_list"]
    kinds = {a["kind"] for a in actions}
    assert "queue_human_needed_items_present" in kinds
    assert "queue_blocked_items_present" in kinds
    assert "release_gate_no_go_human_needed" in kinds
    assert "bugfix_repeated_validation_failure" in kinds
    assert "bugfix_human_needed_candidates" in kinds
    assert "delegation_human_needed_entries" in kinds
    assert "delegation_ready_for_operator_promotion" in kinds


def test_operator_action_list_is_bounded(tmp_path: Path) -> None:
    qp = _write(
        tmp_path / "q.json",
        _queue_payload(total=99, human_needed=99, blocked=99),
    )
    rgp = _write(
        tmp_path / "rg.json",
        _release_gate_payload(
            total=99,
            by_verdict_overrides={
                drg.VERDICT_NO_GO_HUMAN_NEEDED: 99,
                drg.VERDICT_NO_GO_BLOCKED: 99,
            },
        ),
    )
    blp = _write(
        tmp_path / "bl.json",
        _bugfix_loop_payload(total=99, human_needed=99, repeated_failure=99),
    )
    dp = _write(
        tmp_path / "del.json",
        _delegation_payload(
            total=99, human_needed=99, ready_for_operator_promotion=99
        ),
    )
    snap = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
    )
    assert len(snap["operator_action_list"]) <= dod.MAX_OPERATOR_ACTIONS


# ---------------------------------------------------------------------------
# Step 5 readiness
# ---------------------------------------------------------------------------


def test_step5_ready_is_false_when_artifacts_missing(tmp_path: Path) -> None:
    snap = dod.collect_snapshot(
        queue_path=tmp_path / "missing_q.json",
        release_gate_path=tmp_path / "missing_rg.json",
        bugfix_loop_path=tmp_path / "missing_bl.json",
        delegation_path=tmp_path / "missing_del.json",
    )
    s5 = snap["step5_readiness"]
    assert s5["step5_ready"] is False
    # The bool result for every criterion is reported, no missing keys.
    assert set(s5["criteria"]) == set(dod.STEP5_CRITERIA)


def test_step5_implementation_always_blocked_pending_operator(tmp_path: Path) -> None:
    """Even when every criterion passes, step5_implementation_allowed
    must remain False — operator authorisation is separate."""
    qp = _write(
        tmp_path / "q.json",
        _queue_payload(
            total=1,
            human_needed=0,
            ready_for_autonomous_action=1,
            requiring_human_operator=0,
        ),
    )
    rgp = _write(
        tmp_path / "rg.json",
        _release_gate_payload(
            total=1, by_verdict_overrides={drg.VERDICT_GO: 1}
        ),
    )
    blp = _write(tmp_path / "bl.json", _bugfix_loop_payload(total=0))
    dp = _write(tmp_path / "del.json", _delegation_payload(total=0))
    snap = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
    )
    s5 = snap["step5_readiness"]
    assert s5["step5_implementation_allowed"] is False
    # design_planning is allowed unconditionally (operator-authored).
    assert s5["step5_design_planning_allowed"] is True


def test_step5_design_planning_is_always_allowed(tmp_path: Path) -> None:
    snap = dod.collect_snapshot(
        queue_path=tmp_path / "missing.json",
        release_gate_path=tmp_path / "missing.json",
        bugfix_loop_path=tmp_path / "missing.json",
        delegation_path=tmp_path / "missing.json",
    )
    assert snap["step5_readiness"]["step5_design_planning_allowed"] is True


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------


def test_discipline_invariants_block_is_present(tmp_path: Path) -> None:
    snap = dod.collect_snapshot(
        queue_path=tmp_path / "missing_q.json",
        release_gate_path=tmp_path / "missing_rg.json",
        bugfix_loop_path=tmp_path / "missing_bl.json",
        delegation_path=tmp_path / "missing_del.json",
    )
    inv = snap["discipline_invariants"]
    assert inv["mutates_upstream_artifacts"] is False
    assert inv["sends_notifications"] is False
    assert inv["writes_dashboard"] is False
    assert inv["auto_authorises_step5"] is False
    assert inv["operator_step5_authorisation_required"] is True


def test_digest_does_not_mutate_upstream_artifacts(tmp_path: Path) -> None:
    qp = _write(tmp_path / "q.json", _queue_payload())
    rgp = _write(tmp_path / "rg.json", _release_gate_payload())
    blp = _write(tmp_path / "bl.json", _bugfix_loop_payload())
    dp = _write(tmp_path / "del.json", _delegation_payload())
    before = {
        "q": qp.read_bytes(),
        "rg": rgp.read_bytes(),
        "bl": blp.read_bytes(),
        "del": dp.read_bytes(),
    }
    dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
    )
    assert qp.read_bytes() == before["q"]
    assert rgp.read_bytes() == before["rg"]
    assert blp.read_bytes() == before["bl"]
    assert dp.read_bytes() == before["del"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_artifact_bytes_are_deterministic_with_injected_timestamp(
    tmp_path: Path,
) -> None:
    qp = _write(tmp_path / "q.json", _queue_payload())
    rgp = _write(tmp_path / "rg.json", _release_gate_payload())
    blp = _write(tmp_path / "bl.json", _bugfix_loop_payload())
    dp = _write(tmp_path / "del.json", _delegation_payload())
    snap_a = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    snap_b = dod.collect_snapshot(
        queue_path=qp,
        release_gate_path=rgp,
        bugfix_loop_path=blp,
        delegation_path=dp,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    assert json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8") == json.dumps(
        snap_b, sort_keys=True, indent=2
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_append_is_bounded_at_max_entries(tmp_path: Path) -> None:
    history = tmp_path / "logs" / "development_operational_digest" / "history.jsonl"
    history.parent.mkdir(parents=True)
    for i in range(dod.MAX_HISTORY_ENTRIES + 5):
        dod._append_history(history, {"i": i})
    lines = history.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == dod.MAX_HISTORY_ENTRIES
    # The earliest entries dropped; the last entry is i=MAX+4.
    last = json.loads(lines[-1])
    assert last["i"] == dod.MAX_HISTORY_ENTRIES + 4


def test_history_entry_is_compact_projection() -> None:
    snapshot = {
        "generated_at_utc": "2026-05-07T00:00:00Z",
        "module_version": "v3.15.16.A12",
        "presence_count": 4,
        "step5_readiness": {
            "step5_ready": False,
            "criteria": {c: True for c in dod.STEP5_CRITERIA},
        },
        "operator_action_list": [{"kind": "x", "source": "y"}],
        "sources": {
            "queue": {"summary": {"total": 2}},
            "release_gate": {"summary": {"total": 1}},
            "bugfix_loop": {"summary": {"total": 0}},
            "delegation": {"summary": {"total": 1}},
        },
    }
    entry = dod._history_entry(snapshot)
    assert entry["presence_count"] == 4
    assert entry["step5_ready"] is False
    assert entry["queue_total"] == 2
    assert entry["operator_action_count"] == 1
    # No raw source payloads embedded.
    assert "sources" not in entry


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dod.__file__).read_text(encoding="utf-8")


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
    importlib.reload(dod)
    assert callable(dod.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(dod.SCHEMA_VERSION, str) and dod.SCHEMA_VERSION
    assert isinstance(dod.MODULE_VERSION, str) and dod.MODULE_VERSION
    assert "A12" in dod.MODULE_VERSION
