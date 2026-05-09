"""Unit tests for N2b-1 — Dispatch Outbox status summary."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import notification_dispatch_outbox as ndo
from reporting import notification_dispatch_outbox_status as ndos
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_outbox_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _synthetic_outbox_payload(
    *,
    records: list[dict[str, Any]] | None = None,
    note: str = "dispatch_records_present",
) -> dict[str, Any]:
    records = records or []
    counts = {
        "total": len(records),
        "sent": 0,
        "duplicate": 0,
        "skipped_not_ready": 0,
        "rate_limited_outbound": 0,
        "failed_secret_check": 0,
        "failed_stub_provider": 0,
        "by_outbound_delivery_intent": {
            v: 0 for v in ndo.OUTBOUND_DELIVERY_INTENTS
        },
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_source_module": {m: 0 for m in nd.SOURCE_MODULES},
    }
    for r in records:
        di = r.get("outbound_delivery_intent")
        if di in counts:
            counts[di] = counts[di] + 1
        if di in counts["by_outbound_delivery_intent"]:
            counts["by_outbound_delivery_intent"][di] += 1
        ek = r.get("event_kind")
        if isinstance(ek, str) and ek in counts["by_event_kind"]:
            counts["by_event_kind"][ek] += 1
        es = r.get("event_severity")
        if isinstance(es, str) and es in counts["by_event_severity"]:
            counts["by_event_severity"][es] += 1
        sm = r.get("source_module")
        if isinstance(sm, str) and sm in counts["by_source_module"]:
            counts["by_source_module"][sm] += 1
    return {
        "schema_version": "1.0",
        "module_version": ndo.MODULE_VERSION,
        "report_kind": "notification_dispatch_outbox",
        "generated_at_utc": "2026-05-09T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "dispatcher_artifact_path": "/tmp/dispatcher.json",
        "dispatcher_artifact_available": True,
        "outbox_history_path": "/tmp/outbox.jsonl",
        "stub_provider_url": "stub://web-push-provider-disabled",
        "note": note,
        "validation_warnings": [],
        "vocabularies": {},
        "counts": counts,
        "records": records,
        "notification_dispatcher_module_version": nd.MODULE_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "discipline_invariants": {},
    }


def _rec(
    *,
    event_id: str = "rec_001",
    event_kind: str = "intake_candidate_eligible",
    event_severity: str = "push_info",
    source_module: str = "development_intake_promotion",
    outbound_delivery_intent: str = "sent",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_severity": event_severity,
        "source_module": source_module,
        "source_id": "src_001",
        "outbound_delivery_intent": outbound_delivery_intent,
        "payload": {},
        "stub_provider_url": "stub://web-push-provider-disabled",
        "stub_provider_status": "accepted_offline",
        "stub_provider_result": "would_send",
        "secret_guard_ok": True,
        "attempted_at": "2026-05-09T00:00:00Z",
        "audit_event_seq": None,
    }


# ---------------------------------------------------------------------------
# Atomic-write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_status_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        ndos._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_outbox_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    with pytest.raises(ValueError):
        ndos._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Status when upstream artefact is absent
# ---------------------------------------------------------------------------


def test_status_when_artifact_absent(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    snap = ndos.collect_status(
        outbox_artifact_path=missing,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["outbox_artifact_available"] is False
    assert snap["counts"]["total"] == 0
    assert snap["operator_attention_count"] == 0
    assert snap["note"] == "outbox_artifact_absent"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    sp = snap["schema_pinned"]
    assert sp["outbound_delivery_intents"] == list(
        ndo.OUTBOUND_DELIVERY_INTENTS
    )
    assert sp["push_payload_keys"] == list(ndo.PUSH_PAYLOAD_KEYS)


# ---------------------------------------------------------------------------
# Status with synthetic upstream
# ---------------------------------------------------------------------------


def test_status_counts_mirror_upstream(tmp_path: Path) -> None:
    records = [
        _rec(event_id="r_a", outbound_delivery_intent="sent"),
        _rec(event_id="r_b", outbound_delivery_intent="duplicate"),
        _rec(
            event_id="r_c",
            outbound_delivery_intent="failed_secret_check",
        ),
        _rec(
            event_id="r_d",
            outbound_delivery_intent="failed_stub_provider",
        ),
        _rec(
            event_id="r_e",
            outbound_delivery_intent="rate_limited_outbound",
        ),
    ]
    payload = _synthetic_outbox_payload(records=records)
    artifact = _write_outbox_artifact(tmp_path, payload)
    snap = ndos.collect_status(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["outbox_artifact_available"] is True
    assert snap["counts"]["total"] == 5
    assert snap["counts"]["sent"] == 1
    assert snap["counts"]["duplicate"] == 1
    assert snap["counts"]["failed_secret_check"] == 1
    assert snap["counts"]["failed_stub_provider"] == 1
    assert snap["counts"]["rate_limited_outbound"] == 1
    assert snap["counts"]["by_outbound_delivery_intent"]["sent"] == 1
    assert snap["counts"]["by_outbound_delivery_intent"]["duplicate"] == 1
    assert snap["operator_attention_count"] == 2
    assert snap["outbox_module_version"] == ndo.MODULE_VERSION
    assert snap["outbox_note"] == "dispatch_records_present"
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_operator_attention_only_counts_failures(tmp_path: Path) -> None:
    records = [
        _rec(event_id="r_a", outbound_delivery_intent="sent"),
        _rec(event_id="r_b", outbound_delivery_intent="duplicate"),
        _rec(event_id="r_c", outbound_delivery_intent="skipped_not_ready"),
        _rec(event_id="r_d", outbound_delivery_intent="rate_limited_outbound"),
    ]
    payload = _synthetic_outbox_payload(records=records)
    artifact = _write_outbox_artifact(tmp_path, payload)
    snap = ndos.collect_status(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["operator_attention_count"] == 0


def test_status_handles_corrupt_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = ndos.collect_status(
        outbox_artifact_path=bad,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["outbox_artifact_available"] is False
    assert snap["note"] == "outbox_artifact_absent"


def test_status_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    payload = _synthetic_outbox_payload()
    artifact = _write_outbox_artifact(tmp_path, payload)
    snap_a = ndos.collect_status(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    snap_b = ndos.collect_status(
        outbox_artifact_path=artifact,
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
    return Path(ndos.__file__).read_text(encoding="utf-8")


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
    for forbidden in (
        "import pywebpush",
        "from pywebpush",
        "import webpush",
        "from webpush",
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
    importlib.reload(ndos)
    assert callable(ndos.collect_status)
