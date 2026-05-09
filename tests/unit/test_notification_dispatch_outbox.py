"""Unit tests for N2b-1 — Notification Dispatch Outbox (stub provider).

The module is a dry-run dispatch outbox. Real push is BLOCKED at the
code level by closed-vocabulary tests and source-text scans. Audit
emission is gated to non-`--no-write` runs.

Synthetic deterministic fixtures only.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import agent_audit as _audit
from reporting import notification_dispatch_outbox as ndo
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_logs(tmp_path: Path) -> tuple[Path, Path]:
    dispatcher = (
        tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    )
    outbox = (
        tmp_path / "logs" / "notification_dispatch_outbox" / "outbox.jsonl"
    )
    for p in (dispatcher, outbox):
        p.parent.mkdir(parents=True, exist_ok=True)
    return dispatcher, outbox


def _ev(
    *,
    event_id: str = "eid_001",
    event_kind: str = "intake_candidate_eligible",
    event_severity: str = "push_info",
    delivery_intent: str = "ready",
    source_module: str = "development_intake_promotion",
    source_id: str = "src_001",
    title: str = "Synthetic eligible candidate title",
    summary: str = "decision_state=eligible; risk=LOW; target=docs/x.md",
    target_path: str = "docs/x.md",
    risk_class: str = "LOW",
    execution_authority_decision: str = "AUTO_ALLOWED",
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
        "risk_class": risk_class,
        "execution_authority_decision": execution_authority_decision,
        "acceptance_criteria": [],
        "target_path": target_path,
        "evidence_hash": "h",
        "created_at": "2026-05-09T00:00:00Z",
        "notes": "",
    }


def _dispatcher_payload(
    *, events: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    events = events or []
    return {
        "schema_version": "1.0",
        "module_version": nd.MODULE_VERSION,
        "report_kind": "notification_dispatcher",
        "generated_at_utc": "2026-05-09T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "events": events,
    }


def _write_dispatcher(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_outbound_delivery_intents_pinned_exactly() -> None:
    assert ndo.OUTBOUND_DELIVERY_INTENTS == (
        "sent",
        "duplicate",
        "skipped_not_ready",
        "rate_limited_outbound",
        "failed_secret_check",
        "failed_stub_provider",
    )


def test_audit_event_names_pinned_exactly() -> None:
    assert ndo.AUDIT_EVENT_NAMES == (
        "push_dispatch_attempt",
        "push_dispatch_success",
        "push_dispatch_skipped_duplicate",
        "push_dispatch_skipped_rate_limit",
        "push_dispatch_failure",
    )


def test_push_payload_keys_pinned_exactly_and_ordered() -> None:
    assert ndo.PUSH_PAYLOAD_KEYS == (
        "event_id",
        "event_kind",
        "event_severity",
        "title",
        "summary",
        "open_at",
    )


def test_outbox_record_schema_keys_pinned_exactly_and_ordered() -> None:
    assert ndo.OUTBOX_RECORD_SCHEMA_KEYS == (
        "event_id",
        "event_kind",
        "event_severity",
        "source_module",
        "source_id",
        "outbound_delivery_intent",
        "payload",
        "stub_provider_url",
        "stub_provider_status",
        "stub_provider_result",
        "secret_guard_ok",
        "attempted_at",
        "audit_event_seq",
    )


def test_max_dispatch_per_cycle_pinned() -> None:
    assert ndo.MAX_DISPATCH_PER_CYCLE == 16


def test_max_outbox_history_pinned() -> None:
    assert ndo.MAX_OUTBOX_HISTORY == 500


def test_artifact_paths_under_logs_only() -> None:
    assert ndo.ARTIFACT_RELATIVE_PATH.startswith(
        "logs/notification_dispatch_outbox/"
    )
    assert ndo.OUTBOX_JSONL_RELATIVE_PATH.startswith(
        "logs/notification_dispatch_outbox/"
    )
    assert "research/" not in ndo.ARTIFACT_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Atomic-write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_outbox_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        ndo._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatcher" / "latest.json"
    with pytest.raises(ValueError):
        ndo._atomic_write_json(bad, {"x": 1})


def test_outbox_append_refuses_non_outbox_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "outbox.jsonl"
    with pytest.raises(ValueError):
        ndo._append_outbox_history(bad, [])


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_step5_invariants_pinned() -> None:
    assert ndo.step5_implementation_allowed is False
    assert ndo.STEP5_ENABLED_SUBSTAGE == "none"


def test_snapshot_carries_step5_invariants(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["step5_enabled_substage"] == "none"
    assert snap["step5_implementation_allowed"] is False


def test_discipline_invariants_present(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
    )
    inv = snap["discipline_invariants"]
    assert inv["sends_real_push"] is False
    assert inv["invokes_network"] is False
    assert inv["invokes_subprocess"] is False
    assert inv["reads_subscription_files"] is False
    assert inv["reads_vapid_keys"] is False
    assert inv["writes_dashboard_or_frontend"] is False
    assert inv["opens_mobile_inbox"] is False
    assert inv["mints_approval_token"] is False
    assert inv["invokes_merge_or_deploy"] is False
    assert inv["uses_real_push_provider"] is False
    assert inv["secret_redactor_invoked"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "dispatcher_artifact_path",
        "dispatcher_artifact_available",
        "outbox_history_path",
        "stub_provider_url",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "records",
        "notification_dispatcher_module_version",
        "notification_event_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "notification_dispatch_outbox"


# ---------------------------------------------------------------------------
# Ready vs not-ready filtering
# ---------------------------------------------------------------------------


def test_only_ready_records_reach_stub_provider(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[
            _ev(event_id="r_01", delivery_intent="ready"),
            _ev(event_id="s_01", delivery_intent="suppressed"),
            _ev(event_id="d_01", delivery_intent="duplicate_within_window"),
            _ev(event_id="c_01", delivery_intent="suppressed_cooldown"),
            _ev(event_id="x_01", delivery_intent="rate_limited"),
        ]),
    )
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    by_id = {r["event_id"]: r for r in snap["records"]}
    assert by_id["r_01"]["outbound_delivery_intent"] == "sent"
    assert by_id["s_01"]["outbound_delivery_intent"] == "skipped_not_ready"
    assert by_id["d_01"]["outbound_delivery_intent"] == "skipped_not_ready"
    assert by_id["c_01"]["outbound_delivery_intent"] == "skipped_not_ready"
    assert by_id["x_01"]["outbound_delivery_intent"] == "skipped_not_ready"


def test_real_a16a_eligible_event_becomes_sent_via_stub(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    real = _ev(
        event_id="abc12345abc12345abc12345abc12345",
        event_kind="intake_candidate_eligible",
        event_severity="push_info",
        delivery_intent="ready",
        source_module="development_intake_promotion",
        source_id="qre_v3_15_16_addendum_source_manifest_001",
        title="Draft diagnostic-source manifest",
    )
    _write_dispatcher(dispatcher, _dispatcher_payload(events=[real]))
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert len(snap["records"]) == 1
    rec = snap["records"][0]
    assert set(rec.keys()) == set(ndo.OUTBOX_RECORD_SCHEMA_KEYS)
    assert rec["outbound_delivery_intent"] == "sent"
    assert rec["stub_provider_status"] == "accepted_offline"
    assert rec["stub_provider_url"] == "stub://web-push-provider-disabled"
    assert rec["stub_provider_result"] == "would_send"
    assert rec["secret_guard_ok"] is True
    assert set(rec["payload"].keys()) == set(ndo.PUSH_PAYLOAD_KEYS)
    assert rec["payload"]["event_id"] == real["event_id"]
    assert rec["payload"]["event_kind"] == "intake_candidate_eligible"
    assert rec["payload"]["event_severity"] == "push_info"
    assert rec["payload"]["open_at"].startswith("/agent-control/inbox?event=")
    assert rec["payload"]["open_at"].endswith(real["event_id"])


# ---------------------------------------------------------------------------
# Dedupe / rate-limit / failure modes
# ---------------------------------------------------------------------------


def test_duplicate_event_id_becomes_duplicate(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[_ev(event_id="dup_001")]),
    )
    # Pre-seed outbox with the same event_id.
    outbox.write_text(
        json.dumps(
            {
                "event_id": "dup_001",
                "event_kind": "intake_candidate_eligible",
                "outbound_delivery_intent": "sent",
                "stub_provider_status": "accepted_offline",
                "attempted_at": "2026-05-09T00:00:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:01:00Z",
    )
    assert snap["records"][0]["outbound_delivery_intent"] == "duplicate"


def test_rate_limit_excess_becomes_rate_limited_outbound(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    events = [_ev(event_id=f"rl_{i:03d}") for i in range(20)]
    _write_dispatcher(dispatcher, _dispatcher_payload(events=events))
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    intents = [r["outbound_delivery_intent"] for r in snap["records"]]
    assert intents.count("sent") == ndo.MAX_DISPATCH_PER_CYCLE
    assert intents.count("rate_limited_outbound") == 20 - ndo.MAX_DISPATCH_PER_CYCLE


def test_outbox_jsonl_bounded_to_max(tmp_path: Path) -> None:
    """outbox.jsonl is trimmed to <= MAX_OUTBOX_HISTORY rows on append."""
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[_ev(event_id="bound_001")]),
    )
    # Pre-fill with 600 rows.
    lines = [
        json.dumps(
            {
                "event_id": f"existing_{i:04d}",
                "event_kind": "intake_candidate_eligible",
                "outbound_delivery_intent": "sent",
                "stub_provider_status": "accepted_offline",
                "attempted_at": "2026-04-30T00:00:00Z",
            },
            sort_keys=True,
        )
        for i in range(600)
    ]
    outbox.write_text("\n".join(lines) + "\n", encoding="utf-8")
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    ndo._append_outbox_history(outbox, snap.get("records") or [])
    bounded = [
        line for line in outbox.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(bounded) <= ndo.MAX_OUTBOX_HISTORY


# ---------------------------------------------------------------------------
# Payload guarantees
# ---------------------------------------------------------------------------


def test_payload_contains_no_decision_verb(tmp_path: Path) -> None:
    """Even if upstream title contains a decision verb, the outbox
    must mark the record failed_secret_check."""
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[
            _ev(event_id="dv_001", title="Please approve this PR now"),
        ]),
    )
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    rec = snap["records"][0]
    assert rec["outbound_delivery_intent"] == "failed_secret_check"


def test_payload_contains_no_diff_or_pem(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[
            _ev(event_id="diff_001", summary="diff --git a/x b/x change"),
        ]),
    )
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
    )
    rec = snap["records"][0]
    assert rec["outbound_delivery_intent"] == "failed_secret_check"


def test_payload_contains_no_secret(tmp_path: Path) -> None:
    """A credential-shaped string in upstream forces failed_secret_check
    via assert_no_secrets at the record-build stage. The wrapper-level
    assert_no_secrets at snapshot time would also raise, but we never
    reach it because the per-record guard catches first."""
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[
            _ev(
                event_id="sec_001",
                summary="leaked sk-ant-api03-very-bad-secret-here-please-break",
            ),
        ]),
    )
    # The per-record guard catches first, so the snapshot does not raise.
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
    )
    rec = snap["records"][0]
    assert rec["outbound_delivery_intent"] == "failed_secret_check"
    assert rec["secret_guard_ok"] is False


def test_secret_guard_invoked_on_every_payload_path() -> None:
    """The per-record path explicitly calls assert_no_secrets — the
    function name must appear in source."""
    src = Path(ndo.__file__).read_text(encoding="utf-8")
    assert "assert_no_secrets" in src


def test_stub_provider_returns_offline_accept_for_valid_payload() -> None:
    payload = {
        "event_id": "x",
        "event_kind": "intake_candidate_eligible",
        "event_severity": "push_info",
        "title": "t",
        "summary": "s",
        "open_at": "/agent-control/inbox?event=x",
    }
    result = ndo.stub_provider(payload)
    assert result["url"] == "stub://web-push-provider-disabled"
    assert result["status"] == "accepted_offline"
    assert result["result"] == "would_send"


def test_stub_provider_rejects_invalid_payload_shape() -> None:
    bad = {"event_id": "x"}  # missing keys
    result = ndo.stub_provider(bad)
    assert result["status"] == "rejected_shape"
    assert result["result"] == "invalid_payload_keys"


# ---------------------------------------------------------------------------
# --no-write discipline + audit emission boundary
# ---------------------------------------------------------------------------


def test_no_write_writes_no_files_and_no_audit(tmp_path: Path, monkeypatch) -> None:
    """The CLI in --no-write mode must:
    * not write logs/notification_dispatch_outbox/latest.json,
    * not append to logs/notification_dispatch_outbox/outbox.jsonl,
    * not call agent_audit.append_event.
    """
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[_ev(event_id="nw_001")]),
    )
    # Monkeypatch the module's defaults so --no-write doesn't touch
    # the real repo paths.
    monkeypatch.setattr(ndo, "ARTIFACT_LATEST", tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json")
    monkeypatch.setattr(ndo, "OUTBOX_JSONL_PATH", outbox)
    monkeypatch.setattr(nd, "ARTIFACT_LATEST", dispatcher)

    audit_calls: list[Any] = []

    def fake_append(event, *, base_dir=None):  # type: ignore[no-redef]
        audit_calls.append(event)
        return {"sequence_id": 999}

    monkeypatch.setattr(_audit, "append_event", fake_append)

    rc = ndo.main(["--no-write", "--indent", "0"])
    assert rc == 0
    # No files written.
    assert not (tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json").exists()
    # outbox.jsonl exists from _make_logs but should be empty (we never wrote).
    text = outbox.read_text(encoding="utf-8") if outbox.exists() else ""
    assert text == ""
    # No audit calls.
    assert audit_calls == []


def test_normal_run_writes_and_emits_audit(tmp_path: Path, monkeypatch) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[_ev(event_id="nr_001")]),
    )
    artifact_latest = (
        tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    )
    monkeypatch.setattr(ndo, "ARTIFACT_LATEST", artifact_latest)
    monkeypatch.setattr(ndo, "OUTBOX_JSONL_PATH", outbox)
    monkeypatch.setattr(nd, "ARTIFACT_LATEST", dispatcher)

    audit_calls: list[Any] = []

    def fake_append(event, *, base_dir=None):  # type: ignore[no-redef]
        audit_calls.append(event)
        return {"sequence_id": len(audit_calls)}

    monkeypatch.setattr(_audit, "append_event", fake_append)

    rc = ndo.main(["--indent", "0"])
    assert rc == 0
    assert artifact_latest.is_file()
    # outbox.jsonl appended.
    text = outbox.read_text(encoding="utf-8")
    assert "nr_001" in text
    # Two audit events per record (attempt + success).
    assert len(audit_calls) == 2
    assert audit_calls[0]["event"] == "push_dispatch_attempt"
    assert audit_calls[1]["event"] == "push_dispatch_success"
    assert audit_calls[0]["autonomy_level_claimed"] == 0
    assert audit_calls[1]["autonomy_level_claimed"] == 0


# ---------------------------------------------------------------------------
# Determinism + sorting
# ---------------------------------------------------------------------------


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[_ev(event_id="det_001")]),
    )
    snap_a = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    snap_b = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    a = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    b = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert a == b


def test_records_sort_stably(tmp_path: Path) -> None:
    dispatcher, outbox = _make_logs(tmp_path)
    _write_dispatcher(
        dispatcher,
        _dispatcher_payload(events=[
            _ev(event_id="z_03"),
            _ev(event_id="a_01"),
            _ev(event_id="m_02"),
        ]),
    )
    snap = ndo.collect_snapshot(
        dispatcher_artifact_path=dispatcher,
        outbox_history_path=outbox,
    )
    keys = [(r["source_module"], r["event_id"]) for r in snap["records"]]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(ndo.__file__).read_text(encoding="utf-8")


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
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src, forbidden


def test_no_web_push_library_imports() -> None:
    src = _module_source()
    for forbidden in (
        "import pywebpush",
        "from pywebpush",
        "import webpush",
        "from webpush",
        "import web_push",
        "from web_push",
    ):
        assert forbidden not in src, forbidden


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
        "shell=True",
    ):
        assert forbidden not in src, forbidden


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
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


def test_no_subscription_or_vapid_code_paths() -> None:
    """Defense in depth: module must not contain code that opens a
    subscription file or VAPID key. Documentation references in
    docstrings are explicitly allowed (we document what we DO NOT
    do); this test scans for code-shaped patterns only."""
    src = _module_source()
    forbidden_code_patterns = (
        "subscriptions.json",
        "web_push_subscriptions",
        "vapid_public.txt",
        "vapid_private",
        "VAPID_PRIVATE",
        "WEB_PUSH_VAPID",
    )
    for forbidden in forbidden_code_patterns:
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(ndo)
    assert callable(ndo.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(ndo)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "notification_dispatch_outbox.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_real_push_in_n2b1() -> None:
    text = _doc_text().lower()
    assert "no real push" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    text = _doc_text().lower()
    assert "no approval can happen from a notification click alone" in text


def test_doc_states_n2b2_n2b3_n3_n4_n5_remain_unimplemented() -> None:
    text = _doc_text().lower()
    for marker in ("n2b-2", "n2b-3", "n3", "n4", "n5"):
        assert marker in text, marker
    assert "out of scope" in text or "remain unimplemented" in text or "unimplemented" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    import re

    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window
