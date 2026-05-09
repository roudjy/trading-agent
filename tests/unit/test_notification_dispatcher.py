"""Unit tests for N2a — Artifact-only Notification Dispatcher.

Synthetic deterministic fixtures only. The dispatcher is read-only:
it reads existing ADE artefacts and produces notification-ready
records. **It sends no real push, opens no socket, and mints no
token.**

Pinned here:

* Closed vocabularies (DELIVERY_INTENTS, SOURCE_MODULES,
  EVENT_SCHEMA_KEYS) are byte-exact.
* The current real A16a candidate becomes a `ready`
  `intake_candidate_eligible` / `push_info` event.
* A Step 5.0 `plan_emitted` cycle becomes a `suppressed`
  `step5_cycle_planned` / `silent` event.
* Duplicate event_id within the 24h sliding window dedupes.
* Cooldown suppression fires per the pinned table.
* Rate-limit fires after MAX_DISPATCH_PER_CYCLE.
* events.jsonl is bounded ≤ 500.
* No subprocess / socket / urllib / requests / httpx / aiohttp / gh /
  git in the module.
* No imports of dashboard / frontend / automation / broker /
  agent.risk / agent.execution / research /
  reporting.intelligent_routing / live / paper / shadow / trading.
* Importing the module does not flip Step 5 invariants.
* Atomic write refuses any path outside logs/notification_dispatcher/.
* Doc states no real push in N2a, no click-approval, and Level 6
  permanently disabled.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_intake_promotion as dip
from reporting import development_step5_loop as dsl
from reporting import execution_authority as ea
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_logs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    intake = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    step5 = tmp_path / "logs" / "step5_loop" / "latest.json"
    roadmap = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    history = tmp_path / "logs" / "notification_dispatcher" / "events.jsonl"
    for p in (intake, step5, roadmap, history):
        p.parent.mkdir(parents=True, exist_ok=True)
    return (intake, step5, roadmap, history)


def _eligible_promotion_payload(
    *, candidate_id: str = "qre_v3_15_16_addendum_source_manifest_001"
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": dip.MODULE_VERSION,
        "report_kind": "development_intake_promotion",
        "generated_at_utc": "2026-05-09T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "rows": [
            {
                "candidate_id": candidate_id,
                "title": "Draft diagnostic-source manifest",
                "source_document": "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
                "source_kind": "operating_manual",
                "roadmap_phase": "v3.15.16",
                "candidate_kind": "docs",
                "required_agent_role": "planner",
                "risk_level": "LOW",
                "target_path": "docs/governance/agent_run_summaries/qre_addendum_source_manifest_001.md",
                "upstream_intake_status": "eligible",
                "upstream_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
                "reclassified_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
                "reclassified_execution_authority_reason": "low_risk_docs_non_policy",
                "classification_drift": False,
                "human_needed": False,
                "human_needed_reason": "none",
                "acceptance_criteria": ["criterion 1", "criterion 2"],
                "evidence_hash": "abc123",
                "notification_event_kind": "intake_candidate_eligible",
                "notification_event_severity": "push_info",
                "already_in_seed_jsonl": False,
                "already_in_delegation_seed": False,
                "duplicate_of_history_entry": False,
                "decision_state": "eligible",
                "promotion_target": "none",
                "notes": "",
            }
        ],
        "counts": {"total": 1, "eligible": 1},
        "validation_warnings": [],
        "discipline_invariants": {},
    }


def _step5_loop_payload(
    *, outcome: str = "plan_emitted", cycle_id: str = "test_cycle_001"
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": dsl.MODULE_VERSION,
        "report_kind": "step5_loop",
        "generated_at_utc": "2026-05-09T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "current_plan": {
            "cycle_id": cycle_id,
            "source_kind": "queue",
            "source_id": "dwq_test123",
            "outcome": outcome,
            "halt_reason": "ok" if outcome == "plan_emitted" else "needs_human",
            "execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_delivery_intents_pinned_exactly() -> None:
    assert nd.DELIVERY_INTENTS == (
        "ready",
        "suppressed",
        "suppressed_cooldown",
        "duplicate_within_window",
        "rate_limited",
    )


def test_source_modules_pinned_exactly() -> None:
    assert nd.SOURCE_MODULES == (
        "development_intake_promotion",
        "development_step5_loop",
        "development_roadmap_intake",
    )


def test_event_schema_keys_pinned_exactly_and_ordered() -> None:
    assert nd.EVENT_SCHEMA_KEYS == (
        "event_id",
        "event_kind",
        "event_severity",
        "delivery_intent",
        "source_module",
        "source_artifact_path",
        "source_id",
        "title",
        "summary",
        "risk_class",
        "execution_authority_decision",
        "acceptance_criteria",
        "target_path",
        "evidence_hash",
        "created_at",
        "notes",
    )


def test_max_dispatch_per_cycle_pinned() -> None:
    assert nd.MAX_DISPATCH_PER_CYCLE == 16


def test_max_events_history_pinned() -> None:
    assert nd.MAX_EVENTS_HISTORY == 500


def test_dedupe_window_seconds_pinned() -> None:
    assert nd.DEDUPE_WINDOW_SECONDS == 24 * 60 * 60


def test_cooldown_table_covers_all_event_kinds() -> None:
    """Every member of N1 EVENT_KINDS must have a cooldown."""
    missing = set(ne.EVENT_KINDS) - set(
        nd.COOLDOWN_SECONDS_PER_EVENT_KIND.keys()
    )
    assert missing == set(), f"event_kinds missing cooldown: {missing}"


def test_cooldown_critical_kinds_have_zero_cooldown() -> None:
    for k in (
        "governance_violation_detected",
        "secret_or_pii_redaction_event",
        "audit_chain_anomaly",
        "step5_cycle_halted",
        "step5_cycle_needs_human",
        "release_gate_fail",
        "release_gate_needs_human",
        "pr_merge_approval_required",
        "deploy_approval_required",
    ):
        assert nd.COOLDOWN_SECONDS_PER_EVENT_KIND[k] == 0


def test_artifact_paths_under_logs_only() -> None:
    assert nd.ARTIFACT_RELATIVE_PATH.startswith(
        "logs/notification_dispatcher/"
    )
    assert nd.EVENTS_JSONL_RELATIVE_PATH.startswith(
        "logs/notification_dispatcher/"
    )
    assert "research/" not in nd.ARTIFACT_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_dispatcher_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        nd._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    with pytest.raises(ValueError):
        nd._atomic_write_json(bad, {"x": 1})


def test_history_append_refuses_non_dispatcher_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "events.jsonl"
    with pytest.raises(ValueError):
        nd._append_events_history(bad, [])


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_step5_invariants_pinned() -> None:
    assert nd.step5_implementation_allowed is False
    assert nd.STEP5_ENABLED_SUBSTAGE == "none"


def test_snapshot_carries_step5_invariants(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,  # missing file → no rows
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert snap["step5_enabled_substage"] == "none"
    assert snap["step5_implementation_allowed"] is False


def test_discipline_invariants_present(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
    )
    inv = snap["discipline_invariants"]
    assert inv["sends_real_push"] is False
    assert inv["opens_mobile_inbox"] is False
    assert inv["mints_approval_token"] is False
    assert inv["invokes_network"] is False
    assert inv["invokes_subprocess"] is False
    assert inv["mutates_upstream_artifacts"] is False
    assert inv["reads_subscription_files"] is False
    assert inv["reads_vapid_keys"] is False
    assert inv["writes_dashboard_or_frontend"] is False
    assert inv["secret_redactor_invoked"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "sources_read",
        "events_history_path",
        "note",
        "validation_warnings",
        "vocabularies",
        "cooldown_seconds_per_event_kind",
        "counts",
        "events",
        "execution_authority_module_version",
        "notification_event_module_version",
        "intake_promotion_module_version",
        "step5_module_version",
        "roadmap_intake_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "notification_dispatcher"


# ---------------------------------------------------------------------------
# Real-shape happy path: A16a eligible → ready intake_candidate_eligible
# ---------------------------------------------------------------------------


def test_real_a16a_eligible_becomes_ready_event(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(intake, _eligible_promotion_payload())
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    eligibles = [e for e in snap["events"] if e["source_module"] == "development_intake_promotion"]
    assert len(eligibles) == 1
    ev = eligibles[0]
    assert set(ev.keys()) == set(nd.EVENT_SCHEMA_KEYS)
    assert ev["event_kind"] == "intake_candidate_eligible"
    assert ev["event_severity"] == "push_info"
    assert ev["delivery_intent"] == "ready"
    assert ev["source_id"] == "qre_v3_15_16_addendum_source_manifest_001"
    assert ev["execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED
    # No diff, no PR body, no command summary in fields.
    forbidden_in_summary = ("diff --git", "@@", "PATCH", "git commit")
    for field in ("title", "summary", "notes"):
        for s in forbidden_in_summary:
            assert s not in ev[field]


def test_step5_plan_emitted_becomes_suppressed_silent_event(
    tmp_path: Path,
) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(step5, _step5_loop_payload(outcome="plan_emitted"))
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    step5_events = [e for e in snap["events"] if e["source_module"] == "development_step5_loop"]
    assert len(step5_events) == 1
    ev = step5_events[0]
    assert ev["event_kind"] == "step5_cycle_planned"
    assert ev["event_severity"] == "silent"
    assert ev["delivery_intent"] == "suppressed"


def test_step5_halt_needs_human_becomes_ready_event(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(step5, _step5_loop_payload(outcome="halt_needs_human"))
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    step5_events = [e for e in snap["events"] if e["source_module"] == "development_step5_loop"]
    assert len(step5_events) == 1
    ev = step5_events[0]
    assert ev["event_kind"] == "step5_cycle_needs_human"
    # severity is push_action_required; HIGH risk hint or NEEDS_HUMAN
    # decision could escalate further, but the routing-table default
    # for this kind is push_action_required.
    assert ev["event_severity"] in ("push_action_required", "approval_required", "critical")
    assert ev["delivery_intent"] == "ready"


def test_step5_halt_permanently_denied_becomes_halted_event(
    tmp_path: Path,
) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(step5, _step5_loop_payload(outcome="halt_permanently_denied"))
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    step5_events = [e for e in snap["events"] if e["source_module"] == "development_step5_loop"]
    assert len(step5_events) == 1
    assert step5_events[0]["event_kind"] == "step5_cycle_halted"


def test_step5_no_op_emits_no_event(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(step5, _step5_loop_payload(outcome="no_op_no_eligible_item"))
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
    )
    step5_events = [e for e in snap["events"] if e["source_module"] == "development_step5_loop"]
    assert len(step5_events) == 0


# ---------------------------------------------------------------------------
# Delivery-intent gates
# ---------------------------------------------------------------------------


def test_silent_severity_becomes_suppressed(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(step5, _step5_loop_payload(outcome="plan_emitted"))
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
    )
    for ev in snap["events"]:
        if ev["event_severity"] == "silent":
            assert ev["delivery_intent"] == "suppressed"


def test_duplicate_event_id_within_window_deduped(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(intake, _eligible_promotion_payload())
    snap1 = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    eid = snap1["events"][0]["event_id"]
    # Pre-seed the history with the same event_id at an earlier time.
    history.write_text(
        json.dumps(
            {
                "event_id": eid,
                "event_kind": "intake_candidate_eligible",
                "event_severity": "push_info",
                "delivery_intent": "ready",
                "source_module": "development_intake_promotion",
                "source_id": "qre_v3_15_16_addendum_source_manifest_001",
                "created_at": "2026-05-09T00:00:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    snap2 = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:01:00Z",
    )
    target = [e for e in snap2["events"] if e["event_id"] == eid]
    assert len(target) == 1
    assert target[0]["delivery_intent"] == "duplicate_within_window"


def test_cooldown_per_event_kind_suppresses_recent_kind(
    tmp_path: Path,
) -> None:
    """A different event_id but same event_kind seen ≤ cooldown ago
    should be `suppressed_cooldown`."""
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(intake, _eligible_promotion_payload())
    # Pre-seed history with a different event_id of the same kind, 1 minute ago.
    history.write_text(
        json.dumps(
            {
                "event_id": "different_id",
                "event_kind": "intake_candidate_eligible",
                "event_severity": "push_info",
                "delivery_intent": "ready",
                "source_module": "development_intake_promotion",
                "source_id": "different_source",
                "created_at": "2026-05-09T00:00:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:01:00Z",  # 1 minute later, < 600 cooldown
    )
    eligibles = [e for e in snap["events"] if e["source_module"] == "development_intake_promotion"]
    assert len(eligibles) == 1
    assert eligibles[0]["delivery_intent"] == "suppressed_cooldown"


def test_max_dispatch_per_cycle_rate_limits_excess(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    rows = []
    for i in range(20):
        rows.append(
            {
                "candidate_id": f"cand_{i:03d}",
                "title": f"Candidate {i}",
                "source_document": "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
                "source_kind": "operating_manual",
                "roadmap_phase": "v3.15.16",
                "candidate_kind": "docs",
                "required_agent_role": "planner",
                "risk_level": "LOW",
                "target_path": f"docs/governance/agent_run_summaries/syn_{i:03d}.md",
                "upstream_intake_status": "eligible",
                "upstream_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
                "reclassified_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
                "reclassified_execution_authority_reason": "low_risk_docs_non_policy",
                "classification_drift": False,
                "human_needed": False,
                "human_needed_reason": "none",
                "acceptance_criteria": ["a"],
                "evidence_hash": f"hash_{i}",
                "notification_event_kind": "intake_candidate_eligible",
                "notification_event_severity": "push_info",
                "already_in_seed_jsonl": False,
                "already_in_delegation_seed": False,
                "duplicate_of_history_entry": False,
                "decision_state": "eligible",
                "promotion_target": "none",
                "notes": "",
            }
        )
    payload = _eligible_promotion_payload()
    payload["rows"] = rows
    _write_json(intake, payload)
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    intents = [e["delivery_intent"] for e in snap["events"]]
    ready_count = sum(1 for i in intents if i == "ready")
    rate_limited_count = sum(1 for i in intents if i == "rate_limited")
    assert ready_count == nd.MAX_DISPATCH_PER_CYCLE
    assert rate_limited_count == 20 - nd.MAX_DISPATCH_PER_CYCLE


# ---------------------------------------------------------------------------
# events.jsonl bounded
# ---------------------------------------------------------------------------


def test_events_jsonl_bounded_to_max(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    # Pre-populate with 600 rows of placeholder history.
    lines = []
    for i in range(600):
        lines.append(
            json.dumps(
                {
                    "event_id": f"eid_{i:04d}",
                    "event_kind": "intake_candidate_proposed",
                    "event_severity": "digest",
                    "delivery_intent": "suppressed",
                    "source_module": "development_roadmap_intake",
                    "source_id": f"src_{i:04d}",
                    "created_at": "2026-04-30T00:00:00Z",
                },
                sort_keys=True,
            )
        )
    history.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Now run write_outputs which trims the history.
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    # Build a minimal write target.
    out_dir = tmp_path / "logs" / "notification_dispatcher"
    latest = out_dir / "latest.json"
    nd._atomic_write_json(latest, snap)
    nd._append_events_history(history, snap.get("events") or [])
    bounded = [
        line for line in history.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(bounded) <= nd.MAX_EVENTS_HISTORY


# ---------------------------------------------------------------------------
# Determinism + sorting
# ---------------------------------------------------------------------------


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(intake, _eligible_promotion_payload())
    _write_json(step5, _step5_loop_payload())
    snap_a = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    snap_b = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    assert (
        json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
        == json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    )


def test_events_sort_stably(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    _write_json(intake, _eligible_promotion_payload())
    _write_json(step5, _step5_loop_payload())
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
        generated_at_utc="2026-05-09T00:00:00Z",
    )
    keys = [
        (e["source_module"], e["event_kind"], e["event_id"])
        for e in snap["events"]
    ]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# No-secret guard / no-noise payload
# ---------------------------------------------------------------------------


def test_event_records_carry_no_diff_or_pr_body(tmp_path: Path) -> None:
    intake, step5, roadmap, history = _make_logs(tmp_path)
    payload = _eligible_promotion_payload()
    # Even if upstream payload contains diff-like junk in title, the
    # dispatcher must not propagate it as a body field.
    payload["rows"][0]["title"] = "diff --git fake patch text"
    _write_json(intake, payload)
    snap = nd.collect_snapshot(
        intake_promotion_path=intake,
        step5_loop_path=step5,
        roadmap_intake_path=roadmap,
        events_history_path=history,
    )
    ev = snap["events"][0]
    # title is bounded and may pass through verbatim, but no PR body /
    # diff block is present in the *summary* / *notes* / scalar fields.
    for forbidden in ("@@ -", "+++ b/", "--- a/"):
        for field in ("summary", "notes"):
            assert forbidden not in ev[field]


def test_assert_no_secrets_called_on_snapshot(tmp_path: Path) -> None:
    """Defense-in-depth: a credential-shaped string anywhere in the
    snapshot must raise AssertionError via assert_no_secrets."""
    intake, step5, roadmap, history = _make_logs(tmp_path)
    payload = _eligible_promotion_payload()
    # Inject a credential pattern into title.
    payload["rows"][0]["title"] = "leaked sk-ant-api03-very-bad-secret-here-please-break"
    _write_json(intake, payload)
    with pytest.raises(AssertionError):
        nd.collect_snapshot(
            intake_promotion_path=intake,
            step5_loop_path=step5,
            roadmap_intake_path=roadmap,
            events_history_path=history,
        )


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(nd.__file__).read_text(encoding="utf-8")


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
        assert forbidden not in src


def test_no_web_push_library_imports() -> None:
    src = _module_source()
    for forbidden in (
        "pywebpush",
        "web_push",
        "webpush",
        "from pywebpush",
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


def test_no_subscription_file_reads_or_writes() -> None:
    """Defense in depth: module must not contain code paths that
    open a subscription file or VAPID key. Documentation references
    in docstrings are explicitly allowed (we document what we DO NOT
    do). This test scans for code-shaped patterns only."""
    src = _module_source()
    forbidden_code_patterns = (
        "subscriptions.json",
        "web_push_subscriptions",
        "vapid_public.txt",
        "vapid_private",
        "VAPID_PRIVATE",
        "WEB_PUSH_VAPID",
        "open_push_subscription",
        ".send_web_push",
        "WebPushClient",
    )
    for forbidden in forbidden_code_patterns:
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(nd)
    assert callable(nd.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    importlib.reload(nd)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "notification_dispatcher.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_real_push_in_n2a() -> None:
    text = _doc_text().lower()
    assert "no real push" in text or "no real push in n2a" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    text = _doc_text().lower()
    assert "no approval can happen from a notification click alone" in text or "no approval from notification click alone" in text


def test_doc_states_n2b_n3_n4_n5_remain_unimplemented() -> None:
    text = _doc_text().lower()
    for marker in ("n2b", "n3", "n4", "n5"):
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
