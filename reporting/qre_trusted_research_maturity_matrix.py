from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_trusted_research_maturity_matrix"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_trusted_research_maturity_matrix")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_trusted_research_maturity_matrix.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_trusted_research_maturity_matrix/",
    "docs/governance/qre_trusted_research_maturity_matrix.md",
)
LEVELS: Final[tuple[str, ...]] = (
    "scaffold",
    "populated_working_capability",
    "integrated_capability",
    "repeatable_evidence_capability",
    "decision_useful_capability",
    "operator_trusted_capability",
    "evidence_authoritative_capability",
)


def _research_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            "qre_trusted_research_maturity_matrix: refusing write outside allowlist: "
            f"{path!r}"
        )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _top_blockers(counter: Counter[str], *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"blocker_code": code, "count": count}
        for code, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _evidence_refs(*refs: str) -> list[str]:
    out: list[str] = []
    for ref in refs:
        value = str(ref or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _surface_row(
    *,
    surface_id: str,
    surface_name: str,
    current_level: str,
    workstream: str,
    primary_phase: str,
    evidence_refs: Sequence[str],
    supporting_metrics: Mapping[str, Any],
    blocking_factors: Sequence[str],
    why_not_higher: str,
) -> dict[str, Any]:
    if current_level not in LEVELS:
        raise ValueError(f"unknown maturity level: {current_level}")
    return {
        "surface_id": surface_id,
        "surface_name": surface_name,
        "current_level": current_level,
        "workstream": workstream,
        "primary_phase": primary_phase,
        "evidence_refs": list(evidence_refs),
        "supporting_metrics": dict(supporting_metrics),
        "blocking_factors": list(blocking_factors),
        "why_not_higher": why_not_higher,
    }


def _planning_row(plan: Mapping[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), Mapping) else {}
    return _surface_row(
        surface_id="audit_gap_closure_plan",
        surface_name="Audit gap closure planning surface",
        current_level="populated_working_capability",
        workstream="A. Research Loop Maturity and Evidence Density",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_audit_gap_closure_plan.py",
            "docs/roadmap/qre_audit_gap_closure_plan.md",
        ),
        supporting_metrics={
            "audit_item_count": int(summary.get("audit_item_count") or 0),
            "gap_closure_pr_count": int(summary.get("gap_closure_pr_count") or 0),
        },
        blocking_factors=[
            "planning_surface_only",
            "no_runtime_evidence_promotion",
        ],
        why_not_higher=(
            "The surface records a deterministic closure plan, but it is explicitly planning-only "
            "and does not itself materialize mature research evidence."
        ),
    )


def _evidence_coverage_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    counts = (
        summary.get("evidence_completeness_status_counts")
        if isinstance(summary.get("evidence_completeness_status_counts"), Mapping)
        else {}
    )
    missing = (
        summary.get("missing_evidence_taxonomy_counts")
        if isinstance(summary.get("missing_evidence_taxonomy_counts"), Mapping)
        else {}
    )
    return _surface_row(
        surface_id="real_basket_evidence_coverage",
        surface_name="Real basket evidence coverage",
        current_level="repeatable_evidence_capability",
        workstream="A. Research Loop Maturity and Evidence Density",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_real_basket_evidence_coverage.py",
            "logs/qre_data_source_quality_readiness/latest.json",
            "logs/qre_data_cache_manifest/latest.json",
            "research/screening_evidence_latest.v1.json",
            "research/campaign_registry_latest.v1.json",
            "research/candidate_registry_latest.v1.json",
        ),
        supporting_metrics={
            "basket_inventory_count": int(summary.get("basket_inventory_count") or 0),
            "complete_count": int(counts.get("complete") or 0),
            "partial_count": int(counts.get("partial") or 0),
            "thin_count": int(counts.get("thin") or 0),
            "missing_count": int(counts.get("missing") or 0),
        },
        blocking_factors=[str(code) for code in sorted(missing.keys())],
        why_not_higher=(
            "Coverage is real and repeatable, but most baskets remain partial or thin and the "
            "dominant blockers are still source/cache breadth, lineage, and OOS completeness."
        ),
    )


