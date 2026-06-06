from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_candidate_explanation_rows as candidate_rows
from research import qre_failure_action_from_basket as failure_action
from research import qre_failure_recurrence_learning as recurrence_learning
from research import qre_hypothesis_seed_feasibility as hypothesis_feasibility
from research import qre_oos_evidence_blockers as oos_blockers
from research import qre_real_basket_diagnosis as basket_diagnosis
from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_reason_records_v1 as reason_records
from research import qre_routing_readiness_from_basket as routing_readiness
from research import qre_sampling_readiness_from_basket as sampling_readiness
from research import qre_trusted_loop_operator_kpis as trusted_kpis


REPORT_KIND: Final[str] = "qre_pre_shadow_paper_research_readiness"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_pre_shadow_paper_research_readiness")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_pre_shadow_paper_research_readiness/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _all_true(*values: bool) -> bool:
    return all(bool(value) for value in values)


def _source_readiness_note(
    *,
    coverage_summary: Mapping[str, Any],
    diagnosis_summary: Mapping[str, Any],
    source_readiness_linked: bool,
) -> str:
    if source_readiness_linked:
        return "Source/cache readiness sidecars are present and at least one basket is source-ready."
    artifact_availability = diagnosis_summary.get("artifact_availability")
    if not isinstance(artifact_availability, Mapping):
        artifact_availability = {}
    source_quality_present = bool(artifact_availability.get("source_quality"))
    cache_manifest_present = bool(artifact_availability.get("cache_manifest"))
    if not source_quality_present and not cache_manifest_present:
        return "Source quality and cache manifest sidecars are missing or not generated in this environment."
    if not source_quality_present:
        return "Source quality readiness sidecar is missing, stale, or not deployed in this environment."
    if not cache_manifest_present:
        return "Cache manifest sidecar is missing, stale, or not deployed in this environment."
    sidecar_status = coverage_summary.get("source_cache_sidecar_status")
    if isinstance(sidecar_status, Mapping):
        if str(sidecar_status.get("source_quality_sidecar_status") or "") != "present":
            return "Source quality readiness sidecar is not present for the current readiness write."
        if str(sidecar_status.get("cache_manifest_sidecar_status") or "") != "present":
            return "Cache manifest sidecar is not present for the current readiness write."
    return "Source/cache sidecars are present, but no basket currently qualifies as source-ready."


def _readiness_state(
    *,
    diagnosis_exists: bool,
    reason_records_traceable: bool,
    routing_evidence_backed: bool,
    sampling_evidence_backed: bool,
    failure_action_present: bool,
    source_readiness_linked: bool,
    candidate_blockers_explainable: bool,
    oos_blockers_explainable: bool,
    operator_report_complete: bool,
    synthesis_still_blocked: bool,
    boundaries_untouched: bool,
    trusted_loop_maturity_state: str,
) -> tuple[str, str]:
    if not diagnosis_exists:
        return (
            "NOT_READY_RESEARCH_LOOP_SCAFFOLD",
            "Real basket diagnosis does not yet exist, so the research loop is still scaffold-level.",
        )
    if not reason_records_traceable:
        return (
            "NOT_READY_MISSING_REASON_RECORDS",
            "Durable reason records are missing or non-traceable, so the loop is not ready for later readiness planning.",
        )
    if not routing_evidence_backed or not sampling_evidence_backed:
        return (
            "NOT_READY_NO_ROUTING_SAMPLING_EVIDENCE",
            "Routing or sampling still lacks evidence-backed readiness, so the loop must stay pre-readiness.",
        )
    if not failure_action_present:
        return (
            "NOT_READY_FAILURE_ACTION_EMPTY",
            "Failure-to-action mapping is empty, so the loop still lacks bounded next-action coverage.",
        )
    foundational_ready = _all_true(
        source_readiness_linked,
        candidate_blockers_explainable,
        oos_blockers_explainable,
        operator_report_complete,
        synthesis_still_blocked,
        boundaries_untouched,
    )
    if not foundational_ready:
        return (
            "APPROACHING_READY_FOR_READINESS_PLANNING",
            "Core research-loop evidence exists, but one or more explanation, source-linkage, or safety-completeness criteria are still incomplete.",
        )
    if trusted_loop_maturity_state == "operator_trusted_candidate":
        return (
            "READY_FOR_SEPARATE_SHADOW_PAPER_READINESS_PLANNING",
            "The research loop is mature enough for a separate later shadow/paper readiness planning track, while runtime authority remains disabled.",
        )
    return (
        "APPROACHING_READY_FOR_READINESS_PLANNING",
        "The research loop is evidence-backed and bounded, but it is not yet operator-trusted enough for a separate readiness planning track.",
    )


