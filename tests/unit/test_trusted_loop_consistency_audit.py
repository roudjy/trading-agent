from __future__ import annotations

import copy
import json
from pathlib import Path

from reporting import trusted_loop_consistency_audit as audit
from reporting import trusted_loop_missing_evidence_fail_closed as fail_closed

FROZEN = "2026-05-28T00:00:00Z"


def _surface(
    surface_id: str,
    *,
    ready: bool,
    missing_evidence: list[str] | None = None,
) -> dict:
    return {
        "surface_id": surface_id,
        "status": "ready" if ready else "fail_closed",
        "ready": ready,
        "fail_closed": not ready,
        "missing_evidence": [] if missing_evidence is None else missing_evidence,
        "evidence": {},
        "trust_claim_blocked": ""
        if ready
        else f"{surface_id} remains blocked by missing evidence.",
        "notes": [],
    }


def _base_fail_closed_snapshot() -> dict:
    rows = [
        _surface("reason_records", ready=False, missing_evidence=["record_count"]),
        _surface("research_quality_kpis", ready=False, missing_evidence=["TTFPRC"]),
        _surface(
            "routing_readiness",
            ready=False,
            missing_evidence=["latest_artifact_present"],
        ),
        _surface(
            "sampling_readiness",
            ready=False,
            missing_evidence=["latest_artifact_present"],
        ),
        _surface(
            "diagnostics_loop",
            ready=False,
            missing_evidence=["diagnostics_loop_ready"],
        ),
        _surface(
            "retrieval_coverage",
            ready=False,
            missing_evidence=["retrieval_coverage_ready"],
        ),
        _surface(
            "queue_status",
            ready=False,
            missing_evidence=["complete_done_evidence_for_all_done_items"],
        ),
    ]
    rows[4]["trust_claim_blocked"] = (
        "Diagnostics are evidence surfaces only; missing diagnostics cannot "
        "authorize readiness."
    )
    rows[5]["trust_claim_blocked"] = (
        "Retrieval remains context, not authority; missing retrieval coverage "
        "cannot be treated as readiness."
    )
    rows[6]["status"] = "bounded_selection_ready_with_warnings"
    rows[6]["evidence"] = {
        "bounded_current_selection_ready": True,
        "missing_done_evidence_items": ["ADE-QRE-007"],
        "next_eligible_ready_item": "ADE-QRE-016D",
    }
    return {
        "report_kind": fail_closed.REPORT_KIND,
        "summary": {
            "required_surfaces": list(audit.REQUIRED_SURFACES),
            "required_surface_count": len(rows),
            "ready_surface_count": 0,
            "fail_closed_surface_count": len(rows),
            "trusted_loop_ready": False,
        },
        "surfaces": rows,
        "final_recommendation": "not_ready_missing_evidence",
        "safety_invariants": {
            "read_only": True,
            "strategy_synthesis_enabled": False,
            "addendum_runtime_activated": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
        },
    }


def test_blocked_surfaces_are_consistent_when_blockers_have_evidence() -> None:
    snapshot = audit.collect_snapshot(
        frozen_utc=FROZEN,
        fail_closed_snapshot=_base_fail_closed_snapshot(),
    )

    assert snapshot["final_recommendation"] == "consistent_blocked_by_evidence"
    assert snapshot["summary"]["inconsistent_check_count"] == 0
    assert snapshot["summary"]["blocked_with_evidence_count"] == 7
    rows = {row["check_id"]: row for row in snapshot["checks"]}
    assert rows["summary_matches_surface_counts"]["status"] == "passed"
    assert rows["queue_selection_does_not_upgrade_broader_trust"]["status"] == (
        "passed"
    )
    assert rows["diagnostics_loop_remains_non_authority"]["status"] == "passed"
    assert rows["retrieval_coverage_remains_non_authority"]["status"] == "passed"


def test_ready_surface_with_missing_evidence_is_inconsistent() -> None:
    source = copy.deepcopy(_base_fail_closed_snapshot())
    source["surfaces"][0]["ready"] = True
    source["surfaces"][0]["fail_closed"] = False
    source["surfaces"][0]["status"] = "ready"

    snapshot = audit.collect_snapshot(
        frozen_utc=FROZEN,
        fail_closed_snapshot=source,
    )
    inconsistent = [
        row for row in snapshot["checks"] if row["status"] == "inconsistent"
    ]

    assert snapshot["final_recommendation"] == "inconsistent_requires_operator_review"
    assert any(
        row["surface_id"] == "reason_records"
        and row["mismatch"] == "ready_surface_has_missing_evidence"
        for row in inconsistent
    )


def test_queue_bounded_selection_cannot_upgrade_missing_done_evidence() -> None:
    source = copy.deepcopy(_base_fail_closed_snapshot())
    queue = source["surfaces"][-1]
    queue["ready"] = True
    queue["fail_closed"] = False
    queue["status"] = "ready"
    queue["missing_evidence"] = []

    snapshot = audit.collect_snapshot(
        frozen_utc=FROZEN,
        fail_closed_snapshot=source,
    )
    rows = {row["check_id"]: row for row in snapshot["checks"]}

    assert snapshot["final_recommendation"] == "inconsistent_requires_operator_review"
    assert rows["queue_selection_does_not_upgrade_broader_trust"]["status"] == (
        "inconsistent"
    )
    assert rows["queue_selection_does_not_upgrade_broader_trust"]["mismatch"] == (
        "bounded_selection_upgraded_queue_trust"
    )


def test_current_repo_snapshot_is_read_only_and_serializable() -> None:
    snapshot = audit.collect_snapshot(frozen_utc=FROZEN)

    assert snapshot["report_kind"] == audit.REPORT_KIND
    assert snapshot["mode"] == "dry-run"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["safety_invariants"]["read_only"] is True
    assert snapshot["safety_invariants"]["writes_artifacts"] is False
    assert snapshot["safety_invariants"]["mutates_audited_surfaces"] is False
    assert snapshot["safety_invariants"]["mutates_strategy_or_registry"] is False
    assert snapshot["safety_invariants"]["mutates_frozen_contracts"] is False
    assert snapshot["safety_invariants"]["strategy_synthesis_enabled"] is False
    assert snapshot["safety_invariants"]["addendum_runtime_activated"] is False
    assert json.loads(json.dumps(snapshot))["schema_version"] == audit.SCHEMA_VERSION


def test_module_does_not_import_mutation_or_runtime_surfaces() -> None:
    source = Path(audit.__file__).read_text(encoding="utf-8")

    forbidden_tokens = (
        "from dashboard",
        "import dashboard",
        "from registry",
        "import registry",
        "strategies.py",
        "packages.",
        "write_outputs(",
        "materialize(",
    )
    for token in forbidden_tokens:
        assert token not in source