def _reason_records_row(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), Mapping) else {}
    return _surface_row(
        surface_id="reason_records_v1",
        surface_name="Durable reason records",
        current_level="repeatable_evidence_capability",
        workstream="A. Research Loop Maturity and Evidence Density",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_reason_records_v1.py",
            "research/qre_real_basket_diagnosis.py",
            "research/qre_routing_readiness_from_basket.py",
            "research/qre_sampling_readiness_from_basket.py",
        ),
        supporting_metrics={
            "record_count": int(meta.get("record_count") or 0),
            "basket_records": int((meta.get("records_by_surface") or {}).get("basket_diagnosis") or 0),
            "routing_records": int((meta.get("records_by_surface") or {}).get("routing_readiness") or 0),
            "sampling_records": int((meta.get("records_by_surface") or {}).get("sampling_readiness") or 0),
            "skipped_missing_refs_count": int(meta.get("skipped_missing_refs_count") or 0),
        },
        blocking_factors=[
            "reason_record_manifest_not_materialized"
            if int(meta.get("record_count") or 0) > 0
            else "no_reason_records"
        ],
        why_not_higher=(
            "Reason records are already deterministic and evidence-linked, but the broader producer "
            "estate is not yet uniformly normalized or promoted into a complete authority-settled manifest."
        ),
    )


def _reason_record_audit_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return _surface_row(
        surface_id="reason_record_audit",
        surface_name="Reason-record producer audit",
        current_level="integrated_capability",
        workstream="A. Research Loop Maturity and Evidence Density",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_reason_record_audit.py",
            "logs/qre_reason_record_audit/latest.json",
            "logs/reason_records/manifest.v1.json",
        ),
        supporting_metrics={
            "producer_count": int(summary.get("producer_count") or 0),
            "expected_subject_count": int(summary.get("expected_subject_count") or 0),
            "subjects_with_evidence_refs": int(summary.get("subjects_with_evidence_refs") or 0),
            "reason_record_coverage_pct": float(summary.get("reason_record_coverage_pct") or 0.0),
            "reason_records_manifest_total": int(summary.get("reason_records_manifest_total") or 0),
        },
        blocking_factors=[
            "reason_record_manifest_empty"
            if int(summary.get("reason_records_manifest_total") or 0) == 0
            else "producer_gaps_remaining"
        ],
        why_not_higher=(
            "The audit integrates multiple producers and quantifies gaps, but the repo still reports "
            "an empty manifest total and incomplete producer-level evidence references."
        ),
    )


def _routing_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    counts = (
        summary.get("routing_readiness_state_counts")
        if isinstance(summary.get("routing_readiness_state_counts"), Mapping)
        else {}
    )
    return _surface_row(
        surface_id="routing_readiness",
        surface_name="Routing readiness from real basket evidence",
        current_level="decision_useful_capability",
        workstream="F. Routing and Sampling Calibration",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_routing_readiness_from_basket.py",
            "research/qre_real_basket_evidence_coverage.py",
        ),
        supporting_metrics={
            "basket_inventory_count": int(summary.get("basket_inventory_count") or 0),
            "ready_count": int(counts.get("ready") or 0),
            "blocked_count": int(counts.get("blocked") or 0),
            "deferred_count": int(counts.get("deferred") or 0),
            "fail_closed_count": int(counts.get("fail_closed") or 0),
        },
        blocking_factors=[
            "source_identity_blocked",
            "source_or_cache_coverage_missing",
            "oos_evidence_missing",
        ],
        why_not_higher=(
            "The surface already makes bounded routing decisions, but only two baskets are ready and "
            "the broader basket population is still dominated by deferred or blocked evidence states."
        ),
    )


def _sampling_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    counts = (
        summary.get("sampling_readiness_state_counts")
        if isinstance(summary.get("sampling_readiness_state_counts"), Mapping)
        else {}
    )
    return _surface_row(
        surface_id="sampling_readiness",
        surface_name="Sampling readiness from routing-ready evidence",
        current_level="decision_useful_capability",
        workstream="F. Routing and Sampling Calibration",
        primary_phase="Phase 0 - Baseline Reconciliation",
        evidence_refs=_evidence_refs(
            "research/qre_sampling_readiness_from_basket.py",
            "research/qre_routing_readiness_from_basket.py",
        ),
        supporting_metrics={
            "basket_inventory_count": int(summary.get("basket_inventory_count") or 0),
            "ready_count": int(counts.get("ready") or 0),
            "blocked_count": int(counts.get("blocked") or 0),
            "deferred_count": int(counts.get("deferred") or 0),
            "fail_closed_count": int(counts.get("fail_closed") or 0),
        },
        blocking_factors=[
            "source_identity_blocked",
            "source_or_cache_coverage_missing",
            "sampling_oos_window_unknown",
        ],
        why_not_higher=(
            "Sampling recommendations are deterministic and bounded, but they currently inherit the same "
            "coverage and OOS gaps that keep most baskets out of the ready state."
        ),
    )


