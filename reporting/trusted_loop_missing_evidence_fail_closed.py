"""Read-only missing-evidence fail-closed check for trusted-loop surfaces.

ADE-QRE-016C coverage. This module aggregates existing read-only evidence
surfaces and reports whether missing evidence is still treated as blocking. It
does not materialize artifacts, mutate queues, grant authority, or enable
strategy synthesis.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_diagnostics import research_diagnostics_loop as _diagnostics
from packages.qre_research import retrieval_coverage as _retrieval
from reporting import ade_queue_status_self_audit as _queue
from reporting import trusted_loop_materialization as _tlm

SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "ade-qre-016c-2026-05-28"
REPORT_KIND: Final[str] = "trusted_loop_missing_evidence_fail_closed"

_SURFACE_IDS: Final[tuple[str, ...]] = (
    "reason_records",
    "research_quality_kpis",
    "routing_readiness",
    "sampling_readiness",
    "diagnostics_loop",
    "retrieval_coverage",
    "queue_status",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _strings(value: Any) -> list[str]:
    return [str(item) for item in _sequence(value)]


def _surface_row(
    *,
    surface_id: str,
    status: str,
    ready: bool,
    missing_evidence: Sequence[str],
    evidence: Mapping[str, Any],
    trust_claim_blocked: str,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "surface_id": surface_id,
        "status": status,
        "ready": ready,
        "fail_closed": not ready,
        "missing_evidence": list(missing_evidence),
        "evidence": dict(evidence),
        "trust_claim_blocked": trust_claim_blocked,
        "notes": list(notes),
    }


def _reason_record_surface(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    density = _mapping(snapshot.get("reason_record_evidence_density"))
    metrics = _mapping(density.get("metrics"))
    final = str(density.get("final_recommendation") or "unknown")
    record_count = int(metrics.get("record_count") or 0)
    records_with_refs = int(metrics.get("records_with_evidence_refs") or 0)
    ready = final == "evidence_density_ready"
    missing: list[str] = []
    if record_count <= 0:
        missing.append("reason_records_present")
    if records_with_refs <= 0:
        missing.append("reason_records_with_evidence_refs")
    return _surface_row(
        surface_id="reason_records",
        status="ready" if ready else "fail_closed",
        ready=ready,
        missing_evidence=missing,
        evidence={
            "final_recommendation": final,
            "record_count": record_count,
            "records_with_evidence_refs": records_with_refs,
        },
        trust_claim_blocked=(
            "Reason records cannot support trusted-loop readiness until durable "
            "records with evidence references are present."
        ),
    )


def _kpi_surface(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    kpis = _mapping(snapshot.get("research_quality_kpi_readiness"))
    values = _mapping(kpis.get("values"))
    required = _strings(kpis.get("kpi_ids"))
    complete = int(kpis.get("complete_value_count") or 0)
    fail_closed = int(kpis.get("fail_closed_count") or 0)
    ready = bool(required) and complete == len(required) and fail_closed == 0
    missing = [
        kpi_id
        for kpi_id, row in sorted(values.items())
        if _mapping(row).get("numeric_value_ready") is not True
    ]
    if not required:
        missing.append("research_quality_kpi_ids_present")
    return _surface_row(
        surface_id="research_quality_kpis",
        status="ready" if ready else "fail_closed",
        ready=ready,
        missing_evidence=missing,
        evidence={
            "required_kpi_count": len(required),
            "complete_value_count": complete,
            "fail_closed_count": fail_closed,
        },
        trust_claim_blocked=(
            "KPI doctrine or partial KPI evidence cannot be interpreted as "
            "numeric research-quality readiness."
        ),
    )


def _routing_sampling_surface(
    snapshot: Mapping[str, Any],
    *,
    surface_id: str,
    row_id: str,
) -> dict[str, Any]:
    density = _mapping(snapshot.get("routing_sampling_readiness_density"))
    row = _mapping(_mapping(density.get("values")).get(row_id))
    ready = row.get("ready") is True
    status = str(row.get("status") or "missing")
    return _surface_row(
        surface_id=surface_id,
        status="ready" if ready else "fail_closed",
        ready=ready,
        missing_evidence=_strings(row.get("missing_evidence"))
        or ["readiness_evidence_present"],
        evidence={
            "source_status": status,
            "artifact_present": row.get("artifact_present"),
            "final_recommendation": row.get("final_recommendation"),
            "readiness_score": row.get("readiness_score"),
        },
        trust_claim_blocked=(
            f"{surface_id} cannot be treated as ready until the existing "
            "read-only artifact contains positive ready evidence."
        ),
    )


def _diagnostics_surface(status: Mapping[str, Any]) -> dict[str, Any]:
    ready = status.get("diagnostics_loop_ready") is True
    missing = [] if ready else ["diagnostics_loop_ready"]
    return _surface_row(
        surface_id="diagnostics_loop",
        status="ready" if ready else "fail_closed",
        ready=ready,
        missing_evidence=missing,
        evidence={
            "source_status": status.get("status"),
            "path": status.get("path"),
            "schema_version": status.get("schema_version"),
        },
        trust_claim_blocked=(
            "Diagnostics are evidence surfaces only; missing or invalid "
            "diagnostics cannot authorize readiness."
        ),
    )


def _retrieval_surface(status: Mapping[str, Any]) -> dict[str, Any]:
    ready = status.get("retrieval_coverage_ready") is True
    missing = [] if ready else ["retrieval_coverage_ready"]
    return _surface_row(
        surface_id="retrieval_coverage",
        status="ready" if ready else "fail_closed",
        ready=ready,
        missing_evidence=missing,
        evidence={
            "source_status": status.get("status"),
            "path": status.get("path"),
            "schema_version": status.get("schema_version"),
        },
        trust_claim_blocked=(
            "Retrieval remains context, not authority; missing retrieval "
            "coverage cannot be treated as trusted-loop readiness."
        ),
    )


def _queue_surface(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(snapshot.get("summary"))
    eligible = _strings(summary.get("eligible_ready_items"))
    missing_done = _strings(summary.get("missing_done_evidence_items"))
    dependency_gaps = _strings(summary.get("dependency_gap_items"))
    stale_ready = _strings(summary.get("stale_historical_ready_items"))
    blocked_missing = _strings(summary.get("blocked_items_missing_reason"))
    deferred_missing = _strings(summary.get("deferred_items_missing_reason"))
    next_item = snapshot.get("summary", {}).get("next_eligible_ready_item")
    exact_one_next = len(eligible) == 1 and next_item == eligible[0]
    missing = []
    if not exact_one_next:
        missing.append("exactly_one_next_eligible_ready_item")
    if missing_done:
        missing.append("complete_done_evidence_for_all_done_items")
    if dependency_gaps:
        missing.append("queue_dependencies_resolved")
    if blocked_missing:
        missing.append("blocked_items_have_reasons")
    if deferred_missing:
        missing.append("deferred_items_have_reasons")

    ready = not missing
    status = (
        "ready"
        if ready
        else "bounded_selection_ready_with_warnings"
        if exact_one_next
        else "fail_closed"
    )
    return _surface_row(
        surface_id="queue_status",
        status=status,
        ready=ready,
        missing_evidence=missing,
        evidence={
            "final_recommendation": snapshot.get("final_recommendation"),
            "eligible_ready_items": eligible,
            "next_eligible_ready_item": next_item,
            "missing_done_evidence_items": missing_done,
            "dependency_gap_items": dependency_gaps,
            "stale_historical_ready_items": stale_ready,
            "bounded_current_selection_ready": exact_one_next,
        },
        trust_claim_blocked=(
            "Queue status cannot be treated as broadly trusted while done "
            "evidence, dependency, blocked, deferred, or unique-next-item "
            "evidence is missing."
        ),
        notes=(
            (
                "A single bounded next item can still be visible while broader "
                "queue-status trust fails closed."
            ),
        )
        if exact_one_next and not ready
        else (),
    )


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    repo_root: Path = Path("."),
    reason_records_artifact_dir: Path | None = None,
    routing_artifact_dir: Path | None = None,
    sampling_artifact_dir: Path | None = None,
    observability_artifact_dir: Path | None = None,
    diagnostics_output_dir: Path = _diagnostics.DEFAULT_OUTPUT_DIR,
    retrieval_output_dir: Path = _retrieval.DEFAULT_OUTPUT_DIR,
    queue_doc_path: Path | None = None,
    materialization_snapshot: Mapping[str, Any] | None = None,
    diagnostics_status: Mapping[str, Any] | None = None,
    retrieval_status: Mapping[str, Any] | None = None,
    queue_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    materialized = materialization_snapshot or _tlm.collect_snapshot(
        frozen_utc=ts,
        reason_records_artifact_dir=reason_records_artifact_dir,
        routing_artifact_dir=routing_artifact_dir,
        sampling_artifact_dir=sampling_artifact_dir,
        observability_artifact_dir=observability_artifact_dir,
    )
    diagnostics = diagnostics_status or _diagnostics.read_diagnostics_loop_status(
        output_dir=diagnostics_output_dir,
        repo_root=repo_root,
    )
    retrieval = retrieval_status or _retrieval.read_retrieval_coverage_status(
        output_dir=retrieval_output_dir,
        repo_root=repo_root,
    )
    queue = queue_snapshot or _queue.collect_snapshot(
        queue_doc_path=queue_doc_path,
        frozen_utc=ts,
    )

    rows = [
        _reason_record_surface(materialized),
        _kpi_surface(materialized),
        _routing_sampling_surface(
            materialized,
            surface_id="routing_readiness",
            row_id="routing_ready",
        ),
        _routing_sampling_surface(
            materialized,
            surface_id="sampling_readiness",
            row_id="sampling_ready",
        ),
        _diagnostics_surface(diagnostics),
        _retrieval_surface(retrieval),
        _queue_surface(queue),
    ]
    ready_count = sum(1 for row in rows if row["ready"] is True)
    fail_closed_count = len(rows) - ready_count
    missing_evidence_count = sum(len(row["missing_evidence"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": {
            "required_surfaces": list(_SURFACE_IDS),
            "required_surface_count": len(rows),
            "ready_surface_count": ready_count,
            "fail_closed_surface_count": fail_closed_count,
            "missing_evidence_count": missing_evidence_count,
            "trusted_loop_ready": fail_closed_count == 0,
        },
        "surfaces": rows,
        "final_recommendation": (
            "ready_all_required_evidence_present"
            if fail_closed_count == 0
            else "not_ready_missing_evidence"
        ),
        "operator_summary": (
            "All required trusted-loop evidence surfaces are present."
            if fail_closed_count == 0
            else (
                f"{fail_closed_count}/{len(rows)} trusted-loop surfaces fail "
                "closed because required evidence is missing, incomplete, or "
                "not trusted."
            )
        ),
        "safety_invariants": {
            "read_only": True,
            "writes_artifacts": False,
            "mutates_queue": False,
            "mutates_routing": False,
            "mutates_sampling": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "strategy_synthesis_enabled": False,
            "addendum_runtime_activated": False,
            "dashboard_mutation_route_added": False,
            "approval_mutation_added": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.trusted_loop_missing_evidence_fail_closed",
        description="Check that missing trusted-loop evidence fails closed.",
    )
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    print(
        json.dumps(
            collect_snapshot(frozen_utc=args.frozen_utc),
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
]
