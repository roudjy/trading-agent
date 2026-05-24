from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import operator_decision_surface as ods


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _queue_text() -> str:
    return """
### ADE-QRE-014H - Failure-to-Action Actionability Density

- queue id: `ADE-QRE-014H`
- status: `done`
- completion evidence: PR #335, merge SHA `1be8bbc`; Fast pre-merge gate completed/success; frozen contracts unchanged; protected/execution paths untouched.

### ADE-QRE-014I - Operator Decision Surface Readiness

- queue id: `ADE-QRE-014I`
- title: Operator Decision Surface Readiness.
- status: `ready`
- purpose: make operator-facing decision outputs clearer: why next, why
  blocked, why deferred, and why no synthesis.
- depends on: `ADE-QRE-014H done`.

### ADE-QRE-014J - Research Memory Retrieval Coverage

- queue id: `ADE-QRE-014J`
- title: Research Memory Retrieval Coverage.
- status: `blocked until ADE-QRE-014I done`
- depends on: `ADE-QRE-014I done`.

### ADE-QRE-014F - Addendum 4 Activation Review

- queue id: `ADE-QRE-014F`
- status: `deferred unless ADE-QRE-014E done and no operator gate exists`
- depends on: `ADE-QRE-014E done`.
"""


def test_decision_surface_explains_next_blocked_deferred_and_no_synthesis(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "docs" / "governance" / "queue.md"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(_queue_text(), encoding="utf-8")
    trusted_path = tmp_path / "logs" / "trusted_loop_materialization" / "latest.json"
    observability_path = (
        tmp_path / "logs" / "research_observability_minimal" / "latest.json"
    )
    _write_json(
        trusted_path,
        {
            "synthesis_blocker_explanation_density": {
                "overall_status": "blocked_explained",
                "active_blocker_count": 3,
                "explained_blocker_count": 3,
                "unexplained_block_reasons": [],
                "operator_summary": "3/3 active synthesis blockers explained.",
            }
        },
    )
    _write_json(
        observability_path,
        {
            "qre_operator_summary": {
                "operator_state": "operator_review_available",
                "unknown_failure_rate": 0.0,
                "actionable_failure_rate": None,
                "attribution_depth_score": 1.0,
                "missing_sources": [],
            }
        },
    )

    snap = ods.collect_snapshot(
        queue_doc_path=queue_path,
        trusted_loop_path=trusted_path,
        observability_path=observability_path,
        frozen_utc="2026-05-24T00:00:00Z",
    )

    surface = snap["decision_surface"]
    assert snap["final_recommendation"] == "operator_decision_surface_ready"
    assert surface["next"]["queue_item"] == "ADE-QRE-014I"
    assert surface["next"]["dependencies_done"] is True
    assert "earliest non-stale ready item" in surface["next"]["operator_explanation"]
    assert surface["blocked"]["items"][0]["queue_item"] == "ADE-QRE-014J"
    assert surface["blocked"]["items"][0]["blocked_by"] == "ADE-QRE-014I"
    assert surface["deferred"]["items"][0]["queue_item"] == "ADE-QRE-014F"
    assert "no operator gate exists" in surface["deferred"]["items"][0]["defer_condition"]
    assert surface["no_synthesis"]["status"] == "blocked"
    assert surface["no_synthesis"]["synthesis_enabled"] is False
    assert surface["no_synthesis"]["trusted_loop_blockers"]["active_blocker_count"] == 3
    assert snap["safety_invariants"]["strategy_synthesis_enabled"] is False
    assert snap["safety_invariants"]["adds_dashboard_mutation_routes"] is False


def test_missing_queue_fails_closed_without_selecting_next(tmp_path: Path) -> None:
    snap = ods.collect_snapshot(
        queue_doc_path=tmp_path / "missing.md",
        trusted_loop_path=tmp_path / "missing_trusted.json",
        observability_path=tmp_path / "missing_observability.json",
        frozen_utc="2026-05-24T00:00:00Z",
    )

    assert snap["final_recommendation"] == "fail_closed_no_next_item"
    assert snap["source_status"]["queue_doc"]["fails_closed"] is True
    assert snap["decision_surface"]["next"]["status"] == "fail_closed"
    assert snap["decision_surface"]["next"]["missing_evidence"] == [
        "eligible_ready_queue_item"
    ]
    assert snap["decision_surface"]["no_synthesis"]["missing_evidence"] == [
        "research_observability_minimal_latest",
        "trusted_loop_materialization_latest",
    ]
    assert snap["safe_to_execute"] is False


def test_stale_historical_ready_item_does_not_override_current_chain(
    tmp_path: Path,
) -> None:
    text = """
### ADE-QRE-011 - Old Ready Item

- queue id: `ADE-QRE-011`
- status: `ready`

### ADE-QRE-014H - Completed Item

- queue id: `ADE-QRE-014H`
- status: `done`

### ADE-QRE-014I - Current Ready Item

- queue id: `ADE-QRE-014I`
- status: `ready`
- depends on: `ADE-QRE-014H done`.
"""
    items = ods.parse_queue_items(text)
    queue_path = tmp_path / "queue.md"
    queue_path.write_text(text, encoding="utf-8")

    snap = ods.collect_snapshot(
        queue_doc_path=queue_path,
        frozen_utc="2026-05-24T00:00:00Z",
    )

    assert items["ADE-QRE-011"].status == "ready"
    assert snap["decision_surface"]["next"]["queue_item"] == "ADE-QRE-014I"

def test_missing_trusted_loop_keeps_no_synthesis_fail_closed(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.md"
    queue_path.write_text(_queue_text(), encoding="utf-8")

    snap = ods.collect_snapshot(
        queue_doc_path=queue_path,
        trusted_loop_path=tmp_path / "missing_trusted.json",
        observability_path=tmp_path / "missing_observability.json",
        frozen_utc="2026-05-24T00:00:00Z",
    )

    no_synthesis = snap["decision_surface"]["no_synthesis"]
    assert no_synthesis["status"] == "blocked"
    assert no_synthesis["trusted_loop_blockers"]["fail_closed"] is True
    assert "trusted_loop_materialization_latest" in no_synthesis["missing_evidence"]
    assert "missing or thin trusted-loop evidence fails closed" in (
        no_synthesis["operator_explanation"]
    )


def test_thin_trusted_loop_evidence_is_explicit_fail_closed(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.md"
    trusted_path = tmp_path / "trusted.json"
    queue_path.write_text(_queue_text(), encoding="utf-8")
    _write_json(trusted_path, {"report_kind": "trusted_loop_materialization_digest"})

    snap = ods.collect_snapshot(
        queue_doc_path=queue_path,
        trusted_loop_path=trusted_path,
        observability_path=tmp_path / "missing_observability.json",
        frozen_utc="2026-05-24T00:00:00Z",
    )

    blockers = snap["decision_surface"]["no_synthesis"]["trusted_loop_blockers"]
    assert blockers["fail_closed"] is True
    assert blockers["missing_evidence"] == ["synthesis_blocker_explanation_density"]
    assert "present but does not contain" in blockers["operator_summary"]


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "operator_decision_surface"
    snap = ods.collect_snapshot(
        queue_doc_path=tmp_path / "missing.md",
        frozen_utc="2026-05-24T00:00:00Z",
    )

    out = ods.write_outputs(snap, artifact_dir=base)

    assert (base / "latest.json").is_file()
    assert "operator_decision_surface" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        ods._validate_write_target(tmp_path / "outside" / "latest.json")


def test_cli_status_returns_not_available(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ods,
        "ARTIFACT_DIR",
        tmp_path / "logs" / "operator_decision_surface",
    )
    rc = ods.main(["--status"])
    parsed = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert parsed["final_recommendation"] == "not_available"


def test_source_has_no_mutation_route_or_approval_surface() -> None:
    src = Path(ods.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "dashboard.dashboard",
        "@app.post",
        "@router.post",
        ".post(",
        "approval_token",
        "approval_inbox",
        "campaign_queue.append",
        "registry.py",
        "agent/backtesting/strategies.py",
    )
    for needle in forbidden:
        assert needle not in src


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(ods.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "agent.execution",
        "agent.risk",
        "automation.live",
        "automation.broker",
        "broker.",
        "execution.live",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert needle not in src
