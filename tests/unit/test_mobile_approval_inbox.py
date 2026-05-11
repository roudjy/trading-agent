"""Unit tests for N3a — Mobile Approval Inbox projector."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import mobile_approval_inbox as mai


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _outbox_record(
    *,
    event_id: str = "eid_001abc",
    event_kind: str = "intake_candidate_eligible",
    event_severity: str = "push_info",
    outbound_delivery_intent: str = "sent",
    source_id: str = "src_001",
    title: str = "Synthetic eligible candidate",
    summary: str = "decision_state=eligible; risk=LOW",
    open_at: str = "/agent-control/inbox?event=eid_001abc",
    endpoint_hash: str = "deadbeefdeadbeef",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_severity": event_severity,
        "outbound_delivery_intent": outbound_delivery_intent,
        "source_id": source_id,
        "endpoint_hash": endpoint_hash,
        "payload": {
            "event_id": event_id,
            "event_kind": event_kind,
            "event_severity": event_severity,
            "title": title,
            "summary": summary,
            "open_at": open_at,
        },
    }


def _write_outbox(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    p = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    p.parent.mkdir(parents=True)
    payload = {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "notification_dispatch_outbox",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "records": records,
    }
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_attention_levels_pinned_exactly() -> None:
    assert mai.ATTENTION_LEVELS == (
        "informational",
        "needs_review",
        "blocked_attention",
        "critical_attention",
    )


def test_inbox_decision_states_pinned_exactly() -> None:
    assert mai.INBOX_DECISION_STATES == (
        "pending",
        "acknowledged",
        "approved",
        "rejected",
        "expired",
        "superseded",
    )


def test_source_modules_pinned() -> None:
    assert mai.SOURCE_MODULES == ("notification_dispatch_outbox",)


def test_validation_warnings_pinned() -> None:
    assert mai.VALIDATION_WARNINGS == (
        "outbox_artifact_absent",
        "outbox_artifact_unparseable",
        "outbox_record_invalid",
        "decision_verb_redacted_in_summary",
    )


def test_inbox_row_keys_pinned_exactly_and_ordered() -> None:
    assert mai.INBOX_ROW_KEYS == (
        "inbox_row_id",
        "event_id",
        "event_kind",
        "event_severity",
        "source_module",
        "source_id",
        "endpoint_hash",
        "outbound_delivery_intent",
        "attention_level",
        "decision_state",
        "title",
        "summary",
        "open_at",
        "created_at",
    )


def test_max_inbox_rows_bounded() -> None:
    assert mai.MAX_INBOX_ROWS == 64


def test_step5_invariants_pinned() -> None:
    assert mai.step5_implementation_allowed is False
    assert mai.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_inbox_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        mai._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_upstream_outbox_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    with pytest.raises(ValueError):
        mai._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Attention-level classification
# ---------------------------------------------------------------------------


def test_classify_informational_for_push_info_sent() -> None:
    rec = _outbox_record(event_severity="push_info", outbound_delivery_intent="sent")
    assert mai.classify_attention(rec) == "informational"


def test_classify_needs_review_for_push_action_required() -> None:
    rec = _outbox_record(event_severity="push_action_required")
    assert mai.classify_attention(rec) == "needs_review"


def test_classify_needs_review_for_approval_required() -> None:
    rec = _outbox_record(event_severity="approval_required")
    assert mai.classify_attention(rec) == "needs_review"


def test_classify_critical_attention_for_critical_severity() -> None:
    rec = _outbox_record(event_severity="critical")
    assert mai.classify_attention(rec) == "critical_attention"


def test_classify_blocked_attention_for_failed_secret_check() -> None:
    rec = _outbox_record(outbound_delivery_intent="failed_secret_check")
    assert mai.classify_attention(rec) == "blocked_attention"


def test_classify_blocked_attention_for_failed_stub_provider() -> None:
    rec = _outbox_record(outbound_delivery_intent="failed_stub_provider")
    assert mai.classify_attention(rec) == "blocked_attention"


def test_classify_blocked_attention_for_rate_limited_outbound() -> None:
    rec = _outbox_record(outbound_delivery_intent="rate_limited_outbound")
    assert mai.classify_attention(rec) == "blocked_attention"


def test_classify_non_dict_is_informational() -> None:
    # Non-dict input never crashes and defaults to informational.
    assert mai.classify_attention("not a dict") == "informational"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Decision-state invariant: N3a NEVER emits anything other than pending
# ---------------------------------------------------------------------------


def test_decision_state_always_pending_even_with_upstream_approved(
    tmp_path: Path,
) -> None:
    """Even if the upstream record carries a (hypothetical)
    `decision_state="approved"`, N3a's output row MUST set
    decision_state="pending". N3a is forbidden from advancing the
    decision state — that is N4 territory."""
    rec = _outbox_record(event_severity="approval_required")
    # Inject a hypothetical upstream decision_state — N3a should ignore it.
    rec["decision_state"] = "approved"
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert len(snap["rows"]) == 1
    assert snap["rows"][0]["decision_state"] == "pending"


def test_decision_state_always_pending_for_every_record(
    tmp_path: Path,
) -> None:
    """Across a mixed batch of upstream rows, EVERY emitted row has
    decision_state == "pending"."""
    records = [
        _outbox_record(event_id=f"e{i:03d}", event_severity="approval_required")
        for i in range(5)
    ]
    artifact = _write_outbox(tmp_path, records)
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    for row in snap["rows"]:
        assert row["decision_state"] == "pending"


# ---------------------------------------------------------------------------
# Decision-verb redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    ["approve", "reject", "merge ", " merge", "deploy"],
)
def test_decision_verb_in_title_is_redacted(
    tmp_path: Path, forbidden: str
) -> None:
    rec = _outbox_record(
        title=f"please {forbidden} this",
        summary="bounded summary",
    )
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    row = snap["rows"][0]
    assert row["title"] == "[redacted-decision-verb]"
    assert "decision_verb_redacted_in_summary" in snap["validation_warnings"]


def test_decision_verb_in_summary_is_redacted(tmp_path: Path) -> None:
    rec = _outbox_record(
        title="ok title",
        summary="please approve this",
    )
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    row = snap["rows"][0]
    assert row["summary"] == "[redacted-decision-verb]"


def test_clean_title_summary_passes_through(tmp_path: Path) -> None:
    rec = _outbox_record(
        title="Synthetic eligible candidate",
        summary="decision_state=eligible; risk=LOW",
    )
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    row = snap["rows"][0]
    assert row["title"] == "Synthetic eligible candidate"
    assert row["summary"].startswith("decision_state=eligible")


# ---------------------------------------------------------------------------
# Endpoint URL redaction
# ---------------------------------------------------------------------------


def test_no_full_endpoint_url_in_inbox_row(tmp_path: Path) -> None:
    rec = _outbox_record(
        endpoint_hash="deadbeefdeadbeef",
        title="Synthetic",
        summary="Synthetic summary",
    )
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    raw = json.dumps(snap, sort_keys=True)
    # The endpoint URL itself must not appear; only the hash.
    assert "fcm.googleapis.com" not in raw
    assert "deadbeefdeadbeef" in raw


# ---------------------------------------------------------------------------
# Inbox row id stability
# ---------------------------------------------------------------------------


def test_inbox_row_id_stable_for_same_event_id(tmp_path: Path) -> None:
    rec = _outbox_record(event_id="ev_abcdef")
    artifact = _write_outbox(tmp_path, [rec])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    assert snap["rows"][0]["inbox_row_id"] == "mai_ev_abcdef"


# ---------------------------------------------------------------------------
# Bounded inbox
# ---------------------------------------------------------------------------


def test_inbox_rows_bounded_to_max(tmp_path: Path) -> None:
    records = [
        _outbox_record(event_id=f"ev_{i:04d}")
        for i in range(100)
    ]
    artifact = _write_outbox(tmp_path, records)
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    assert len(snap["rows"]) <= mai.MAX_INBOX_ROWS


# ---------------------------------------------------------------------------
# Wrapper shape + counts
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    artifact = _write_outbox(tmp_path, [_outbox_record()])
    snap = mai.collect_snapshot(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "outbox_artifact_path",
        "outbox_artifact_available",
        "max_inbox_rows",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "notification_dispatch_outbox_module_version",
        "notification_event_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    artifact = _write_outbox(tmp_path, [_outbox_record()])
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    inv = snap["discipline_invariants"]
    assert inv["mints_approval_token"] is False
    assert inv["verifies_approval_token"] is False
    assert inv["executes_approve_or_reject"] is False
    assert inv["merges_or_deploys"] is False
    assert inv["sends_real_push"] is False
    assert inv["registers_flask_blueprint"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"
    assert inv["no_approval_from_notification_click_alone"] is True


def test_counts_aggregate_by_attention_level(tmp_path: Path) -> None:
    records = [
        _outbox_record(event_id="a", event_severity="push_info"),
        _outbox_record(event_id="b", event_severity="approval_required"),
        _outbox_record(event_id="c", event_severity="critical"),
        _outbox_record(
            event_id="d", outbound_delivery_intent="failed_secret_check"
        ),
    ]
    artifact = _write_outbox(tmp_path, records)
    snap = mai.collect_snapshot(outbox_artifact_path=artifact)
    counts = snap["counts"]
    assert counts["total"] == 4
    assert counts["informational"] == 1
    assert counts["needs_review"] == 1
    assert counts["critical_attention"] == 1
    assert counts["blocked_attention"] == 1


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    artifact = _write_outbox(tmp_path, [_outbox_record()])
    a = mai.collect_snapshot(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    b = mai.collect_snapshot(
        outbox_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_no_outbox_artifact_yields_warning(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    snap = mai.collect_snapshot(
        outbox_artifact_path=missing,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert "outbox_artifact_absent" in snap["validation_warnings"]
    assert snap["rows"] == []


def test_unparseable_outbox_yields_warning(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "notification_dispatch_outbox" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = mai.collect_snapshot(outbox_artifact_path=bad)
    assert "outbox_artifact_absent" in snap["validation_warnings"] or (
        "outbox_artifact_unparseable" in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(mai.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_or_network() -> None:
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


def test_no_web_push_library_imports() -> None:
    src = _module_source()
    for forbidden in (
        "pywebpush",
        "from webpush",
        "import webpush",
        "from web_push",
        "import web_push",
    ):
        assert forbidden not in src, forbidden


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
    importlib.reload(mai)
    assert callable(mai.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(mai)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_does_not_open_seed_jsonl_for_writing() -> None:
    src = _module_source()
    forbidden_code_patterns = (
        "seed.jsonl\", \"w",
        "seed.jsonl', 'w",
        "delegation_seed.jsonl\", \"w",
        "GENERATED_SEED_PATH",
        ".register_blueprint(",
        "add_url_rule(",
    )
    for s in forbidden_code_patterns:
        assert s not in src, s


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "mobile_approval_inbox.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
    )


def test_doc_states_n4_path_only_for_decision_state_flip() -> None:
    text = _doc_text().lower()
    assert "n4" in text
    assert "pending" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        raw = text[start:end].lower()
        cleaned = re.sub(r"\n\s*>\s*", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned)
        assert "permanently disabled" in cleaned
