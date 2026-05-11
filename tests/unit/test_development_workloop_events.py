"""Unit tests for A24 — Autonomous Development Workloop event-taxonomy projector."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_workloop_events as a24
from reporting import notification_event as ne


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_workloop_digest(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _digest(
    *,
    pr_queue: list[dict[str, Any]] | None = None,
    dependabot_queue: list[dict[str, Any]] | None = None,
    roadmap_queue: list[dict[str, Any]] | None = None,
    blocked_items: list[dict[str, Any]] | None = None,
    audit_chain_status: dict[str, Any] | None = None,
    governance_status: dict[str, Any] | None = None,
    actions_taken: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "controller_version": "v3.15.15.16",
        "cycle_id": 0,
        "mode": "dry-run",
        "pr_queue": pr_queue or [],
        "dependabot_queue": dependabot_queue or [],
        "roadmap_queue": roadmap_queue or [],
        "blocked_items": blocked_items or [],
        "audit_chain_status": audit_chain_status,
        "governance_status": governance_status,
        "actions_taken": actions_taken or [],
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_workloop_signal_sources_pinned_exactly() -> None:
    assert a24.WORKLOOP_SIGNAL_SOURCES == (
        "pr_queue",
        "dependabot_queue",
        "roadmap_queue",
        "blocked_items",
        "audit_chain_status",
        "governance_status",
        "actions_taken",
    )


def test_validation_warnings_pinned() -> None:
    assert a24.VALIDATION_WARNINGS == (
        "workloop_digest_absent",
        "workloop_digest_unparseable",
        "workloop_signal_invalid",
    )


def test_event_row_keys_pinned_exactly_and_ordered() -> None:
    assert a24.EVENT_ROW_KEYS == (
        "workloop_event_id",
        "source_signal",
        "source_index",
        "event_kind",
        "event_severity",
        "decision_or_outcome",
        "title",
        "summary",
        "extracted_at",
    )


def test_max_event_rows_pinned() -> None:
    assert a24.MAX_EVENT_ROWS == 128


def test_step5_invariants_pinned() -> None:
    assert a24.step5_implementation_allowed is False
    assert a24.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_workloop_events_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        a24._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_upstream_workloop_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    with pytest.raises(ValueError):
        a24._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Signal → N1 mapping
# ---------------------------------------------------------------------------


def test_pr_queue_maps_to_pr_lifecycle_event(tmp_path: Path) -> None:
    digest = _digest(
        pr_queue=[
            {
                "item_id": "pr1",
                "title": "PR #1",
                "decision": "operator_click",
                "risk_class": "low",
            }
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "pr_queue"]
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "pr_lifecycle_event"
    # Severity is routed verbatim through N1; pr_lifecycle_event → push_info.
    assert rows[0]["event_severity"] == ne.route_for("pr_lifecycle_event")


def test_dependabot_queue_maps_to_pr_lifecycle_event(tmp_path: Path) -> None:
    digest = _digest(
        dependabot_queue=[
            {
                "item_id": "dep1",
                "branch_or_pr": "dependabot/x",
                "decision": "operator_click",
                "risk_class": "dependabot_minor_safe_candidate",
            }
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "dependabot_queue"]
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "pr_lifecycle_event"


def test_roadmap_queue_normal_maps_to_queue_item_proposed(tmp_path: Path) -> None:
    digest = _digest(
        roadmap_queue=[
            {"item_id": "rm1", "title": "Roadmap item", "risk_class": "low"}
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "roadmap_queue"]
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "queue_item_proposed"


def test_roadmap_queue_blocked_maps_to_queue_item_blocked(tmp_path: Path) -> None:
    digest = _digest(
        roadmap_queue=[
            {"item_id": "rm2", "title": "Blocked", "risk_class": "blocked_path"}
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "roadmap_queue"]
    assert rows[0]["event_kind"] == "queue_item_blocked"


def test_blocked_items_maps_to_queue_item_blocked(tmp_path: Path) -> None:
    digest = _digest(
        blocked_items=[
            {"item_id": "b1", "title": "Blocked", "reason": "missing_label"}
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "blocked_items"]
    assert rows[0]["event_kind"] == "queue_item_blocked"


def test_audit_chain_status_maps_to_audit_chain_anomaly(tmp_path: Path) -> None:
    """audit_chain_anomaly routes to severity=critical regardless of
    status value — this is intentional (every audit-chain signal
    surfaces to the operator)."""
    digest = _digest(
        audit_chain_status={"status": "intact", "ledger_path": "logs/x.jsonl"}
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "audit_chain_status"]
    assert rows[0]["event_kind"] == "audit_chain_anomaly"
    assert rows[0]["event_severity"] == "critical"


def test_governance_ok_maps_to_operational_digest_emitted(tmp_path: Path) -> None:
    digest = _digest(governance_status={"status": "ok"})
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "governance_status"]
    assert rows[0]["event_kind"] == "operational_digest_emitted"


def test_governance_anomaly_maps_to_violation_detected(tmp_path: Path) -> None:
    digest = _digest(governance_status={"status": "drift"})
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "governance_status"]
    assert rows[0]["event_kind"] == "governance_violation_detected"
    # governance_violation_detected → critical per N1 routing.
    assert rows[0]["event_severity"] == "critical"


def test_actions_taken_maps_to_operational_digest_emitted(tmp_path: Path) -> None:
    digest = _digest(
        actions_taken=[{"kind": "write_digest", "outcome": "ok", "target": "x"}]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    rows = [r for r in snap["rows"] if r["source_signal"] == "actions_taken"]
    assert rows[0]["event_kind"] == "operational_digest_emitted"


# ---------------------------------------------------------------------------
# Severity routed through N1
# ---------------------------------------------------------------------------


def test_every_emitted_event_severity_comes_from_n1_route_for(
    tmp_path: Path,
) -> None:
    """A24 must not introduce custom severity logic. For every row,
    `event_severity == route_for(event_kind)` (with defaults — no
    risk_class / authority-decision hints in A24)."""
    digest = _digest(
        pr_queue=[{"item_id": "p1", "title": "x", "decision": "blocked"}],
        roadmap_queue=[{"item_id": "r1", "title": "x", "risk_class": "low"}],
        blocked_items=[{"item_id": "b1", "title": "x", "reason": "y"}],
        audit_chain_status={"status": "intact"},
        governance_status={"status": "ok"},
        actions_taken=[{"kind": "k", "outcome": "ok"}],
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    for row in snap["rows"]:
        assert row["event_severity"] == ne.route_for(row["event_kind"]), row


# ---------------------------------------------------------------------------
# Bounded artefact + identity
# ---------------------------------------------------------------------------


def test_rows_bounded_to_max(tmp_path: Path) -> None:
    digest = _digest(
        pr_queue=[
            {"item_id": f"pr{i:04d}", "title": f"PR {i}", "decision": "operator_click"}
            for i in range(200)
        ]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    assert len(snap["rows"]) <= a24.MAX_EVENT_ROWS


def test_workloop_event_id_is_stable_for_same_signal_and_index(tmp_path: Path) -> None:
    digest = _digest(
        pr_queue=[{"item_id": "p1", "title": "x", "decision": "operator_click"}]
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap1 = a24.collect_snapshot(workloop_digest_path=artifact)
    snap2 = a24.collect_snapshot(workloop_digest_path=artifact)
    assert snap1["rows"][0]["workloop_event_id"] == snap2["rows"][0]["workloop_event_id"]


# ---------------------------------------------------------------------------
# Wrapper shape + counts
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    artifact = _write_workloop_digest(tmp_path, _digest())
    snap = a24.collect_snapshot(
        workloop_digest_path=artifact,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "workloop_digest_path",
        "workloop_digest_available",
        "upstream_controller_version",
        "upstream_mode",
        "upstream_cycle_id",
        "max_event_rows",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "autonomous_workloop_module_version",
        "notification_event_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    artifact = _write_workloop_digest(tmp_path, _digest())
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    inv = snap["discipline_invariants"]
    assert inv["calls_workloop_functions"] is False
    assert inv["calls_gh_cli"] is False
    assert inv["calls_git_cli"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["emits_real_notification"] is False
    assert inv["mints_approval_token"] is False
    assert inv["merges_or_deploys"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


def test_counts_aggregate_by_signal_kind_severity(tmp_path: Path) -> None:
    digest = _digest(
        pr_queue=[
            {"item_id": "p1", "title": "x", "decision": "operator_click"},
            {"item_id": "p2", "title": "y", "decision": "blocked"},
        ],
        roadmap_queue=[
            {"item_id": "r1", "title": "x", "risk_class": "low"},
        ],
        audit_chain_status={"status": "intact"},
    )
    artifact = _write_workloop_digest(tmp_path, digest)
    snap = a24.collect_snapshot(workloop_digest_path=artifact)
    counts = snap["counts"]
    assert counts["total"] == 4
    assert counts["by_source_signal"]["pr_queue"] == 2
    assert counts["by_source_signal"]["roadmap_queue"] == 1
    assert counts["by_source_signal"]["audit_chain_status"] == 1
    assert counts["by_event_kind"]["pr_lifecycle_event"] == 2
    assert counts["by_event_kind"]["queue_item_proposed"] == 1
    assert counts["by_event_kind"]["audit_chain_anomaly"] == 1


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    digest = _digest(pr_queue=[{"item_id": "p1", "title": "x"}])
    artifact = _write_workloop_digest(tmp_path, digest)
    a = a24.collect_snapshot(
        workloop_digest_path=artifact, generated_at_utc="2026-05-11T00:00:00Z"
    )
    b = a24.collect_snapshot(
        workloop_digest_path=artifact, generated_at_utc="2026-05-11T00:00:00Z"
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# Absent / unparseable digest
# ---------------------------------------------------------------------------


def test_absent_digest_yields_warning(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    snap = a24.collect_snapshot(
        workloop_digest_path=missing,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    assert "workloop_digest_absent" in snap["validation_warnings"]
    assert snap["workloop_digest_available"] is False
    assert snap["rows"] == []


def test_unparseable_digest_yields_warning(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = a24.collect_snapshot(workloop_digest_path=bad)
    assert (
        "workloop_digest_absent" in snap["validation_warnings"]
        or "workloop_digest_unparseable" in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a24.__file__).read_text(encoding="utf-8")


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


def test_module_does_not_invoke_workloop_functions() -> None:
    """The most load-bearing pin: A24 imports
    `reporting.autonomous_workloop` only for its MODULE_VERSION
    constant. It must NEVER call any function from that module."""
    import ast

    src = _module_source()
    tree = ast.parse(src)
    # Find every Call whose function resolves to an attribute or name
    # under the workloop alias `_aw`.
    forbidden_callables = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # `_aw.foo(...)` pattern.
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "_aw":
                    forbidden_callables.add(func.attr)
    assert forbidden_callables == set(), (
        f"A24 must not call any function from autonomous_workloop; "
        f"found calls to: {forbidden_callables}"
    )


def test_module_does_not_open_seed_jsonl_for_writing() -> None:
    src = _module_source()
    forbidden = (
        "seed.jsonl\", \"w",
        "seed.jsonl', 'w",
        "delegation_seed.jsonl\", \"w",
        "GENERATED_SEED_PATH",
        ".register_blueprint(",
        "add_url_rule(",
    )
    for s in forbidden:
        assert s not in src, s


def test_module_imports_cleanly() -> None:
    importlib.reload(a24)
    assert callable(a24.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(a24)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "development_workloop_events.md"
    ).read_text(encoding="utf-8")


def test_doc_states_a24_never_calls_workloop() -> None:
    text = _doc_text().lower()
    assert "never invokes any workloop function" in text or "never invoke any workloop function" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
    )


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
