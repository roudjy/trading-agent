from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_evidence_density_inventory"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_evidence_density_inventory")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_evidence_density_inventory.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_evidence_density_inventory/",
    "docs/governance/qre_evidence_density_inventory.md",
)
POPULATION_STATES: Final[tuple[str, ...]] = (
    "missing",
    "thin",
    "partial",
    "complete",
    "blocked",
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


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            "qre_evidence_density_inventory: refusing write outside allowlist: "
            f"{path!r}"
        )


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _status_from_ratio(
    numerator: int,
    denominator: int,
    *,
    blocked: bool = False,
) -> str:
    if blocked:
        return "blocked"
    if denominator <= 0 or numerator <= 0:
        return "missing"
    ratio = numerator / denominator
    if ratio >= 0.85:
        return "complete"
    if ratio >= 0.4:
        return "partial"
    return "thin"


def _bounded_strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:160])
    return out[:16]


def _coverage_rows(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = report.get("rows")
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = report.get("summary")
    return payload if isinstance(payload, Mapping) else {}


def _evidence_class(
    *,
    evidence_class_id: str,
    title: str,
    producers: Sequence[str],
    consumers: Sequence[str],
    population_state: str,
    fail_closed: bool,
    blocker_codes: Sequence[str],
    artifact_paths: Sequence[str],
    metrics: Mapping[str, Any],
    why: str,
) -> dict[str, Any]:
    if population_state not in POPULATION_STATES:
        raise ValueError((evidence_class_id, population_state))
    return {
        "evidence_class_id": evidence_class_id,
        "title": title,
        "producers": list(producers),
        "consumers": list(consumers),
        "population_state": population_state,
        "fail_closed": fail_closed,
        "blocker_codes": list(blocker_codes),
        "artifact_paths": list(artifact_paths),
        "metrics": dict(metrics),
        "why": why,
    }


def build_evidence_density_inventory(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    coverage_mod = _research_module("research.qre_real_basket_evidence_coverage")
    reason_records_mod = _research_module("research.qre_reason_records_v1")
    reason_audit_mod = _research_module("research.qre_reason_record_audit")
    routing_mod = _research_module("research.qre_routing_readiness_from_basket")
    sampling_mod = _research_module("research.qre_sampling_readiness_from_basket")
    failure_mod = _research_module("research.qre_failure_action_from_basket")
    explanations_mod = _research_module("research.qre_candidate_explanation_rows")
    memory_mod = _research_module("research.qre_research_memory_coverage")
    kpis_mod = _research_module("research.qre_trusted_loop_operator_kpis")

    coverage = coverage_mod.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_records = reason_records_mod.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_audit = reason_audit_mod.build_reason_record_audit(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    routing = routing_mod.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling = sampling_mod.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure = failure_mod.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    explanations = explanations_mod.build_candidate_explanation_rows(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    memory = memory_mod.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    kpis = kpis_mod.build_trusted_loop_operator_kpis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    coverage_rows = _coverage_rows(coverage)
    basket_count = len(coverage_rows)
    missing_taxonomy = _summary(coverage).get("missing_evidence_taxonomy_counts")
    taxonomy = missing_taxonomy if isinstance(missing_taxonomy, Mapping) else {}
    coverage_status_counts = _summary(coverage).get("evidence_completeness_status_counts")
    completeness_counts = (
        coverage_status_counts if isinstance(coverage_status_counts, Mapping) else {}
    )
    routing_summary = _summary(routing)
    sampling_summary = _summary(sampling)
    reason_meta = reason_records.get("meta")
    reason_meta = reason_meta if isinstance(reason_meta, Mapping) else {}
    reason_audit_summary = _summary(reason_audit)
    failure_summary = _summary(failure)
    explanations_summary = _summary(explanations)
    memory_summary = _summary(memory)
    kpi_summary = _summary(kpis)

    source_identity_ready = sum(
        1 for row in coverage_rows if str(row.get("provider_symbol_status") or "") == "verified"
    )
    source_quality_ready = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("source_quality_ready"))
    )
    cache_ready = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("cache_ready"))
    )
    screening_present = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("screening_evidence_present"))
    )
    oos_known = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("oos_evidence_known"))
    )
    campaign_lineage = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("campaign_lineage_present"))
    )
    candidate_lineage = sum(
        1
        for row in coverage_rows
        if bool((row.get("evidence_presence") or {}).get("candidate_lineage_present"))
    )

    evidence_classes = [
        _evidence_class(
            evidence_class_id="source_identity",
            title="Source identity verification",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_routing_readiness_from_basket",
                "research.qre_sampling_readiness_from_basket",
                "ADE-QRE-017J",
            ),
            population_state=_status_from_ratio(
                source_identity_ready,
                basket_count,
                blocked=int(taxonomy.get("source_identity_blocked") or 0) > 0,
            ),
            fail_closed=True,
            blocker_codes=("source_identity_blocked",),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "verified_basket_count": source_identity_ready,
                "basket_inventory_count": basket_count,
                "verified_basket_pct": _pct(source_identity_ready, basket_count),
            },
            why="Provider symbol verification is required before downstream evidence can be trusted.",
        ),
        _evidence_class(
            evidence_class_id="source_quality",
            title="Source quality rows",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_candidate_explanation_rows",
                "research.qre_trusted_loop_operator_kpis",
                "ADE-QRE-017J",
            ),
            population_state=_status_from_ratio(source_quality_ready, basket_count),
            fail_closed=True,
            blocker_codes=("source_quality_rows_missing", "source_quality_not_ready"),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "ready_basket_count": source_quality_ready,
                "basket_inventory_count": basket_count,
                "ready_basket_pct": _pct(source_quality_ready, basket_count),
            },
            why="Quality rows are the repository-backed signal that input data is inspectable rather than assumed.",
        ),
        _evidence_class(
            evidence_class_id="cache_coverage",
            title="Cache coverage evidence",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_routing_readiness_from_basket",
                "research.qre_sampling_readiness_from_basket",
                "ADE-QRE-017I",
            ),
            population_state=_status_from_ratio(cache_ready, basket_count),
            fail_closed=True,
            blocker_codes=("cache_coverage_missing", "cache_coverage_not_ready"),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "ready_basket_count": cache_ready,
                "basket_inventory_count": basket_count,
                "ready_basket_pct": _pct(cache_ready, basket_count),
            },
            why="Cache readiness is the current repository-native evidence that data supply is reproducible.",
        ),
        _evidence_class(
            evidence_class_id="screening_evidence",
            title="Screening-stage evidence",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_candidate_explanation_rows",
                "ADE-QRE-017F",
                "ADE-QRE-017X",
            ),
            population_state=_status_from_ratio(screening_present, basket_count),
            fail_closed=True,
            blocker_codes=("screening_evidence_missing",),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "present_basket_count": screening_present,
                "basket_inventory_count": basket_count,
                "present_basket_pct": _pct(screening_present, basket_count),
            },
            why="Without screening evidence the repository cannot distinguish absence of edge from absence of evaluation.",
        ),
        _evidence_class(
            evidence_class_id="validation_oos_evidence",
            title="Validation and OOS evidence",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_candidate_explanation_rows",
                "research.qre_trusted_loop_operator_kpis",
                "ADE-QRE-017AC",
            ),
            population_state=_status_from_ratio(oos_known, basket_count),
            fail_closed=True,
            blocker_codes=(
                "oos_evidence_missing",
                "oos_evidence_unknown",
                "no_oos_evidence",
                "insufficient_oos_evidence",
            ),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "known_basket_count": oos_known,
                "basket_inventory_count": basket_count,
                "known_basket_pct": _pct(oos_known, basket_count),
                "sufficient_oos_rows_total": int(
                    _summary(coverage).get("sufficient_oos_evidence_rows_total") or 0
                ),
            },
            why="OOS evidence is a hard trust gate for later operator decisions and replay steps.",
        ),
        _evidence_class(
            evidence_class_id="campaign_lineage",
            title="Campaign lineage evidence",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_candidate_explanation_rows",
                "ADE-QRE-017S",
                "ADE-QRE-017X",
            ),
            population_state=_status_from_ratio(
                campaign_lineage,
                basket_count,
                blocked=int(taxonomy.get("campaign_lineage_missing") or 0) > 0,
            ),
            fail_closed=True,
            blocker_codes=("campaign_lineage_missing",),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "present_basket_count": campaign_lineage,
                "basket_inventory_count": basket_count,
                "present_basket_pct": _pct(campaign_lineage, basket_count),
            },
            why="Campaign lineage is required to connect hypotheses, windows, and later campaign governance.",
        ),
        _evidence_class(
            evidence_class_id="candidate_lineage",
            title="Candidate lineage evidence",
            producers=("research.qre_real_basket_evidence_coverage",),
            consumers=(
                "research.qre_research_memory_coverage",
                "ADE-QRE-017S",
            ),
            population_state=_status_from_ratio(candidate_lineage, basket_count),
            fail_closed=True,
            blocker_codes=("candidate_lineage_missing",),
            artifact_paths=("logs/qre_real_basket_evidence_coverage/latest.json",),
            metrics={
                "present_basket_count": candidate_lineage,
                "basket_inventory_count": basket_count,
                "present_basket_pct": _pct(candidate_lineage, basket_count),
            },
            why="Candidate lineage is the minimal trace linking a basket diagnosis back to repository candidate identities.",
        ),
        _evidence_class(
            evidence_class_id="reason_records",
            title="Reason-record coverage",
            producers=("research.qre_reason_records_v1", "research.qre_reason_record_audit"),
            consumers=(
                "research.qre_candidate_explanation_rows",
                "research.qre_research_memory_coverage",
                "ADE-QRE-017C",
            ),
            population_state=_status_from_ratio(
                int(reason_audit_summary.get("subjects_with_evidence_refs") or 0),
                int(reason_audit_summary.get("expected_subject_count") or 0),
            ),
            fail_closed=True,
            blocker_codes=("reason_record_coverage_incomplete",),
            artifact_paths=(
                "logs/qre_reason_records/latest.meta.json",
                "logs/qre_reason_record_audit/latest.json",
            ),
            metrics={
                "record_count": int(reason_meta.get("record_count") or 0),
                "coverage_pct": float(reason_audit_summary.get("reason_record_coverage_pct") or 0.0),
                "skipped_missing_refs_count": int(reason_meta.get("skipped_missing_refs_count") or 0),
            },
            why="Reason records are the durable explanation layer connecting evidence to later operator-facing decisions.",
        ),
        _evidence_class(
            evidence_class_id="routing_readiness",
            title="Routing readiness evidence",
            producers=("research.qre_routing_readiness_from_basket",),
            consumers=("research.qre_trusted_loop_operator_kpis", "ADE-QRE-017D", "ADE-QRE-017P"),
            population_state=_status_from_ratio(
                int(routing_summary.get("routing_ready_count") or 0),
                basket_count,
            ),
            fail_closed=True,
            blocker_codes=("routing_not_ready",),
            artifact_paths=("logs/qre_routing_readiness_from_basket/latest.json",),
            metrics={
                "ready_count": int(routing_summary.get("routing_ready_count") or 0),
                "blocked_count": int(routing_summary.get("routing_blocked_count") or 0),
                "deferred_count": int(routing_summary.get("routing_deferred_count") or 0),
            },
            why="Routing readiness is already materialized; this inventory tracks how much of the basket set actually reaches that state.",
        ),
        _evidence_class(
            evidence_class_id="sampling_readiness",
            title="Sampling readiness evidence",
            producers=("research.qre_sampling_readiness_from_basket",),
            consumers=("research.qre_trusted_loop_operator_kpis", "ADE-QRE-017D", "ADE-QRE-017Q"),
            population_state=_status_from_ratio(
                int(sampling_summary.get("sampling_ready_count") or 0),
                basket_count,
            ),
            fail_closed=True,
            blocker_codes=("sampling_not_ready",),
            artifact_paths=("logs/qre_sampling_readiness_from_basket/latest.json",),
            metrics={
                "ready_count": int(sampling_summary.get("sampling_ready_count") or 0),
                "blocked_count": int(sampling_summary.get("sampling_blocked_count") or 0),
                "deferred_count": int(sampling_summary.get("sampling_deferred_count") or 0),
            },
            why="Sampling readiness is a distinct evidence class because basket availability does not imply sample adequacy.",
        ),
        _evidence_class(
            evidence_class_id="failure_action_mapping",
            title="Actionable failure evidence",
            producers=("research.qre_failure_action_from_basket",),
            consumers=("research.qre_candidate_explanation_rows", "ADE-QRE-017G", "ADE-QRE-017H"),
            population_state=_status_from_ratio(
                int(failure_summary.get("actionable_count") or 0),
                int(failure_summary.get("basket_inventory_count") or 0),
            ),
            fail_closed=False,
            blocker_codes=("non_actionable_failure",),
            artifact_paths=("logs/qre_failure_action_from_basket/latest.json",),
            metrics={
                "actionable_count": int(failure_summary.get("actionable_count") or 0),
                "non_actionable_count": int(failure_summary.get("non_actionable_count") or 0),
            },
            why="Failure mapping is evidence-bearing only when a basket receives a bounded action grounded in current artifacts.",
        ),
        _evidence_class(
            evidence_class_id="candidate_explanations",
            title="Operator explanation rows",
            producers=("research.qre_candidate_explanation_rows",),
            consumers=("research.qre_trusted_loop_operator_kpis", "ADE-QRE-017U", "ADE-QRE-017V"),
            population_state=_status_from_ratio(
                int(explanations_summary.get("candidate_count") or 0)
                - int(explanations_summary.get("paper_blocked_count") or 0),
                int(explanations_summary.get("candidate_count") or 0),
            ),
            fail_closed=True,
            blocker_codes=("paper_blocked", "synthesis_blocked"),
            artifact_paths=("logs/qre_candidate_explanation_rows/latest.json",),
            metrics={
                "candidate_count": int(explanations_summary.get("candidate_count") or 0),
                "paper_blocked_count": int(explanations_summary.get("paper_blocked_count") or 0),
                "synthesis_blocked_count": int(
                    explanations_summary.get("synthesis_blocked_count") or 0
                ),
            },
            why="Candidate explanations are the current read-only surface where evidence is translated into operator-facing decisions.",
        ),
        _evidence_class(
            evidence_class_id="research_memory",
            title="Research-memory index coverage",
            producers=("research.qre_research_memory_coverage",),
            consumers=("ADE-QRE-017N", "ADE-QRE-017S"),
            population_state=_status_from_ratio(
                int(memory_summary.get("indexed_entry_count") or 0),
                max(
                    int(memory_summary.get("indexed_basket_count") or 0)
                    + int(memory_summary.get("indexed_failure_action_count") or 0)
                    + int(memory_summary.get("indexed_reason_record_count") or 0),
                    1,
                ),
            ),
            fail_closed=False,
            blocker_codes=("memory_index_missing",),
            artifact_paths=("logs/qre_research_memory_coverage/latest.json",),
            metrics={
                "indexed_entry_count": int(memory_summary.get("indexed_entry_count") or 0),
                "indexed_basket_count": int(memory_summary.get("indexed_basket_count") or 0),
                "indexed_reason_record_count": int(
                    memory_summary.get("indexed_reason_record_count") or 0
                ),
            },
            why="Research memory remains context-only, but the inventory still needs to show whether prior failures are retrievable.",
        ),
        _evidence_class(
            evidence_class_id="trusted_loop_kpis",
            title="Trusted-loop KPI projection",
            producers=("research.qre_trusted_loop_operator_kpis",),
            consumers=("ADE-QRE-017E", "ADE-QRE-017U", "ADE-QRE-017AD"),
            population_state=_status_from_ratio(
                int(kpi_summary.get("basket_inventory_count") or 0),
                basket_count,
                blocked=str(kpi_summary.get("trusted_loop_maturity_state") or "") == "scaffold",
            ),
            fail_closed=False,
            blocker_codes=("operator_kpi_projection_incomplete",),
            artifact_paths=("logs/qre_trusted_loop_operator_kpis/latest.json",),
            metrics={
                "basket_inventory_count": int(kpi_summary.get("basket_inventory_count") or 0),
                "reason_record_coverage_pct": float(
                    kpi_summary.get("reason_record_coverage_pct") or 0.0
                ),
                "source_ready_basket_pct": float(kpi_summary.get("source_ready_basket_pct") or 0.0),
                "evidence_complete_basket_pct": float(
                    kpi_summary.get("evidence_complete_basket_pct") or 0.0
                ),
            },
            why="The KPI surface is itself downstream evidence; its completeness depends on the underlying evidence classes being populated.",
        ),
    ]

    state_counts = Counter(str(row["population_state"]) for row in evidence_classes)
    blocker_counts = Counter(
        blocker for row in evidence_classes for blocker in row["blocker_codes"] if row["population_state"] != "complete"
    )
    fail_closed_count = sum(1 for row in evidence_classes if bool(row["fail_closed"]))
    complete_count = int(state_counts.get("complete") or 0)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": _utcnow(),
        "population_states": list(POPULATION_STATES),
        "evidence_classes": evidence_classes,
        "summary": {
            "evidence_class_count": len(evidence_classes),
            "population_state_counts": dict(sorted(state_counts.items())),
            "complete_count": complete_count,
            "fail_closed_evidence_class_count": fail_closed_count,
            "top_blocker_codes": [
                {"blocker_code": code, "count": count}
                for code, count in blocker_counts.most_common(10)
            ],
            "coverage_completeness_counts": dict(sorted(completeness_counts.items())),
            "final_recommendation": (
                "evidence_density_inventory_ready" if len(evidence_classes) >= 10 else "inventory_incomplete"
            ),
            "operator_summary": (
                "Evidence-density inventory enumerates current repository-backed evidence classes, "
                "their producers, consumers, population state, and fail-closed blockers. "
                "It remains read-only and does not authorize runtime activation."
            ),
        },
        "supporting_reports": {
            "coverage": _summary(coverage),
            "reason_records": reason_meta,
            "reason_record_audit": reason_audit_summary,
            "routing": routing_summary,
            "sampling": sampling_summary,
            "failure_action": failure_summary,
            "candidate_explanations": explanations_summary,
            "research_memory": memory_summary,
            "trusted_loop_kpis": kpi_summary,
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "strategy_synthesis_enabled": False,
        },
        "write_targets": {
            "latest": "logs/qre_evidence_density_inventory/latest.json",
            "doc": "docs/governance/qre_evidence_density_inventory.md",
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    rows = report.get("evidence_classes")
    evidence_classes = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    summary = _summary(report)
    table_rows = [
        (
            str(row.get("evidence_class_id") or ""),
            str(row.get("population_state") or ""),
            "yes" if bool(row.get("fail_closed")) else "no",
            str(len(_bounded_strings(row.get("producers")))),
            str(len(_bounded_strings(row.get("consumers")))),
            ", ".join(_bounded_strings(row.get("blocker_codes"))) or "-",
        )
        for row in evidence_classes
    ]
    return "\n".join(
        [
            "# QRE Evidence Density Inventory",
            "",
            f"- generated_at_utc: `{report.get('generated_at_utc')}`",
            f"- evidence_class_count: `{summary.get('evidence_class_count')}`",
            f"- final_recommendation: `{summary.get('final_recommendation')}`",
            "",
            "## Inventory",
            "",
            _table(
                ("evidence_class", "state", "fail_closed", "producers", "consumers", "blockers"),
                table_rows,
            ),
            "",
            "## State Counts",
            "",
            _table(
                ("population_state", "count"),
                [
                    (str(key), str(value))
                    for key, value in sorted(
                        (_summary(report).get("population_state_counts") or {}).items()
                    )
                ],
            ),
            "",
            "## Top Blockers",
            "",
            _table(
                ("blocker_code", "count"),
                [
                    (str(row.get("blocker_code") or ""), str(row.get("count") or "0"))
                    for row in (summary.get("top_blocker_codes") or [])
                    if isinstance(row, Mapping)
                ]
                or [("-", "0")],
            ),
        ]
    )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    doc_path: Path = DOC_PATH,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    doc_path = Path(doc_path)
    latest_path = output_dir / LATEST_NAME
    _validate_write_target(latest_path)
    _validate_write_target(doc_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    return {
        "latest": latest_path.as_posix(),
        "doc": doc_path.as_posix(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_evidence_density_inventory",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=15)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_evidence_density_inventory(max_candidates=args.max_candidates)
    if args.write:
        payload = {
            "report": report,
            "paths": write_outputs(report),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
