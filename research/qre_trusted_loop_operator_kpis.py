from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_candidate_explanation_rows as candidate_rows
from research import qre_failure_action_from_basket as failure_action
from research import qre_oos_evidence_blockers as oos_blockers
from research import qre_real_basket_diagnosis as basket_diagnosis
from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_reason_record_audit as reason_audit
from research import qre_reason_records_v1 as reason_records
from research import qre_routing_readiness_from_basket as routing
from research import qre_sampling_readiness_from_basket as sampling


REPORT_KIND: Final[str] = "qre_trusted_loop_operator_kpis"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_trusted_loop_operator_kpis")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_trusted_loop_operator_kpis/"


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _trusted_loop_maturity_state(
    *,
    basket_inventory_count: int,
    routing_ready_count: int,
    sampling_ready_count: int,
    reason_record_count: int,
    failure_actionable_count: int,
    operator_explanation_completeness_score: float,
    synthesis_blocked_count: int,
) -> str:
    if basket_inventory_count == 0 or reason_record_count == 0:
        return "scaffold"
    if synthesis_blocked_count > 0:
        return "working_capability"
    if (
        routing_ready_count > 0
        and sampling_ready_count > 0
        and failure_actionable_count > 0
        and operator_explanation_completeness_score >= 90.0
    ):
        return "operator_trusted_candidate"
    return "working_capability"


