from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_suppression_efficacy"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017r-2026-06-27"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_suppression_efficacy")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_suppression_efficacy.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_suppression_efficacy/",
    "docs/governance/qre_suppression_efficacy.md",
)
DEFAULT_ROUTER_PATH: Final[Path] = Path("logs/qre_research_cycle_router/latest.json")
DEFAULT_DEDUP_PATH: Final[Path] = Path("logs/qre_experiment_dedup_novelty_enforcement/latest.json")
DEFAULT_PRIOR_FAILURE_PATH: Final[Path] = Path("logs/qre_prior_failure_retrieval/latest.json")
DEFAULT_ROUTING_BASELINE_PATH: Final[Path] = Path("logs/qre_routing_baseline_comparison/latest.json")
DEFAULT_SAMPLING_BASELINE_PATH: Final[Path] = Path("logs/qre_sampling_baseline_comparison/latest.json")
DEFAULT_RUN_CANDIDATES_PATH: Final[Path] = Path("research/run_candidates_latest.v1.json")
DEFAULT_RUN_MANIFEST_PATH: Final[Path] = Path("research/run_manifest_latest.v1.json")
DEFAULT_CAMPAIGN_REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
DEFAULT_THROUGHPUT_PATH: Final[Path] = Path(
    "logs/qre_campaign_throughput_bottleneck_intelligence/latest.json"
)
METRIC_STATUS_VALUES: Final[frozenset[str]] = frozenset(
    {"measured", "observed", "insufficient_evidence", "missing"}
)
FINAL_RECOMMENDATION_VALUES: Final[frozenset[str]] = frozenset(
    {
        "suppression_efficacy_measured",
        "suppression_efficacy_insufficient_baseline",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_suppression_efficacy: refusing write outside allowlist: {path!r}"
        )


def _source_status(payload: dict[str, Any] | None, *, required_field: str) -> dict[str, Any]:
    if payload is None:
        return {"status": "missing", "required_field": required_field, "fails_closed": True}
    if required_field not in payload:
        return {"status": "invalid", "required_field": required_field, "fails_closed": True}
    return {"status": "ready", "required_field": required_field, "fails_closed": False}


def _metric(
    metric_id: str,
    *,
    status: str,
    value: int | float | None,
    unit: str,
    rationale: str,
    provenance_refs: list[str],
) -> dict[str, Any]:
    if status not in METRIC_STATUS_VALUES:
        raise ValueError(f"invalid metric status for {metric_id}: {status}")
    return {
        "metric_id": metric_id,
        "status": status,
        "value": value,
        "unit": unit,
        "rationale": rationale,
        "provenance_refs": list(dict.fromkeys(provenance_refs)),
    }


def _find_metric(rows: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    return next(row for row in rows if _text(row.get("metric_id")) == metric_id)


def validate_metric(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if _text(row.get("metric_id")) == "":
        reasons.append("missing_metric_id")
    if _text(row.get("status")) not in METRIC_STATUS_VALUES:
        reasons.append("invalid_status")
    if not isinstance(row.get("provenance_refs"), list) or not row.get("provenance_refs"):
        reasons.append("missing_provenance_refs")
    if row.get("status") in {"measured", "observed"} and row.get("value") is None:
        reasons.append("missing_value_for_observed_metric")
    return {"valid": not reasons, "rejection_reasons": reasons}


def build_suppression_efficacy(
    *,
    repo_root: Path | None = None,
    router_report: dict[str, Any] | None = None,
    dedup_report: dict[str, Any] | None = None,
    prior_failure_report: dict[str, Any] | None = None,
    routing_baseline_report: dict[str, Any] | None = None,
    sampling_baseline_report: dict[str, Any] | None = None,
    run_candidates_report: dict[str, Any] | None = None,
    run_manifest_report: dict[str, Any] | None = None,
    campaign_registry_report: dict[str, Any] | None = None,
    throughput_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    router_report = router_report or _read_json(root / DEFAULT_ROUTER_PATH)
    dedup_report = dedup_report or _read_json(root / DEFAULT_DEDUP_PATH)
    prior_failure_report = prior_failure_report or _read_json(root / DEFAULT_PRIOR_FAILURE_PATH)
    routing_baseline_report = routing_baseline_report or _read_json(root / DEFAULT_ROUTING_BASELINE_PATH)
    sampling_baseline_report = sampling_baseline_report or _read_json(root / DEFAULT_SAMPLING_BASELINE_PATH)
    run_candidates_report = run_candidates_report or _read_json(root / DEFAULT_RUN_CANDIDATES_PATH)
    run_manifest_report = run_manifest_report or _read_json(root / DEFAULT_RUN_MANIFEST_PATH)
    campaign_registry_report = campaign_registry_report or _read_json(root / DEFAULT_CAMPAIGN_REGISTRY_PATH)
    throughput_report = throughput_report or _read_json(root / DEFAULT_THROUGHPUT_PATH)

    source_status = {
        "research_cycle_router": _source_status(router_report, required_field="suppressed_scopes"),
        "experiment_dedup_novelty_enforcement": _source_status(dedup_report, required_field="duplicate_rows"),
        "prior_failure_retrieval": _source_status(prior_failure_report, required_field="rows"),
        "routing_baseline_comparison": _source_status(routing_baseline_report, required_field="baselines"),
        "sampling_baseline_comparison": _source_status(sampling_baseline_report, required_field="baselines"),
        "run_candidates": _source_status(run_candidates_report, required_field="summary"),
        "run_manifest": _source_status(run_manifest_report, required_field="status"),
        "campaign_registry": _source_status(campaign_registry_report, required_field="campaigns"),
        "campaign_throughput_bottleneck_intelligence": _source_status(
            throughput_report, required_field="bottlenecks"
        ),
    }

    suppressed_scopes = _read_rows(router_report, "suppressed_scopes")
    duplicate_rows = _read_rows(dedup_report, "duplicate_rows")
    eligible_directions = _read_rows(router_report, "eligible_directions")
    prior_rows = _read_rows(prior_failure_report, "rows")
    campaigns = (
        list((campaign_registry_report or {}).get("campaigns", {}).values())
        if isinstance((campaign_registry_report or {}).get("campaigns"), dict)
        else []
    )
    current_routing = next(
        (
            row
            for row in _read_rows(routing_baseline_report, "baselines")
            if _text(row.get("baseline_id")) == "current_routing_score"
        ),
        {},
    )
    current_sampling = next(
        (
            row
            for row in _read_rows(sampling_baseline_report, "baselines")
            if _text(row.get("baseline_id")) == "current_sampling_score"
        ),
        {},
    )
    run_candidates_summary = (
        dict(run_candidates_report.get("summary") or {})
        if isinstance(run_candidates_report, dict)
        else {}
    )
    throughput_summary = (
        dict(throughput_report.get("summary") or {})
        if isinstance(throughput_report, dict)
        else {}
    )

    exact_suppressed = [
        row for row in suppressed_scopes if _text(row.get("scope_kind")) == "exact_failed_scope"
    ]
    materially_equivalent = [
        row
        for row in suppressed_scopes
        if _text(row.get("scope_kind")) == "materially_equivalent_retry"
    ]
    active_duplicate_fingerprint = [
        row
        for row in duplicate_rows
        if _text(row.get("duplicate_class")) == "active_duplicate_fingerprint"
    ]
    active_scope_conflict = [
        row for row in duplicate_rows if _text(row.get("duplicate_class")) == "active_scope_conflict"
    ]
    duplicate_pressure = [
        row
        for row in duplicate_rows
        if _text(row.get("duplicate_class")) == "duplicate_low_value_run_pressure"
    ]
    duplicate_candidate_count = int(run_candidates_summary.get("duplicates_removed") or 0)
    repeated_rejected_scope_count = len(exact_suppressed) + len(materially_equivalent)
    dead_zone_context_count = sum(int(row.get("dead_zone_count") or 0) for row in prior_rows)
    evaluation_avoidance_count = repeated_rejected_scope_count
    comparison_population_count = len(eligible_directions) + repeated_rejected_scope_count
    coverage_ratio = (
        round(
            sum(
                1
                for row in (
                    suppressed_scopes
                    + duplicate_rows
                    + eligible_directions
                    + prior_rows
                )
                if isinstance(row, dict)
            )
            / max(
                1,
                len(suppressed_scopes)
                + len(duplicate_rows)
                + len(eligible_directions)
                + len(prior_rows),
            ),
            6,
        )
        if (suppressed_scopes or duplicate_rows or eligible_directions or prior_rows)
        else 0.0
    )

    unresolved_cases = []
    if duplicate_pressure:
        unresolved_cases.append(
            {
                "case_id": "duplicate_low_value_run_pressure",
                "reason": "throughput pressure is visible, but no same-population before/after suppression baseline exists",
                "provenance_refs": [
                    f"{DEFAULT_DEDUP_PATH.as_posix()}#duplicate_rows",
                    f"{DEFAULT_THROUGHPUT_PATH.as_posix()}#bottlenecks",
                ],
            }
        )

    insufficient_evidence_cases = [
        {
            "case_id": "useful_outcome_rate_with_suppression",
            "reason": "current routing and sampling baselines prove ordering usefulness, not suppression-vs-no-suppression efficacy on the same population",
            "provenance_refs": [
                DEFAULT_ROUTING_BASELINE_PATH.as_posix(),
                DEFAULT_SAMPLING_BASELINE_PATH.as_posix(),
            ],
        },
        {
            "case_id": "useful_outcome_rate_baseline",
            "reason": "no repository-backed no-suppression comparator exists for the observed suppressed scopes",
            "provenance_refs": [
                DEFAULT_ROUTER_PATH.as_posix(),
                DEFAULT_DEDUP_PATH.as_posix(),
            ],
        },
        {
            "case_id": "false_suppression_rate",
            "reason": "no adjudication artifact records whether any suppressed exact scope later proved uniquely valuable",
            "provenance_refs": [
                DEFAULT_ROUTER_PATH.as_posix(),
                DEFAULT_PRIOR_FAILURE_PATH.as_posix(),
            ],
        },
        {
            "case_id": "compute_avoided",
            "reason": "suppressed scope counts are observed, but compute consumption for each prevented rerun is not materialized",
            "provenance_refs": [
                DEFAULT_ROUTER_PATH.as_posix(),
                DEFAULT_RUN_MANIFEST_PATH.as_posix(),
            ],
        },
    ]

    mechanics_exist = bool(source_status["research_cycle_router"]["status"] == "ready" and source_status["experiment_dedup_novelty_enforcement"]["status"] == "ready")
    evidence_populated = bool(suppressed_scopes or duplicate_rows or prior_rows or duplicate_candidate_count > 0)
    efficacy_measured = False
    efficacy_evidence_authoritative = False

    metrics = [
        _metric(
            "eligible_comparison_population",
            status="observed" if comparison_population_count else "missing",
            value=comparison_population_count if comparison_population_count else None,
            unit="items",
            rationale="Observed comparison population counts eligible directions plus directly suppressed repeated-scope rows.",
            provenance_refs=[
                DEFAULT_ROUTER_PATH.as_posix(),
                DEFAULT_DEDUP_PATH.as_posix(),
            ],
        ),
        _metric(
            "duplicate_candidates_detected",
            status="observed",
            value=duplicate_candidate_count,
            unit="candidates",
            rationale="Candidate-level duplicates come only from run-candidate dedupe artifacts when present.",
            provenance_refs=[DEFAULT_RUN_CANDIDATES_PATH.as_posix()],
        ),
        _metric(
            "duplicate_campaigns_detected",
            status="observed",
            value=len(active_duplicate_fingerprint) + len(active_scope_conflict),
            unit="campaign_groups",
            rationale="Detected duplicate campaigns are limited to explicit active duplicate rows in the dedup artifact.",
            provenance_refs=[DEFAULT_DEDUP_PATH.as_posix(), DEFAULT_CAMPAIGN_REGISTRY_PATH.as_posix()],
        ),
        _metric(
            "duplicate_campaign_pressure_visible",
            status="observed",
            value=len(duplicate_pressure) or int(throughput_summary.get("duplicate_low_value_run_count") or 0),
            unit="pressure_rows",
            rationale="Duplicate campaign pressure is visible through throughput bottleneck artifacts, even when an active duplicate group is not present now.",
            provenance_refs=[DEFAULT_DEDUP_PATH.as_posix(), DEFAULT_THROUGHPUT_PATH.as_posix()],
        ),
        _metric(
            "repeated_rejected_scopes_prevented",
            status="observed",
            value=repeated_rejected_scope_count,
            unit="scopes",
            rationale="Exact-failed-scope and materially-equivalent-retry suppression rows are directly observed prevented repeats.",
            provenance_refs=[DEFAULT_ROUTER_PATH.as_posix()],
        ),
        _metric(
            "dead_zone_selections_avoided",
            status="observed" if dead_zone_context_count else "missing",
            value=dead_zone_context_count if dead_zone_context_count else None,
            unit="dead_zone_links",
            rationale="Dead-zone visibility is counted only from explicit prior-failure retrieval rows linked back to a thesis.",
            provenance_refs=[DEFAULT_PRIOR_FAILURE_PATH.as_posix()],
        ),
        _metric(
            "evaluations_avoided",
            status="observed" if evaluation_avoidance_count else "missing",
            value=evaluation_avoidance_count if evaluation_avoidance_count else None,
            unit="evaluations",
            rationale="Avoided evaluations are limited to directly suppressed repeated scopes; no broader counterfactual is inferred.",
            provenance_refs=[DEFAULT_ROUTER_PATH.as_posix(), DEFAULT_DEDUP_PATH.as_posix()],
        ),
        _metric(
            "compute_avoided",
            status="insufficient_evidence",
            value=None,
            unit="compute_units",
            rationale="Run-manifest artifacts do not attribute compute cost to each prevented rerun.",
            provenance_refs=[DEFAULT_RUN_MANIFEST_PATH.as_posix(), DEFAULT_ROUTER_PATH.as_posix()],
        ),
        _metric(
            "useful_outcome_rate_with_suppression",
            status="insufficient_evidence",
            value=None,
            unit="rate",
            rationale="Observed routing/sampling usefulness cannot be re-labeled as suppression efficacy without a same-population comparator.",
            provenance_refs=[
                DEFAULT_ROUTING_BASELINE_PATH.as_posix(),
                DEFAULT_SAMPLING_BASELINE_PATH.as_posix(),
            ],
        ),
        _metric(
            "useful_outcome_rate_valid_baseline",
            status="insufficient_evidence",
            value=None,
            unit="rate",
            rationale="No repository-backed no-suppression baseline exists for the suppressed scopes.",
            provenance_refs=[DEFAULT_ROUTER_PATH.as_posix(), DEFAULT_DEDUP_PATH.as_posix()],
        ),
        _metric(
            "false_suppression_rate",
            status="insufficient_evidence",
            value=None,
            unit="rate",
            rationale="False suppression requires later adjudication evidence that is not materialized in current artifacts.",
            provenance_refs=[DEFAULT_ROUTER_PATH.as_posix(), DEFAULT_PRIOR_FAILURE_PATH.as_posix()],
        ),
        _metric(
            "provenance_completeness",
            status="measured",
            value=coverage_ratio,
            unit="ratio",
            rationale="Coverage ratio is the share of observed rows drawn from repository-backed artifacts in this report.",
            provenance_refs=[
                DEFAULT_ROUTER_PATH.as_posix(),
                DEFAULT_DEDUP_PATH.as_posix(),
                DEFAULT_PRIOR_FAILURE_PATH.as_posix(),
            ],
        ),
    ]
    for row in metrics:
        validation = validate_metric(row)
        if not validation["valid"]:
            raise ValueError(
                "qre_suppression_efficacy: invalid metric "
                f"{row.get('metric_id')}: {validation['rejection_reasons']}"
            )

    final_recommendation = "suppression_efficacy_insufficient_baseline"
    if final_recommendation not in FINAL_RECOMMENDATION_VALUES:
        raise ValueError(f"invalid final recommendation: {final_recommendation}")

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "source_status": source_status,
        "artifact_references": {
            "research_cycle_router": DEFAULT_ROUTER_PATH.as_posix(),
            "experiment_dedup_novelty_enforcement": DEFAULT_DEDUP_PATH.as_posix(),
            "prior_failure_retrieval": DEFAULT_PRIOR_FAILURE_PATH.as_posix(),
            "routing_baseline_comparison": DEFAULT_ROUTING_BASELINE_PATH.as_posix(),
            "sampling_baseline_comparison": DEFAULT_SAMPLING_BASELINE_PATH.as_posix(),
            "run_candidates": DEFAULT_RUN_CANDIDATES_PATH.as_posix(),
            "run_manifest": DEFAULT_RUN_MANIFEST_PATH.as_posix(),
            "campaign_registry": DEFAULT_CAMPAIGN_REGISTRY_PATH.as_posix(),
            "campaign_throughput_bottleneck_intelligence": DEFAULT_THROUGHPUT_PATH.as_posix(),
        },
        "metrics": metrics,
        "mechanics_vs_evidence": {
            "mechanics_exist": mechanics_exist,
            "evidence_populated": evidence_populated,
            "efficacy_measured": efficacy_measured,
            "efficacy_evidence_authoritative": efficacy_evidence_authoritative,
            "routing_baseline_score_context_only": float(current_routing.get("decision_usefulness_score") or 0.0),
            "sampling_baseline_score_context_only": float(current_sampling.get("decision_usefulness_score") or 0.0),
        },
        "unresolved_cases": unresolved_cases,
        "insufficient_evidence_cases": insufficient_evidence_cases,
        "summary": {
            "eligible_comparison_population_count": comparison_population_count,
            "suppressed_scope_count": len(suppressed_scopes),
            "duplicate_row_count": len(duplicate_rows),
            "campaign_registry_count": len(campaigns),
            "coverage_ratio": coverage_ratio,
            "final_recommendation": final_recommendation,
            "operator_summary": (
                "Suppression mechanics and populated evidence are visible for exact-scope suppression, duplicate pressure, "
                "and dead-zone linkage, but the repository does not yet contain a valid same-population no-suppression baseline."
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_routing": False,
            "mutates_sampling": False,
            "mutates_campaigns": False,
            "can_launch_campaign": False,
            "can_register_strategy": False,
            "can_generate_executable_strategy": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "context_only_not_authority": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Suppression Efficacy",
        "",
        "This surface measures only what the current repository artifacts can prove about dead-zone and duplicate suppression.",
        "",
        "| metric_id | status | value |",
        "| --- | --- | --- |",
    ]
    for row in report.get("metrics", []):
        value = row.get("value")
        rendered = "unavailable" if value is None else str(value)
        lines.append(
            f"| {_text(row.get('metric_id'))} | {_text(row.get('status'))} | {rendered} |"
        )
    mechanics = report.get("mechanics_vs_evidence") if isinstance(report.get("mechanics_vs_evidence"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines.extend(
        [
            "",
            f"- mechanics_exist: `{bool(mechanics.get('mechanics_exist'))}`",
            f"- evidence_populated: `{bool(mechanics.get('evidence_populated'))}`",
            f"- efficacy_measured: `{bool(mechanics.get('efficacy_measured'))}`",
            f"- efficacy_evidence_authoritative: `{bool(mechanics.get('efficacy_evidence_authoritative'))}`",
            f"- final_recommendation: `{_text(summary.get('final_recommendation'))}`",
            "",
            "Current routing and sampling baselines are reused as context only. They are not treated as a suppression-vs-no-suppression comparator.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path.cwd()
    latest = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    doc = root / DOC_PATH
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    for path in (latest, doc):
        _validate_write_target(path)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, latest)
    doc.write_text(render_doc(report), encoding="utf-8")
    return {
        "latest": latest.relative_to(root).as_posix(),
        "doc": doc.relative_to(root).as_posix(),
    }


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {"status": "missing", "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(), "fails_closed": True}
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_status(), indent=2, sort_keys=True))
        return 0
    report = build_suppression_efficacy()
    if args.write:
        print(json.dumps(write_outputs(report), indent=2, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