def _failure_action_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    action_counts = (
        summary.get("action_counts")
        if isinstance(summary.get("action_counts"), Mapping)
        else {}
    )
    blocker_counts = (
        summary.get("blocker_counts")
        if isinstance(summary.get("blocker_counts"), Mapping)
        else {}
    )
    return _surface_row(
        surface_id="failure_action_mapping",
        surface_name="Failure-to-action mapping",
        current_level="decision_useful_capability",
        workstream="E. Actionable Failure Intelligence",
        primary_phase="Phase 2 - Failure and Funnel Understanding",
        evidence_refs=_evidence_refs(
            "research/qre_failure_action_from_basket.py",
            "research/qre_reason_records_v1.py",
        ),
        supporting_metrics={
            "actionable_count": int(summary.get("actionable_count") or 0),
            "non_actionable_count": int(summary.get("non_actionable_count") or 0),
            "distinct_action_count": len(action_counts),
            "distinct_blocker_count": len(blocker_counts),
        },
        blocking_factors=[str(code) for code in sorted(blocker_counts.keys())],
        why_not_higher=(
            "The mapping already yields one bounded next action per current blocker class, but it remains "
            "read-only advisory evidence and is not yet backed by broad campaign, replay, or repeated OOS results."
        ),
    )


def _candidate_explanations_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    actions = (
        summary.get("safe_next_action_counts")
        if isinstance(summary.get("safe_next_action_counts"), Mapping)
        else {}
    )
    return _surface_row(
        surface_id="candidate_explanation_rows",
        surface_name="Candidate explanation rows",
        current_level="decision_useful_capability",
        workstream="H. Operator-Trusted Research Observability",
        primary_phase="Phase 7 - Operator Trust",
        evidence_refs=_evidence_refs(
            "research/qre_candidate_explanation_rows.py",
            "research/qre_failure_action_from_basket.py",
            "research/qre_reason_records_v1.py",
        ),
        supporting_metrics={
            "candidate_count": int(summary.get("candidate_count") or 0),
            "safe_next_action_count": len(actions),
            "paper_blocked_count": int(summary.get("paper_blocked_count") or 0),
            "synthesis_blocked_count": int(summary.get("synthesis_blocked_count") or 0),
        },
        blocking_factors=[
            "campaign_lineage_missing",
            "grid_readiness_bridge_missing",
            "paper_readiness_not_available",
            "synthesis_not_available",
        ],
        why_not_higher=(
            "Operator explanations are readable and deterministic, but paper/synthesis remain fail-closed "
            "and the current surfaces stop at research context rather than operator-trusted final decisions."
        ),
    )


def _research_memory_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return _surface_row(
        surface_id="research_memory_coverage",
        surface_name="Research memory coverage",
        current_level="integrated_capability",
        workstream="G. Epistemological Research Memory",
        primary_phase="Phase 6 - Research Memory Maturity",
        evidence_refs=_evidence_refs(
            "research/qre_research_memory_coverage.py",
            "research/qre_reason_records_v1.py",
            "research/qre_failure_action_from_basket.py",
        ),
        supporting_metrics={
            "indexed_entry_count": int(summary.get("indexed_entry_count") or 0),
            "indexed_basket_count": int(summary.get("indexed_basket_count") or 0),
            "indexed_reason_record_count": int(summary.get("indexed_reason_record_count") or 0),
            "ready_ontology_count": int((summary.get("ontology_readiness_state_counts") or {}).get("ready") or 0),
            "unknown_ontology_count": int((summary.get("ontology_readiness_state_counts") or {}).get("unknown") or 0),
        },
        blocking_factors=[
            "ontology_scope_unknown",
            "context_only_memory_not_authority",
        ],
        why_not_higher=(
            "The repo already indexes memory across baskets, failures, and reason records, but most ontology "
            "classifications still resolve to unknown and the memory layer explicitly remains context-only."
        ),
    )