def build_trusted_loop_operator_kpis(
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
    routing_report = routing.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling_report = sampling.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    audit = reason_audit.build_reason_record_audit(
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

    diagnosis_rows = diagnosis.get("rows") if isinstance(diagnosis.get("rows"), list) else []
    coverage_rows = coverage.get("rows") if isinstance(coverage.get("rows"), list) else []
    failure_rows = failure.get("rows") if isinstance(failure.get("rows"), list) else []
    candidate_rows_list = (
        candidates.get("rows") if isinstance(candidates.get("rows"), list) else []
    )

    basket_inventory_count = len(diagnosis_rows)
    diagnosable_basket_count = sum(
        1 for row in diagnosis_rows if str(row.get("diagnosis_class") or "") == "diagnosable"
    )
    routing_ready_count = int(routing_report.get("summary", {}).get("routing_ready_count") or 0)
    sampling_ready_count = int(
        sampling_report.get("summary", {}).get("sampling_ready_count") or 0
    )
    reason_record_count = int(reason_snapshot.get("meta", {}).get("record_count") or 0)
    reason_record_coverage_pct = float(
        audit.get("summary", {}).get("reason_record_coverage_pct") or 0.0
    )
    failure_actionable_count = int(failure.get("summary", {}).get("actionable_count") or 0)
    failure_actionability_pct = _pct(failure_actionable_count, len(failure_rows))
    source_ready_basket_pct = _pct(
        sum(
            1
            for row in coverage_rows
            if bool((row.get("evidence_presence") or {}).get("source_quality_ready"))
        ),
        len(coverage_rows),
    )
    evidence_complete_basket_pct = _pct(
        sum(
            1
            for row in coverage_rows
            if str(row.get("evidence_completeness_status") or "") == "complete"
        ),
        len(coverage_rows),
    )
    duplicate_suppression_candidates = sum(
        1
        for row in failure_rows
        if str(row.get("recommended_action") or "")
        in {"defer_as_duplicate", "suppress_until_new_evidence"}
    )
    unknown_failure_rate = _pct(
        sum(
            1
            for row in candidate_rows_list
            if str(row.get("primary_blocker") or "") in {"unknown", "unknown_requires_artifact_inspection"}
        ),
        len(candidate_rows_list),
    )
    operator_explanation_completeness_score = _pct(
        sum(
            1
            for row in candidate_rows_list
            if (row.get("reason_record_refs") or {}).get("record_ids")
            and str(row.get("safe_next_action") or "").strip()
            and str(row.get("paper_readiness_status") or "").strip()
            and str(row.get("synthesis_gate_state") or "").strip()
        ),
        len(candidate_rows_list),
    )
    synthesis_blocked_count = sum(
        1
        for row in candidate_rows_list
        if str(row.get("synthesis_gate_state") or "").startswith("blocked")
    )
    maturity_state = _trusted_loop_maturity_state(
        basket_inventory_count=basket_inventory_count,
        routing_ready_count=routing_ready_count,
        sampling_ready_count=sampling_ready_count,
        reason_record_count=reason_record_count,
        failure_actionable_count=failure_actionable_count,
        operator_explanation_completeness_score=operator_explanation_completeness_score,
        synthesis_blocked_count=synthesis_blocked_count,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_inventory_count": basket_inventory_count,
            "diagnosable_basket_count": diagnosable_basket_count,
            "routing_ready_count": routing_ready_count,
            "sampling_ready_count": sampling_ready_count,
            "reason_record_count": reason_record_count,
            "reason_record_coverage_pct": reason_record_coverage_pct,
            "failure_actionable_count": failure_actionable_count,
            "failure_actionability_pct": failure_actionability_pct,
            "source_ready_basket_pct": source_ready_basket_pct,
            "evidence_complete_basket_pct": evidence_complete_basket_pct,
            "duplicate_suppression_candidates": duplicate_suppression_candidates,
            "unknown_failure_rate": unknown_failure_rate,
            "operator_explanation_completeness_score": operator_explanation_completeness_score,
            "trusted_loop_maturity_state": maturity_state,
            "final_recommendation": (
                "trusted_loop_kpis_ready" if basket_inventory_count > 0 else "trusted_loop_kpis_missing"
            ),
            "operator_summary": (
                "Trusted-loop KPI projection aggregates current read-only basket, routing, "
                "sampling, reason-record, failure-action, and explanation surfaces. "
                "It does not authorize strategy synthesis or runtime activation."
            ),
        },
        "supporting_reports": {
            "diagnosis": diagnosis.get("summary"),
            "coverage": coverage.get("summary"),
            "routing": routing_report.get("summary"),
            "sampling": sampling_report.get("summary"),
            "reason_records": reason_snapshot.get("meta"),
            "reason_record_audit": audit.get("summary"),
            "failure_action": failure.get("summary"),
            "candidate_explanations": candidates.get("summary"),
            "oos_blockers": oos.get("summary"),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_candidate_lifecycle": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = [
        ("basket_inventory_count", summary.get("basket_inventory_count")),
        ("diagnosable_basket_count", summary.get("diagnosable_basket_count")),
        ("routing_ready_count", summary.get("routing_ready_count")),
        ("sampling_ready_count", summary.get("sampling_ready_count")),
        ("reason_record_count", summary.get("reason_record_count")),
        ("reason_record_coverage_pct", summary.get("reason_record_coverage_pct")),
        ("failure_actionable_count", summary.get("failure_actionable_count")),
        ("failure_actionability_pct", summary.get("failure_actionability_pct")),
        ("source_ready_basket_pct", summary.get("source_ready_basket_pct")),
        ("evidence_complete_basket_pct", summary.get("evidence_complete_basket_pct")),
        ("duplicate_suppression_candidates", summary.get("duplicate_suppression_candidates")),
        ("unknown_failure_rate", summary.get("unknown_failure_rate")),
        (
            "operator_explanation_completeness_score",
            summary.get("operator_explanation_completeness_score"),
        ),
        ("trusted_loop_maturity_state", summary.get("trusted_loop_maturity_state")),
    ]
    table = "\n".join(
        ["| KPI | Value |", "| --- | --- |"]
        + [f"| {key} | {value} |" for key, value in rows]
    )
    return "\n".join(
        [
            "# QRE Trusted-Loop Operator KPIs",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. KPI values",
            table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_trusted_loop_operator_kpis: refusing write outside allowlist: {path!r}"
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
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_trusted_loop_operator_kpis",
        description="Build read-only trusted-loop operator KPI projection.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_trusted_loop_operator_kpis(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
