"""Unit tests for A16a — Intake Candidate Promotion Staging status."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_intake_promotion as dip
from reporting import development_intake_promotion_status as dips
from reporting import execution_authority as ea
from reporting import notification_event as ne


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_promotion_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic_promotion_payload(
    *,
    rows_total: int = 2,
    eligible: int = 1,
    human_needed: int = 1,
    blocked: int = 0,
    already_promoted: int = 0,
    classification_drift: int = 0,
    by_decision_state: dict[str, int] | None = None,
    by_kind: dict[str, int] | None = None,
    by_severity: dict[str, int] | None = None,
    by_decision: dict[str, int] | None = None,
    note: str = "promotion_intents_present",
    validation_warnings: list[str] | None = None,
) -> dict[str, Any]:
    decision_states = {s: 0 for s in dip.DECISION_STATES}
    if by_decision_state:
        decision_states.update(by_decision_state)
    kinds = {k: 0 for k in ne.EVENT_KINDS}
    if by_kind:
        kinds.update(by_kind)
    sevs = {s: 0 for s in ne.EVENT_SEVERITIES}
    if by_severity:
        sevs.update(by_severity)
    decisions = {
        ea.DECISION_AUTO_ALLOWED: 0,
        ea.DECISION_NEEDS_HUMAN: 0,
        ea.DECISION_PERMANENTLY_DENIED: 0,
    }
    if by_decision:
        decisions.update(by_decision)
    return {
        "schema_version": "1.0",
        "module_version": dip.MODULE_VERSION,
        "report_kind": "development_intake_promotion",
        "generated_at_utc": "2026-05-08T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "intake_artifact_path": "/tmp/logs/development_roadmap_intake/latest.json",
        "intake_artifact_available": True,
        "seed_path": "/tmp/docs/development_work_queue/seed.jsonl",
        "seed_present": False,
        "delegation_seed_path": "/tmp/docs/development_work_queue/delegation_seed.jsonl",
        "delegation_seed_present": False,
        "history_path": "/tmp/logs/development_intake_promotion/history.jsonl",
        "note": note,
        "validation_warnings": list(validation_warnings or []),
        "vocabularies": {
            "decision_states": list(dip.DECISION_STATES),
            "validation_warnings": list(dip.VALIDATION_WARNINGS),
            "promotion_targets": list(dip.PROMOTION_TARGETS),
            "notification_event_kinds": list(ne.EVENT_KINDS),
            "notification_event_severities": list(ne.EVENT_SEVERITIES),
        },
        "counts": {
            "total": rows_total,
            "eligible": eligible,
            "human_needed": human_needed,
            "blocked": blocked,
            "already_promoted": already_promoted,
            "classification_drift": classification_drift,
            "already_in_seed_jsonl": 0,
            "already_in_delegation_seed": 0,
            "by_decision_state": decision_states,
            "by_notification_event_kind": kinds,
            "by_notification_event_severity": sevs,
            "by_reclassified_execution_authority_decision": decisions,
        },
        "rows": [],
        "execution_authority_module_version": ea.MODULE_VERSION,
        "intake_module_version": "v0",
        "notification_event_module_version": ne.MODULE_VERSION,
        "discipline_invariants": {},
    }


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dips._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    with pytest.raises(ValueError):
        dips._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Status when upstream artefact is absent
# ---------------------------------------------------------------------------


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    snap = dips.collect_status(
        promotion_artifact_path=missing,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["promotion_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["counts"]["eligible"] == 0
    assert snap["counts"]["human_needed"] == 0
    assert snap["counts"]["blocked"] == 0
    assert snap["note"] == "promotion_artifact_absent"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    sp = snap["schema_pinned"]
    assert sp["decision_states"] == list(dip.DECISION_STATES)
    assert sp["promotion_targets"] == list(dip.PROMOTION_TARGETS)


# ---------------------------------------------------------------------------
# Status with synthetic upstream
# ---------------------------------------------------------------------------


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    payload = _synthetic_promotion_payload(
        rows_total=3,
        eligible=1,
        human_needed=1,
        blocked=1,
        classification_drift=1,
        by_decision_state={
            "eligible": 1,
            "human_needed": 1,
            "blocked": 1,
        },
        by_kind={
            "intake_candidate_eligible": 1,
            "queue_item_human_needed": 1,
            "intake_candidate_blocked": 1,
        },
        by_severity={
            "push_info": 1,
            "push_action_required": 1,
            "approval_required": 1,
        },
        by_decision={
            ea.DECISION_AUTO_ALLOWED: 1,
            ea.DECISION_NEEDS_HUMAN: 1,
            ea.DECISION_PERMANENTLY_DENIED: 1,
        },
    )
    artifact = _write_promotion_artifact(tmp_path, payload)
    snap = dips.collect_status(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["promotion_artifact_available"] is True
    assert snap["counts"]["total"] == 3
    assert snap["counts"]["eligible"] == 1
    assert snap["counts"]["human_needed"] == 1
    assert snap["counts"]["blocked"] == 1
    assert snap["counts"]["classification_drift"] == 1
    assert snap["counts"]["by_decision_state"]["eligible"] == 1
    assert snap["counts"]["by_decision_state"]["human_needed"] == 1
    assert snap["counts"]["by_decision_state"]["blocked"] == 1
    assert snap["counts"]["by_notification_event_kind"][
        "intake_candidate_eligible"
    ] == 1
    assert snap["counts"]["by_notification_event_kind"][
        "queue_item_human_needed"
    ] == 1
    assert snap["counts"]["by_notification_event_kind"][
        "intake_candidate_blocked"
    ] == 1
    assert snap["counts"]["by_notification_event_severity"]["push_info"] == 1
    assert snap["counts"]["by_notification_event_severity"][
        "push_action_required"
    ] == 1
    assert snap["counts"]["by_notification_event_severity"][
        "approval_required"
    ] == 1
    assert snap["counts"]["by_reclassified_execution_authority_decision"][
        ea.DECISION_AUTO_ALLOWED
    ] == 1
    assert snap["counts"]["by_reclassified_execution_authority_decision"][
        ea.DECISION_NEEDS_HUMAN
    ] == 1
    assert snap["counts"]["by_reclassified_execution_authority_decision"][
        ea.DECISION_PERMANENTLY_DENIED
    ] == 1
    assert snap["promotion_module_version"] == dip.MODULE_VERSION
    assert snap["promotion_note"] == "promotion_intents_present"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_status_validation_warnings_pass_through(tmp_path: Path) -> None:
    payload = _synthetic_promotion_payload(
        validation_warnings=["abc:classification_drift"],
    )
    artifact = _write_promotion_artifact(tmp_path, payload)
    snap = dips.collect_status(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["validation_warnings"] == ["abc:classification_drift"]


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = dips.collect_status(
        promotion_artifact_path=bad,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["promotion_artifact_available"] is False
    assert snap["note"] == "promotion_artifact_absent"


def test_status_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    payload = _synthetic_promotion_payload()
    artifact = _write_promotion_artifact(tmp_path, payload)
    snap_a = dips.collect_status(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_b = dips.collect_status(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    a_bytes = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    b_bytes = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert a_bytes == b_bytes


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dips.__file__).read_text(encoding="utf-8")


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
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src


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


def test_status_module_imports_cleanly() -> None:
    importlib.reload(dips)
    assert callable(dips.collect_status)