def build_pre_shadow_paper_research_readiness(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    diagnosis = basket_diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    coverage = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    routing = routing_readiness.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling = sampling_readiness.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reasons = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    candidates = candidate_rows.build_candidate_explanation_rows(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    oos = oos_blockers.build_oos_evidence_blockers(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    kpis = trusted_kpis.build_trusted_loop_operator_kpis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    feasibility = hypothesis_feasibility.build_hypothesis_seed_feasibility(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    recurrence = recurrence_learning.build_failure_recurrence_learning(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    diagnosis_rows = diagnosis.get("rows")
    if not isinstance(diagnosis_rows, list):
        diagnosis_rows = []
    candidate_rows_list = candidates.get("rows")
    if not isinstance(candidate_rows_list, list):
        candidate_rows_list = []
    oos_rows = oos.get("rows")
    if not isinstance(oos_rows, list):
        oos_rows = []
    feasibility_rows = feasibility.get("rows")
    if not isinstance(feasibility_rows, list):
        feasibility_rows = []

    routing_summary = routing.get("summary") or {}
    sampling_summary = sampling.get("summary") or {}
    failure_summary = failure.get("summary") or {}
    reason_meta = reasons.get("meta") or {}
    kpi_summary = kpis.get("summary") or {}
    coverage_summary = coverage.get("summary") or {}
    diagnosis_summary = diagnosis.get("summary") or {}

    diagnosis_exists = len(diagnosis_rows) > 0
    routing_evidence_backed = bool(routing_summary.get("routing_ready_count")) or bool(
        routing_summary.get("evidence_backed_zero_ready")
    )
    sampling_evidence_backed = bool(sampling_summary.get("sampling_ready_count")) or bool(
        sampling_summary.get("evidence_backed_zero_ready")
    )
    reason_records_traceable = int(reason_meta.get("record_count") or 0) > 0
    failure_action_present = (
        int(failure_summary.get("actionable_count") or 0) > 0
        or int(failure_summary.get("non_actionable_count") or 0) > 0
    )
    source_readiness_linked = float(kpi_summary.get("source_ready_basket_pct") or 0.0) > 0.0
    source_readiness_note = _source_readiness_note(
        coverage_summary=coverage_summary,
        diagnosis_summary=diagnosis_summary,
        source_readiness_linked=source_readiness_linked,
    )
    candidate_blockers_explainable = len(candidate_rows_list) > 0 and float(
        kpi_summary.get("unknown_failure_rate") or 100.0
    ) < 100.0
    oos_blockers_explainable = len(oos_rows) > 0 and bool(
        (oos.get("summary") or {}).get("final_recommendation") == "oos_evidence_blockers_ready"
    )
    operator_report_complete = float(
        kpi_summary.get("operator_explanation_completeness_score") or 0.0
    ) > 0.0
    synthesis_still_blocked = int(kpi_summary.get("trusted_loop_maturity_state") == "working_capability") or int(
        kpi_summary.get("trusted_loop_maturity_state") == "operator_trusted_candidate"
    )
    safety_flags = [
        bool((report.get("safety_invariants") or {}).get("paper_shadow_live_forbidden"))
        and bool((report.get("safety_invariants") or {}).get("broker_risk_execution_forbidden"))
        and not bool((report.get("safety_invariants") or {}).get("mutates_frozen_contracts"))
        for report in (
            diagnosis,
            coverage,
            routing,
            sampling,
            failure,
            candidates,
            oos,
            kpis,
            feasibility,
            recurrence,
        )
        if isinstance(report, Mapping)
    ]
    boundaries_untouched = all(safety_flags)
    readiness_state, operator_explanation = _readiness_state(
        diagnosis_exists=diagnosis_exists,
        reason_records_traceable=reason_records_traceable,
        routing_evidence_backed=routing_evidence_backed,
        sampling_evidence_backed=sampling_evidence_backed,
        failure_action_present=failure_action_present,
        source_readiness_linked=source_readiness_linked,
        candidate_blockers_explainable=candidate_blockers_explainable,
        oos_blockers_explainable=oos_blockers_explainable,
        operator_report_complete=operator_report_complete,
        synthesis_still_blocked=bool(synthesis_still_blocked),
        boundaries_untouched=boundaries_untouched,
        trusted_loop_maturity_state=str(kpi_summary.get("trusted_loop_maturity_state") or "scaffold"),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "readiness_state": readiness_state,
            "real_basket_diagnosis_exists": diagnosis_exists,
            "basket_inventory_count": len(diagnosis_rows),
            "routing_evidence_backed": routing_evidence_backed,
            "sampling_evidence_backed": sampling_evidence_backed,
            "reason_records_traceable": reason_records_traceable,
            "reason_record_count": int(reason_meta.get("record_count") or 0),
            "failure_action_present": failure_action_present,
            "source_readiness_linked": source_readiness_linked,
            "source_readiness_note": source_readiness_note,
            "candidate_blockers_explainable": candidate_blockers_explainable,
            "oos_blockers_explainable": oos_blockers_explainable,
            "operator_report_complete": operator_report_complete,
            "hypothesis_seed_count": len(feasibility_rows),
            "trusted_loop_maturity_state": str(
                kpi_summary.get("trusted_loop_maturity_state") or "scaffold"
            ),
            "synthesis_still_blocked": bool(synthesis_still_blocked),
            "paper_shadow_live_untouched": boundaries_untouched,
            "broker_risk_execution_untouched": boundaries_untouched,
            "final_recommendation": readiness_state,
            "operator_summary": operator_explanation,
        },
        "supporting_reports": {
            "diagnosis": diagnosis.get("summary"),
            "coverage": coverage_summary,
            "routing": routing_summary,
            "sampling": sampling_summary,
            "reason_records": reason_meta,
            "failure_action": failure_summary,
            "candidate_explanations": candidates.get("summary"),
            "oos_blockers": oos.get("summary"),
            "trusted_loop_kpis": kpi_summary,
            "hypothesis_seed_feasibility": feasibility.get("summary"),
            "failure_recurrence_learning": recurrence.get("summary"),
        },
        "safety_invariants": {
            "read_only": True,
            "implements_shadow_readiness": False,
            "implements_paper_readiness": False,
            "implements_live_readiness": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    table = _table(
        ["Gate", "Value"],
        [
            ["readiness_state", str(summary.get("readiness_state") or "")],
            ["real_basket_diagnosis_exists", str(summary.get("real_basket_diagnosis_exists") or False)],
            ["routing_evidence_backed", str(summary.get("routing_evidence_backed") or False)],
            ["sampling_evidence_backed", str(summary.get("sampling_evidence_backed") or False)],
            ["reason_records_traceable", str(summary.get("reason_records_traceable") or False)],
            ["failure_action_present", str(summary.get("failure_action_present") or False)],
            ["source_readiness_linked", str(summary.get("source_readiness_linked") or False)],
            ["source_readiness_note", str(summary.get("source_readiness_note") or "")],
            ["candidate_blockers_explainable", str(summary.get("candidate_blockers_explainable") or False)],
            ["oos_blockers_explainable", str(summary.get("oos_blockers_explainable") or False)],
            ["operator_report_complete", str(summary.get("operator_report_complete") or False)],
            ["trusted_loop_maturity_state", str(summary.get("trusted_loop_maturity_state") or "")],
            ["synthesis_still_blocked", str(summary.get("synthesis_still_blocked") or False)],
        ],
    )
    return "\n".join(
        [
            "# QRE Pre-Shadow/Paper Research Readiness",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Readiness gate",
            table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_pre_shadow_paper_research_readiness: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_pre_shadow_paper_research_readiness",
        description="Build a read-only QRE pre-shadow/paper research readiness gate.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_pre_shadow_paper_research_readiness(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
