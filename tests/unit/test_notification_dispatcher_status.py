"""Unit tests for N2a — Notification Dispatcher status summary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import execution_authority as ea
from reporting import notification_dispatcher as nd
from reporting import notification_dispatcher_status as nds
from reporting import notification_event as ne


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_dispatcher_artifact(
    tmp_path: Path, payload: dict[str, Any]
) -> Path:
    p = tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic_dispatcher_payload(
    *,
    events: list[dict[str, Any]] | None = None,
    note: str = "events_present",
) -> dict[str, Any]:
    events = events or []
    counts = {
        "total": len(events),
        "ready": sum(1 for e in events if e.get("delivery_intent") == "ready"),
        "suppressed": sum(
            1 for e in events if e.get("delivery_intent") == "suppressed"
        ),
        "suppressed_cooldown": 0,
        "duplicate_within_window": 0,
        "rate_limited": 0,
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_delivery_intent": {d: 0 for d in nd.DELIVERY_INTENTS},
        "by_source_module": {m: 0 for m in nd.SOURCE_MODULES},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }
    for ev in events:
        kind = ev.get("event_kind")
        if isinstance(kind, str) and kind in counts["by_event_kind"]:
            counts["by_event_kind"][kind] += 1
        sev = ev.get("event_severity")
        if isinstance(sev, str) and sev in counts["by_event_severity"]:
            counts["by_event_severity"][sev] += 1
        di = ev.get("delivery_intent")
        if di in counts["by_delivery_intent"]:
            counts["by_delivery_intent"][di] += 1
        sm = ev.get("source_module")
        if isinstance(sm, str) and sm in counts["by_source_module"]:
            counts["by_source_module"][sm] += 1
        d = ev.get("execution_authority_decision")
        if d in counts["by_execution_authority_decision"]:
            counts["by_execution_authority_decision"][d] += 1
    return {
        "schema_version": "1.0",
        "module_version": nd.MODULE_VERSION,
        "report_kind": "notification_dispatcher",
        "generated_at_utc": "2026-05-09T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "sources_read": [],
        "events_history_path": "/tmp/events.jsonl",
        "note": note,
        "validation_warnings": [],
        "vocabularies": {},
        "cooldown_seconds_per_event_kind": dict(
            nd.COOLDOWN_SECONDS_PER_EVENT_KIND
        ),
        "counts": counts,
        "events": events,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "intake_promotion_module_version": "v0",
        "step5_module_version": "v0",
        "roadmap_intake_module_version": "v0",
        "discipline_invariants": {},
    }


def _ev(
    *,
    event_id: str = "eid_001",
    event_kind: str = "intake_candidate_eligible",
    event_severity: str = "push_info",
    delivery_intent: str = "ready",
    source_module: str = "development_intake_promotion",
    source_id: str = "src_001",
    execution_authority_decision: str = ea.DECISION_AUTO_ALLOWED,
    title: str = "Title",
    summary: str = "Summary",
    target_path: str = "docs/x.md",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_severity": event_severity,
        "delivery_intent": delivery_intent,
        "source_module": source_module,
        "source_artifact_path": "logs/x/latest.json",
        "source_id": source_id,
        "title": title,
        "summary": summary,
        "risk_class": "LOW",
        "execution_authority_decision": execution_authority_decision,
        "acceptance_criteria": [],
        "target_path": target_path,
        "evidence_hash": "h",
        "created_at": "2026-05-09T00:00:00Z",
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        nds._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_dispatcher_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    with pytest.raises(ValueError):
        nds._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Status when upstream artefact is absent
# ---------------------------------------------------------------------------


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    snap = nds.collect_status(
        dispatcher_artifact_path=missing,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["dispatcher_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["operator_action_list"] == []
    assert snap["note"] == "dispatcher_artifact_absent"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    sp = snap["schema_pinned"]
    assert sp["delivery_intents"] == list(nd.DELIVERY_INTENTS)
    assert sp["source_modules"] == list(nd.SOURCE_MODULES)


# ---------------------------------------------------------------------------
# Status with synthetic upstream
# ---------------------------------------------------------------------------


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    events = [
        _ev(
            event_id="e_a",
            event_kind="intake_candidate_eligible",
            event_severity="push_info",
            delivery_intent="ready",
        ),
        _ev(
            event_id="e_b",
            event_kind="step5_cycle_planned",
            event_severity="silent",
            delivery_intent="suppressed",
            source_module="development_step5_loop",
        ),
        _ev(
            event_id="e_c",
            event_kind="step5_cycle_needs_human",
            event_severity="push_action_required",
            delivery_intent="ready",
            source_module="development_step5_loop",
        ),
    ]
    payload = _synthetic_dispatcher_payload(events=events)
    artifact = _write_dispatcher_artifact(tmp_path, payload)
    snap = nds.collect_status(
        dispatcher_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["dispatcher_artifact_available"] is True
    assert snap["counts"]["total"] == 3
    assert snap["counts"]["ready"] == 2
    assert snap["counts"]["suppressed"] == 1
    assert snap["counts"]["by_event_kind"]["intake_candidate_eligible"] == 1
    assert snap["counts"]["by_event_kind"]["step5_cycle_planned"] == 1
    assert snap["counts"]["by_event_kind"]["step5_cycle_needs_human"] == 1
    assert snap["counts"]["by_event_severity"]["push_info"] == 1
    assert snap["counts"]["by_event_severity"]["silent"] == 1
    assert snap["counts"]["by_event_severity"]["push_action_required"] == 1
    assert (
        snap["counts"]["by_source_module"]["development_intake_promotion"]
        == 1
    )
    assert snap["counts"]["by_source_module"]["development_step5_loop"] == 2
    # Operator-attention events: only the push_action_required ready one.
    assert snap["counts"]["operator_attention_ready"] == 1
    assert len(snap["operator_action_list"]) == 1
    assert snap["operator_action_list"][0]["event_id"] == "e_c"
    assert snap["operator_action_list"][0]["event_kind"] == "step5_cycle_needs_human"


def test_operator_action_list_only_includes_ready_attention_events(
    tmp_path: Path,
) -> None:
    events = [
        # Suppressed approval_required must NOT appear.
        _ev(
            event_id="e_a",
            event_kind="pr_merge_approval_required",
            event_severity="approval_required",
            delivery_intent="suppressed_cooldown",
        ),
        # ready + push_info is below the attention threshold.
        _ev(
            event_id="e_b",
            event_kind="intake_candidate_eligible",
            event_severity="push_info",
            delivery_intent="ready",
        ),
        # ready + critical → attention.
        _ev(
            event_id="e_c",
            event_kind="governance_violation_detected",
            event_severity="critical",
            delivery_intent="ready",
        ),
    ]
    payload = _synthetic_dispatcher_payload(events=events)
    artifact = _write_dispatcher_artifact(tmp_path, payload)
    snap = nds.collect_status(
        dispatcher_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    ids = {row["event_id"] for row in snap["operator_action_list"]}
    assert ids == {"e_c"}


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = nds.collect_status(
        dispatcher_artifact_path=bad,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["dispatcher_artifact_available"] is False
    assert snap["note"] == "dispatcher_artifact_absent"


def test_status_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    payload = _synthetic_dispatcher_payload()
    artifact = _write_dispatcher_artifact(tmp_path, payload)
    snap_a = nds.collect_status(
        dispatcher_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    snap_b = nds.collect_status(
        dispatcher_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert (
        json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
        == json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    )


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(nds.__file__).read_text(encoding="utf-8")


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


def test_no_web_push_library_imports_status() -> None:
    src = _module_source()
    for forbidden in ("pywebpush", "from pywebpush", "from web_push"):
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
    importlib.reload(nds)
    assert callable(nds.collect_status)
