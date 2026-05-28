"""Read-only cross-surface consistency audit for trusted-loop evidence.

ADE-QRE-016D coverage. This module checks that trusted-loop evidence surfaces
agree about readiness, blockers, and queue status without mutating the audited
surfaces or granting authority.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Final

from reporting import trusted_loop_missing_evidence_fail_closed as _fail_closed

SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "ade-qre-016d-2026-05-28"
REPORT_KIND: Final[str] = "trusted_loop_consistency_audit"

REQUIRED_SURFACES: Final[tuple[str, ...]] = (
    "reason_records",
    "research_quality_kpis",
    "routing_readiness",
    "sampling_readiness",
    "diagnostics_loop",
    "retrieval_coverage",
    "queue_status",
)

_EVIDENCE_ONLY_SURFACES: Final[tuple[str, ...]] = (
    "diagnostics_loop",
    "retrieval_coverage",
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


def _surface_rows(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for raw in _sequence(snapshot.get("surfaces")):
        row = _mapping(raw)
        surface_id = row.get("surface_id")
        if isinstance(surface_id, str):
            rows[surface_id] = row
    return rows


def _check_row(
    *,
    check_id: str,
    surface_id: str,
    status: str,
    evidence: Mapping[str, Any],
    blocker: str,
    mismatch: str | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "surface_id": surface_id,
        "status": status,
        "evidence": dict(evidence),
        "blocker": blocker,
        "mismatch": mismatch,
    }


def _surface_consistency_checks(
    rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for surface_id in REQUIRED_SURFACES:
        row = rows.get(surface_id)
        if row is None:
            checks.append(
                _check_row(
                    check_id=f"{surface_id}_present",
                    surface_id=surface_id,
                    status="inconsistent",
                    evidence={"surface_present": False},
                    blocker="Required surface is absent from the audit input.",
                    mismatch="missing_required_surface",
                )
            )
            continue

        ready = row.get("ready") is True
        fail_closed = row.get("fail_closed") is True
        missing = _strings(row.get("missing_evidence"))
        claim_blocked = str(row.get("trust_claim_blocked") or "")
        status = str(row.get("status") or "unknown")

        mismatches: list[str] = []
        if ready == fail_closed:
            mismatches.append("ready_and_fail_closed_flags_disagree")
        if ready and missing:
            mismatches.append("ready_surface_has_missing_evidence")
        if not ready and not fail_closed:
            mismatches.append("non_ready_surface_not_fail_closed")
        if fail_closed and not missing:
            mismatches.append("fail_closed_surface_lacks_missing_evidence")
        if fail_closed and not claim_blocked:
            mismatches.append("fail_closed_surface_lacks_blocked_claim")
        if ready and status != "ready":
            mismatches.append("ready_surface_status_not_ready")

        if mismatches:
            checks.append(
                _check_row(
                    check_id=f"{surface_id}_readiness_consistency",
                    surface_id=surface_id,
                    status="inconsistent",
                    evidence={
                        "ready": ready,
                        "fail_closed": fail_closed,
                        "status": status,
                        "missing_evidence": missing,
                    },
                    blocker=(
                        "Surface readiness, fail-closed state, status, and "
                        "missing-evidence fields must agree before a trust "
                        "claim can be made."
                    ),
                    mismatch=";".join(mismatches),
                )
            )
            continue

        checks.append(
            _check_row(
                check_id=f"{surface_id}_readiness_consistency",
                surface_id=surface_id,
                status="passed" if ready else "blocked_with_evidence",
                evidence={
                    "ready": ready,
                    "fail_closed": fail_closed,
                    "status": status,
                    "missing_evidence": missing,
                },
                blocker="" if ready else claim_blocked,
            )
        )
    return checks


def _cross_surface_checks(
    snapshot: Mapping[str, Any],
    rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary = _mapping(snapshot.get("summary"))
    final = str(snapshot.get("final_recommendation") or "unknown")
    trusted_ready = summary.get("trusted_loop_ready") is True
    fail_closed_count = int(summary.get("fail_closed_surface_count") or 0)
    ready_count = int(summary.get("ready_surface_count") or 0)
    required_count = int(summary.get("required_surface_count") or 0)
    checks: list[dict[str, Any]] = []

    expected_final = (
        "ready_all_required_evidence_present"
        if fail_closed_count == 0
        else "not_ready_missing_evidence"
    )
    final_ok = final == expected_final and trusted_ready == (fail_closed_count == 0)
    checks.append(
        _check_row(
            check_id="summary_matches_surface_counts",
            surface_id="trusted_loop_summary",
            status="passed" if final_ok else "inconsistent",
            evidence={
                "final_recommendation": final,
                "expected_final_recommendation": expected_final,
                "trusted_loop_ready": trusted_ready,
                "ready_surface_count": ready_count,
                "fail_closed_surface_count": fail_closed_count,
                "required_surface_count": required_count,
            },
            blocker=(
                ""
                if final_ok
                else "Summary readiness must match the surface readiness counts."
            ),
            mismatch=None if final_ok else "summary_count_or_final_recommendation_mismatch",
        )
    )

    queue = rows.get("queue_status", {})
    queue_evidence = _mapping(queue.get("evidence"))
    bounded_selection = queue_evidence.get("bounded_current_selection_ready") is True
    queue_ready = queue.get("ready") is True
    missing_done = _strings(queue_evidence.get("missing_done_evidence_items"))
    queue_ok = not (bounded_selection and missing_done and queue_ready)
    checks.append(
        _check_row(
            check_id="queue_selection_does_not_upgrade_broader_trust",
            surface_id="queue_status",
            status="passed" if queue_ok else "inconsistent",
            evidence={
                "bounded_current_selection_ready": bounded_selection,
                "queue_ready": queue_ready,
                "missing_done_evidence_items": missing_done,
                "next_eligible_ready_item": queue_evidence.get(
                    "next_eligible_ready_item"
                ),
            },
            blocker=(
                ""
                if queue_ok
                else (
                    "A bounded next queue item cannot upgrade broader queue "
                    "status while done evidence is missing."
                )
            ),
            mismatch=None if queue_ok else "bounded_selection_upgraded_queue_trust",
        )
    )

    for surface_id in _EVIDENCE_ONLY_SURFACES:
        row = rows.get(surface_id, {})
        trust_claim = str(row.get("trust_claim_blocked") or "").lower()
        ready = row.get("ready") is True
        authority_language_present = (
            "authorize" in trust_claim
            or "authority" in trust_claim
            or "context, not authority" in trust_claim
            or "evidence surfaces only" in trust_claim
        )
        ok = ready or authority_language_present
        checks.append(
            _check_row(
                check_id=f"{surface_id}_remains_non_authority",
                surface_id=surface_id,
                status="passed" if ok else "inconsistent",
                evidence={
                    "ready": ready,
                    "trust_claim_blocked": row.get("trust_claim_blocked"),
                },
                blocker=(
                    ""
                    if ok
                    else (
                        f"{surface_id} must be framed as evidence/context, "
                        "not authority."
                    )
                ),
                mismatch=None if ok else "evidence_surface_missing_non_authority_claim",
            )
        )

    safety = _mapping(snapshot.get("safety_invariants"))
    safety_ok = (
        safety.get("read_only") is True
        and safety.get("strategy_synthesis_enabled") is False
        and safety.get("addendum_runtime_activated") is False
        and safety.get("mutates_strategy_or_registry") is False
        and safety.get("mutates_frozen_contracts") is False
    )
    checks.append(
        _check_row(
            check_id="safety_invariants_preserve_non_runtime_scope",
            surface_id="safety_invariants",
            status="passed" if safety_ok else "inconsistent",
            evidence={
                "read_only": safety.get("read_only"),
                "strategy_synthesis_enabled": safety.get(
                    "strategy_synthesis_enabled"
                ),
                "addendum_runtime_activated": safety.get(
                    "addendum_runtime_activated"
                ),
                "mutates_strategy_or_registry": safety.get(
                    "mutates_strategy_or_registry"
                ),
                "mutates_frozen_contracts": safety.get("mutates_frozen_contracts"),
            },
            blocker=(
                ""
                if safety_ok
                else (
                    "Consistency audit requires read-only, non-runtime, "
                    "non-synthesis safety invariants."
                )
            ),
            mismatch=None if safety_ok else "safety_invariant_mismatch",
        )
    )
    return checks


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    fail_closed_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    source = fail_closed_snapshot or _fail_closed.collect_snapshot(frozen_utc=ts)
    rows = _surface_rows(source)
    checks = _surface_consistency_checks(rows) + _cross_surface_checks(source, rows)
    inconsistent = [row for row in checks if row["status"] == "inconsistent"]
    blocked = [row for row in checks if row["status"] == "blocked_with_evidence"]
    passed = [row for row in checks if row["status"] == "passed"]

    if inconsistent:
        final = "inconsistent_requires_operator_review"
    elif blocked:
        final = "consistent_blocked_by_evidence"
    else:
        final = "consistent_all_required_surfaces_ready"

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "source_report_kind": source.get("report_kind"),
        "summary": {
            "required_surfaces": list(REQUIRED_SURFACES),
            "check_count": len(checks),
            "passed_check_count": len(passed),
            "blocked_with_evidence_count": len(blocked),
            "inconsistent_check_count": len(inconsistent),
            "audited_surface_count": len(rows),
        },
        "checks": checks,
        "final_recommendation": final,
        "operator_summary": (
            "Cross-surface inconsistencies require operator review."
            if inconsistent
            else (
                f"{len(blocked)} consistency checks are blocked by explicit "
                "evidence; no readiness upgrade is inferred."
            )
            if blocked
            else "All required trusted-loop surfaces are internally consistent."
        ),
        "safety_invariants": {
            "read_only": True,
            "writes_artifacts": False,
            "mutates_audited_surfaces": False,
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
            "retrieval_context_not_authority": True,
            "diagnostics_evidence_not_authority": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.trusted_loop_consistency_audit",
        description="Audit cross-surface consistency for trusted-loop evidence.",
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
    "REQUIRED_SURFACES",
    "SCHEMA_VERSION",
    "collect_snapshot",
]