def _trusted_loop_kpis_row(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return _surface_row(
        surface_id="trusted_loop_operator_kpis",
        surface_name="Trusted-loop operator KPI projection",
        current_level="decision_useful_capability",
        workstream="H. Operator-Trusted Research Observability",
        primary_phase="Phase 7 - Operator Trust",
        evidence_refs=_evidence_refs(
            "research/qre_trusted_loop_operator_kpis.py",
            "research/qre_real_basket_diagnosis.py",
            "research/qre_real_basket_evidence_coverage.py",
            "research/qre_routing_readiness_from_basket.py",
            "research/qre_sampling_readiness_from_basket.py",
            "research/qre_reason_records_v1.py",
            "research/qre_reason_record_audit.py",
            "research/qre_failure_action_from_basket.py",
            "research/qre_candidate_explanation_rows.py",
        ),
        supporting_metrics={
            "basket_inventory_count": int(summary.get("basket_inventory_count") or 0),
            "routing_ready_count": int(summary.get("routing_ready_count") or 0),
            "sampling_ready_count": int(summary.get("sampling_ready_count") or 0),
            "reason_record_count": int(summary.get("reason_record_count") or 0),
            "reason_record_coverage_pct": float(summary.get("reason_record_coverage_pct") or 0.0),
            "source_ready_basket_pct": float(summary.get("source_ready_basket_pct") or 0.0),
            "evidence_complete_basket_pct": float(summary.get("evidence_complete_basket_pct") or 0.0),
        },
        blocking_factors=[
            "operator_trusted_candidate_not_operator_trusted",
            "evidence_complete_basket_pct_below_majority",
            "campaign_lineage_missing",
        ],
        why_not_higher=(
            "The KPI layer is decision-useful and already surfaces a trust candidate state, but it still "
            "aggregates a mostly thin basket population and does not yet meet the program's operator-trusted bar."
        ),
    )


def _behavior_thesis_row() -> dict[str, Any]:
    return _surface_row(
        surface_id="behavior_thesis_registry",
        surface_name="Behavior thesis registry",
        current_level="scaffold",
        workstream="D. Behavior Thesis Engine",
        primary_phase="Phase 4 - Behavior Thesis Maturity",
        evidence_refs=_evidence_refs(
            "research/production_discovery_catalog.py",
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
        ),
        supporting_metrics={
            "preset_hypothesis_pairs_present": 1,
        },
        blocking_factors=[
            "no_deterministic_behavior_thesis_registry",
            "no_falsification_plan_registry",
            "no_null_control_registry",
        ],
        why_not_higher=(
            "The production discovery catalog already names hypotheses and behavior families, but the repo does not "
            "yet have a dedicated thesis registry with explicit mechanism, falsification, and preregistered test plans."
        ),
    )


def _campaign_closure_row() -> dict[str, Any]:
    return _surface_row(
        surface_id="preregistered_campaign_closure",
        surface_name="Preregistered campaign and replay closure",
        current_level="populated_working_capability",
        workstream="I. Broad Preregistered Campaign",
        primary_phase="Phase 8 - Broad Campaign Execution",
        evidence_refs=_evidence_refs(
            "research/qre_multiwindow_evidence_closure.py",
            "research/qre_hypothesis_disposition_memory.py",
            "tests/unit/test_qre_hypothesis_disposition_memory.py",
        ),
        supporting_metrics={
            "working_closure_engine_present": 1,
        },
        blocking_factors=[
            "no_current_preregistered_campaign_artifact",
            "no_broad_campaign_execution_currently_materialized",
        ],
        why_not_higher=(
            "The repository already contains deterministic closure and disposition-memory scaffolds for preregistered "
            "campaign evidence, but no current broad campaign artifact has been executed through them."
        ),
    )


def _contradiction_decay_row() -> dict[str, Any]:
    return _surface_row(
        surface_id="contradiction_and_decay",
        surface_name="Contradiction visibility and evidence decay",
        current_level="scaffold",
        workstream="G. Epistemological Research Memory",
        primary_phase="Phase 6 - Research Memory Maturity",
        evidence_refs=_evidence_refs(
            "research/qre_contradiction_staleness_intelligence.py",
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
        ),
        supporting_metrics={
            "current_repo_backed_operator_surface_count": 0,
        },
        blocking_factors=[
            "no_current_repo_backed_contradiction_graph_output",
            "no_current_repo_backed_evidence_decay_output",
        ],
        why_not_higher=(
            "The repo contains relevant scaffolds, but the current state inspection does not yet expose a mature "
            "operator-facing contradiction graph or explicit evidence-decay decision surface."
        ),
    )


def _independent_oos_row() -> dict[str, Any]:
    return _surface_row(
        surface_id="independent_oos_repetition",
        surface_name="Repeated independent OOS closure",
        current_level="scaffold",
        workstream="J. Controlled Learning and Replay",
        primary_phase="Phase 9 - Controlled Recalibration and Replay",
        evidence_refs=_evidence_refs(
            "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md",
            "research/qre_multiwindow_evidence_closure.py",
        ),
        supporting_metrics={
            "independent_oos_runs_materialized": 0,
        },
        blocking_factors=[
            "no_independent_oos_artifacts_currently_materialized",
            "campaign_execution_not_completed",
        ],
        why_not_higher=(
            "The doctrine and closure scaffolds are present, but no current repository artifact demonstrates repeated "
            "independent OOS evidence under the ADE-QRE-017 program."
        ),
    )


def build_maturity_matrix(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    audit_gap_plan = _research_module("research.qre_audit_gap_closure_plan")
    evidence_coverage = _research_module("research.qre_real_basket_evidence_coverage")
    reason_records_v1 = _research_module("research.qre_reason_records_v1")
    reason_record_audit = _research_module("research.qre_reason_record_audit")
    routing_readiness = _research_module("research.qre_routing_readiness_from_basket")
    sampling_readiness = _research_module("research.qre_sampling_readiness_from_basket")
    failure_actions = _research_module("research.qre_failure_action_from_basket")
    candidate_explanations = _research_module("research.qre_candidate_explanation_rows")
    research_memory = _research_module("research.qre_research_memory_coverage")
    trusted_loop_kpis = _research_module("research.qre_trusted_loop_operator_kpis")

    plan = audit_gap_plan.build_audit_gap_closure_plan()
    coverage_report = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reasons = reason_records_v1.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_audit = reason_record_audit.build_reason_record_audit(
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
    actions = failure_actions.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    explanations = candidate_explanations.build_candidate_explanation_rows(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    memory = research_memory.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    kpis = trusted_loop_kpis.build_trusted_loop_operator_kpis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    rows = [
        _planning_row(plan),
        _evidence_coverage_row(coverage_report),
        _reason_records_row(reasons),
        _reason_record_audit_row(reason_audit),
        _routing_row(routing),
        _sampling_row(sampling),
        _failure_action_row(actions),
        _candidate_explanations_row(explanations),
        _research_memory_row(memory),
        _trusted_loop_kpis_row(kpis),
        _behavior_thesis_row(),
        _campaign_closure_row(),
        _contradiction_decay_row(),
        _independent_oos_row(),
    ]

    level_counts = Counter(str(row["current_level"]) for row in rows)
    blocker_counts: Counter[str] = Counter()
    for row in rows:
        blocker_counts.update(str(code) for code in row.get("blocking_factors") or [])

    highest_present = next(
        (level for level in reversed(LEVELS) if level_counts.get(level, 0) > 0),
        "scaffold",
    )
    summary = {
        "surface_count": len(rows),
        "current_level_counts": {level: int(level_counts.get(level, 0)) for level in LEVELS},
        "top_blockers": _top_blockers(blocker_counts),
        "highest_level_present": highest_present,
        "operator_trusted_surface_count": int(level_counts.get("operator_trusted_capability", 0)),
        "evidence_authoritative_surface_count": int(
            level_counts.get("evidence_authoritative_capability", 0)
        ),
        "planning_gap_scaffold_count": int((plan.get("current_maturity") or {}).get("SCAFFOLD") or 0),
        "planning_gap_working_count": int((plan.get("current_maturity") or {}).get("WORKING_CAPABILITY") or 0),
        "overall_baseline": (
            "mixed_decision_useful_pockets_not_operator_trusted"
            if highest_present in {"decision_useful_capability", "operator_trusted_capability"}
            else "pre_decision_useful_baseline"
        ),
        "operator_summary": (
            "Current QRE maturity is uneven: the repo already has integrated and decision-useful read-only "
            "surfaces for basket diagnosis, readiness, failure actions, explanations, memory, and KPI summaries, "
            "but behavior-thesis discipline, contradiction/decay visibility, broad preregistered campaign evidence, "
            "and repeated independent OOS closure remain below operator-trusted maturity."
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": _utcnow(),
        "max_candidates": max_candidates,
        "summary": summary,
        "surfaces": rows,
        "supporting_reports": {
            "audit_gap_closure_plan": {
                "report_kind": plan.get("report_kind"),
                "current_maturity": plan.get("current_maturity"),
            },
            "trusted_loop_operator_kpis": kpis.get("summary"),
            "reason_records_v1": reasons.get("meta"),
            "reason_record_audit": reason_audit.get("summary"),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_queue": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "evidence_authority_inferred_from_file_existence": False,
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("surfaces") if isinstance(report.get("surfaces"), list) else []
    level_counts = summary.get("current_level_counts") if isinstance(summary.get("current_level_counts"), Mapping) else {}
    level_table = _table(
        ["Level", "Count"],
        [[level, str(level_counts.get(level) or 0)] for level in LEVELS],
    )
    blocker_table = _table(
        ["Blocker", "Count"],
        [
            [str(item.get("blocker_code") or ""), str(item.get("count") or 0)]
            for item in summary.get("top_blockers") or []
        ],
    )
    surface_table = _table(
        ["Surface", "Level", "Workstream", "Phase", "Key metrics", "Why not higher"],
        [
            [
                str(row.get("surface_name") or ""),
                str(row.get("current_level") or ""),
                str(row.get("workstream") or ""),
                str(row.get("primary_phase") or ""),
                ", ".join(
                    f"{key}={value}"
                    for key, value in list((row.get("supporting_metrics") or {}).items())[:4]
                ),
                str(row.get("why_not_higher") or ""),
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    evidence_lines = [
        f"- `{row.get('surface_id')}`: "
        + ", ".join(f"`{ref}`" for ref in (row.get("evidence_refs") or [])[:6])
        for row in rows
        if isinstance(row, Mapping)
    ]
    return "\n".join(
        [
            "# QRE Trusted Research Maturity Matrix",
            "",
            "## 1. Summary",
            f"- {summary.get('operator_summary') or ''}",
            f"- overall_baseline: `{summary.get('overall_baseline') or ''}`",
            f"- highest_level_present: `{summary.get('highest_level_present') or ''}`",
            f"- operator_trusted_surface_count: `{summary.get('operator_trusted_surface_count') or 0}`",
            f"- evidence_authoritative_surface_count: `{summary.get('evidence_authoritative_surface_count') or 0}`",
            f"- planning_gap_scaffold_count: `{summary.get('planning_gap_scaffold_count') or 0}`",
            f"- planning_gap_working_count: `{summary.get('planning_gap_working_count') or 0}`",
            "",
            "## 2. Level counts",
            level_table,
            "",
            "## 3. Top blockers",
            blocker_table,
            "",
            "## 4. Surface matrix",
            surface_table,
            "",
            "## 5. Evidence refs",
            *evidence_lines,
            "",
            "## 6. Safety",
            "- This report is read-only.",
            "- Evidence-authoritative status is never inferred from file existence alone.",
            "- Paper, shadow, live, broker, risk, execution, and capital-allocation behavior remain out of scope.",
        ]
    )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    doc_path: Path = DOC_PATH,
) -> dict[str, str]:
    base = repo_root / output_dir
    doc = repo_root / doc_path
    base.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    for target in (latest, doc):
        _validate_write_target(target)
    payload = json.dumps(report, indent=2, sort_keys=True)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_doc = doc.with_suffix(doc.suffix + ".tmp")
    tmp_doc.write_text(render_markdown(report) + "\n", encoding="utf-8")
    os.replace(tmp_doc, doc)
    return {
        "latest": _rel(latest, repo_root=repo_root),
        "doc": _rel(doc, repo_root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_trusted_research_maturity_matrix",
        description="Build a read-only QRE trusted research maturity matrix.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_maturity_matrix(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
