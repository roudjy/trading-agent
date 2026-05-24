"""ADE-QRE-012 trusted-loop evidence materializer.

Read-only helper that materialises missing trusted-loop evidence
snapshots from artifacts that already exist locally. It never emits
synthetic reason records, routing candidates, sampling strata, failure
actions, strategies, registry entries, or trading behavior.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import intelligent_routing_minimal as _routing
from reporting import reason_record_evidence_density as _rr_density
from reporting import reason_records as _rr
from reporting import research_observability_minimal as _observability
from reporting import sampling_intelligence_minimal as _sampling

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-014g-2026-05-24"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "trusted_loop_materialization_digest"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "trusted_loop_materialization"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/trusted_loop_materialization/"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "trusted_loop_materialization: refusing write outside "
            f"allowlist: {path!r}"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _numeric_or_none(value: Any) -> int | float | None:
    return value if _is_number(value) else None


_KPI_READINESS_SPECS: Final[dict[str, dict[str, Any]]] = {
    "TTFPRC": {
        "direction": "minimise",
        "required_evidence": (
            "sprint_exit_merge_timestamp",
            "paper_readiness_checklist_overall_yes_timestamp",
        ),
    },
    "OOS_DSR": {
        "direction": "maximise",
        "required_evidence": (
            "oos_survivor_deflated_sharpe_distribution",
            "multiplicity_ledger_n_eff",
        ),
    },
    "MASQ": {
        "direction": "maximise",
        "required_evidence": (
            "active_survivor_multiplicity_adjusted_sharpe_distribution",
            "multiplicity_ledger_n_eff",
        ),
    },
    "NMBR": {
        "direction": "maximise",
        "required_evidence": (
            "promotion_candidate_count",
            "promotion_candidate_null_model_yes_count",
        ),
    },
    "DZCR": {
        "direction": "minimise",
        "required_evidence": (
            "dead_zone_flagged_compute",
            "total_campaign_compute",
            "quarter_prior_reset_baseline",
        ),
    },
    "OAB": {
        "direction": "minimise",
        "required_evidence": (
            "visible_surface_count",
            "operator_decisions_per_week",
        ),
    },
    "CRSR": {
        "direction": "maximise",
        "required_evidence": (
            "promotion_candidate_count",
            "multi_asset_timeframe_regime_survivor_count",
        ),
    },
}


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _kpi_evidence_source(
    observability_snapshot: Mapping[str, Any],
    kpi_id: str,
) -> Mapping[str, Any]:
    evidence = _mapping_or_empty(
        observability_snapshot.get("research_quality_kpi_evidence")
    )
    return _mapping_or_empty(evidence.get(kpi_id))


def _available_kpi_components(
    *,
    kpi_id: str,
    observability_snapshot: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, int | float]:
    components = {
        key: value
        for key, value in evidence.items()
        if _is_number(value) and key != "value"
    }
    if kpi_id == "OAB":
        oab = _mapping_or_empty(observability_snapshot.get("operator_attention_budget"))
        for key in (
            "visible_surfaces_per_campaign_cap",
            "subjects_observed",
            "attention_overflow_count",
            "near_cap_count",
        ):
            numeric = _numeric_or_none(oab.get(key))
            if numeric is not None:
                components.setdefault(key, numeric)
    return dict(sorted(components.items()))


def _derive_kpi_numeric_value(
    *,
    kpi_id: str,
    evidence: Mapping[str, Any],
) -> int | float | None:
    direct_value = _numeric_or_none(evidence.get("value"))
    if direct_value is not None:
        return direct_value
    if kpi_id == "OAB":
        visible_surface_count = _numeric_or_none(evidence.get("visible_surface_count"))
        operator_decisions = _numeric_or_none(evidence.get("operator_decisions_per_week"))
        if visible_surface_count is not None and operator_decisions is not None:
            return visible_surface_count * operator_decisions
    return None


def _kpi_readiness_row(
    *,
    kpi_id: str,
    observability_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    spec = _KPI_READINESS_SPECS[kpi_id]
    evidence = _kpi_evidence_source(observability_snapshot, kpi_id)
    value = _derive_kpi_numeric_value(kpi_id=kpi_id, evidence=evidence)
    components = _available_kpi_components(
        kpi_id=kpi_id,
        observability_snapshot=observability_snapshot,
        evidence=evidence,
    )
    numeric_ready = value is not None
    row: dict[str, Any] = {
        "status": "ready" if numeric_ready else "fail_closed",
        "value": value,
        "numeric_value_ready": numeric_ready,
        "fail_closed": not numeric_ready,
        "readiness_score": 1.0 if numeric_ready else 0.0,
        "direction": spec["direction"],
        "required_evidence": list(spec["required_evidence"]),
        "missing_evidence": [] if numeric_ready else list(spec["required_evidence"]),
        "source": (
            str(evidence.get("source"))
            if isinstance(evidence.get("source"), str)
            else "research_quality_kpi_evidence"
            if evidence
            else "not_available"
        ),
    }
    if components:
        row["available_components"] = components
        row["partial_evidence_count"] = len(components)
    else:
        row["partial_evidence_count"] = 0
    return row


def _trusted_loop_metric_values(
    observability_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only numeric values already present in evidence.

    Null rates caused by zero denominators are reported as not-ready,
    not converted to zero.
    """
    qre = observability_snapshot.get("qre_operator_summary")
    qre = qre if isinstance(qre, Mapping) else {}
    oab = observability_snapshot.get("operator_attention_budget")
    oab = oab if isinstance(oab, Mapping) else {}

    values: dict[str, dict[str, Any]] = {}
    for key in (
        "unknown_failure_rate",
        "actionable_failure_rate",
        "attribution_depth_score",
    ):
        numeric = _numeric_or_none(qre.get(key))
        values[key] = {
            "ready": numeric is not None,
            "value": numeric,
            "source": "logs/research_observability_minimal/latest.json",
            "note": (
                "evidence_backed"
                if numeric is not None
                else "not_ready_zero_denominator_or_missing_evidence"
            ),
        }

    for key in (
        "visible_surfaces_per_campaign_cap",
        "subjects_observed",
        "attention_overflow_count",
        "near_cap_count",
    ):
        numeric = _numeric_or_none(oab.get(key))
        values[f"operator_attention_budget_{key}"] = {
            "ready": numeric is not None,
            "value": numeric,
            "source": "logs/research_observability_minimal/latest.json",
            "note": "evidence_backed" if numeric is not None else "not_ready",
        }
    return values


def _research_quality_kpi_readiness(
    observability_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Surface KPI numeric readiness without inventing values."""
    readiness = {
        kpi_id: _kpi_readiness_row(
            kpi_id=kpi_id,
            observability_snapshot=observability_snapshot,
        )
        for kpi_id in _observability.RESEARCH_QUALITY_KPI_IDS
    }
    complete_count = sum(
        1 for row in readiness.values() if row.get("numeric_value_ready") is True
    )
    fail_closed_count = sum(
        1 for row in readiness.values() if row.get("fail_closed") is True
    )
    partial_count = sum(
        1
        for row in readiness.values()
        if row.get("fail_closed") is True
        and _numeric_or_none(row.get("partial_evidence_count"))
    )
    return {
        "kpi_ids": list(_observability.RESEARCH_QUALITY_KPI_IDS),
        "values": readiness,
        "complete_value_count": complete_count,
        "partial_value_count": partial_count,
        "fail_closed_count": fail_closed_count,
        "all_reported_kpis_numeric_or_fail_closed": (
            complete_count + fail_closed_count == len(readiness)
        ),
        "note": (
            "KPI rows are ready only when numeric values are evidence-backed; "
            "missing, partial, unknown, or non-numeric evidence fails closed."
        ),
    }


def _readiness_evidence_score(
    required_evidence: tuple[str, ...],
    missing_evidence: list[str],
) -> float:
    ready_count = len(required_evidence) - len(missing_evidence)
    return round(ready_count / len(required_evidence), 6)


def _routing_sampling_readiness_row(
    *,
    kind: str,
    snapshot: Mapping[str, Any],
    artifact_path: Path,
) -> dict[str, Any]:
    counts = _mapping_or_empty(snapshot.get("counts"))
    by_decision = _mapping_or_empty(counts.get("by_decision"))
    total = _numeric_or_none(counts.get("total"))
    recommendation = snapshot.get("final_recommendation")
    recommendation = recommendation if isinstance(recommendation, str) else "unknown"

    if kind == "routing":
        ready_recommendation = "ready_for_implementation"
        ready_count_key = "prioritize_count"
        ready_count = _numeric_or_none(by_decision.get("prioritize"))
        ready_decision = "prioritize"
    elif kind == "sampling":
        ready_recommendation = "ready_for_sampling"
        ready_count_key = "actionable_count"
        ready_count = _numeric_or_none(counts.get("actionable"))
        ready_decision = "actionable_sampling_decision"
    else:
        raise ValueError(f"unknown readiness kind: {kind!r}")

    required_evidence = (
        "latest_artifact_present",
        "final_recommendation_ready",
        "total_count_positive",
        f"{ready_count_key}_positive",
    )
    missing_evidence: list[str] = []
    artifact_exists = artifact_path.is_file()
    if not artifact_exists:
        missing_evidence.append("latest_artifact_present")
    if recommendation != ready_recommendation:
        missing_evidence.append("final_recommendation_ready")
    if total is None or total <= 0:
        missing_evidence.append("total_count_positive")
    if ready_count is None or ready_count <= 0:
        missing_evidence.append(f"{ready_count_key}_positive")

    ready = not missing_evidence
    return {
        "status": "ready" if ready else "fail_closed",
        "ready": ready,
        "fail_closed": not ready,
        "artifact_path": _rel(artifact_path),
        "artifact_present": artifact_exists,
        "final_recommendation": recommendation,
        "expected_final_recommendation": ready_recommendation,
        "total": total,
        ready_count_key: ready_count,
        "ready_decision": ready_decision,
        "required_evidence": list(required_evidence),
        "missing_evidence": missing_evidence,
        "readiness_score": 1.0 if ready else 0.0,
        "evidence_density_score": _readiness_evidence_score(
            required_evidence,
            missing_evidence,
        ),
        "source": "existing_read_only_artifact_snapshot",
    }


def _routing_sampling_readiness_density(
    *,
    routing_snapshot: Mapping[str, Any],
    sampling_snapshot: Mapping[str, Any],
    routing_artifact_path: Path,
    sampling_artifact_path: Path,
) -> dict[str, Any]:
    """Fail-closed read-only readiness over routing/sampling artifacts."""
    rows = {
        "routing_ready": _routing_sampling_readiness_row(
            kind="routing",
            snapshot=routing_snapshot,
            artifact_path=routing_artifact_path,
        ),
        "sampling_ready": _routing_sampling_readiness_row(
            kind="sampling",
            snapshot=sampling_snapshot,
            artifact_path=sampling_artifact_path,
        ),
    }
    ready_count = sum(1 for row in rows.values() if row["ready"] is True)
    fail_closed_count = len(rows) - ready_count
    missing_evidence_count = sum(
        len(row["missing_evidence"]) for row in rows.values()
    )
    required_evidence_count = sum(
        len(row["required_evidence"]) for row in rows.values()
    )
    return {
        "values": rows,
        "ready_count": ready_count,
        "fail_closed_count": fail_closed_count,
        "missing_evidence_count": missing_evidence_count,
        "required_evidence_count": required_evidence_count,
        "overall_status": "ready" if fail_closed_count == 0 else "fail_closed",
        "overall_evidence_density_score": round(
            (required_evidence_count - missing_evidence_count)
            / required_evidence_count,
            6,
        ),
        "all_reported_readiness_numeric_or_fail_closed": True,
        "note": (
            "Routing and sampling readiness become ready only when existing "
            "read-only artifacts contain positive ready evidence; missing, "
            "empty, unknown, or non-ready evidence fails closed."
        ),
    }


def _synthesis_blocker_explanation_density(
    *,
    block_reasons: list[str],
    failure_action_mapping: Mapping[str, Any],
    kpi_readiness: Mapping[str, Any],
    routing_sampling_readiness: Mapping[str, Any],
    reason_density: Mapping[str, Any],
) -> dict[str, Any]:
    """Explain active synthesis blockers from read-only readiness evidence."""
    kpi_total = len(_mapping_or_empty(kpi_readiness.get("values")))
    kpi_complete = int(kpi_readiness.get("complete_value_count") or 0)
    kpi_partial = int(kpi_readiness.get("partial_value_count") or 0)
    kpi_fail_closed = int(kpi_readiness.get("fail_closed_count") or 0)

    failure_status = str(failure_action_mapping.get("status") or "unknown")
    failure_total = _numeric_or_none(failure_action_mapping.get("total_failures"))
    failure_actionable = _numeric_or_none(
        failure_action_mapping.get("actionable_failure_count")
    )

    reason_metrics = _mapping_or_empty(reason_density.get("metrics"))
    reason_record_count = _numeric_or_none(reason_metrics.get("record_count"))
    reason_with_refs = _numeric_or_none(
        reason_metrics.get("records_with_evidence_refs")
    )
    reason_final = str(reason_density.get("final_recommendation") or "unknown")

    routing_values = _mapping_or_empty(routing_sampling_readiness.get("values"))
    routing_ready = _mapping_or_empty(routing_values.get("routing_ready"))
    sampling_ready = _mapping_or_empty(routing_values.get("sampling_ready"))

    source_refs = {
        "failure_action_mapping": "logs/failure_action_mapping_minimal/latest.json",
        "research_quality_kpi_readiness": (
            "logs/research_observability_minimal/latest.json"
        ),
        "reason_record_evidence_density": (
            "logs/reason_record_evidence_density/latest.json"
        ),
        "routing_sampling_readiness_density": (
            "logs/intelligent_routing_minimal/latest.json"
        ),
        "strategy_synthesis_authority": (
            "docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md"
        ),
    }

    templates: dict[str, dict[str, Any]] = {
        "failure_action_mapping_not_ready_when_total_failures_zero": {
            "source": "failure_action_mapping",
            "evidence_status": failure_status,
            "readiness_score": 0.0 if failure_status != "ready" else 1.0,
            "missing_evidence": (
                ["positive_failure_count", "actionable_failure_mapping"]
                if not failure_total
                else []
            ),
            "operator_explanation": (
                "Failure-to-action evidence is not yet actionable: "
                f"status={failure_status}, total_failures={failure_total or 0}, "
                f"actionable_failure_count={failure_actionable or 0}."
            ),
        },
        "no_complete_research_quality_kpi_values": {
            "source": "research_quality_kpi_readiness",
            "evidence_status": ("fail_closed" if kpi_fail_closed else "ready"),
            "readiness_score": (
                round(kpi_complete / kpi_total, 6) if kpi_total else 0.0
            ),
            "missing_evidence": (
                ["complete_numeric_research_quality_kpis"]
                if kpi_complete == 0
                else ["all_research_quality_kpis_numeric"]
                if kpi_fail_closed
                else []
            ),
            "operator_explanation": (
                "Research quality KPI readiness is numerically incomplete: "
                f"{kpi_complete}/{kpi_total} complete, {kpi_partial} partial, "
                f"{kpi_fail_closed} fail-closed."
            ),
        },
        "reason_record_evidence_density_not_ready": {
            "source": "reason_record_evidence_density",
            "evidence_status": reason_final,
            "readiness_score": (
                round(reason_with_refs / reason_record_count, 6)
                if reason_record_count
                else 0.0
            ),
            "missing_evidence": (
                ["reason_records_with_evidence_refs"]
                if reason_final != "evidence_density_ready"
                else []
            ),
            "operator_explanation": (
                "Reason-record evidence density is not ready: "
                f"final_recommendation={reason_final}, "
                f"record_count={reason_record_count or 0}, "
                f"records_with_evidence_refs={reason_with_refs or 0}."
            ),
        },
        "routing_ready_evidence_missing_or_not_ready": {
            "source": "routing_sampling_readiness_density",
            "evidence_status": str(routing_ready.get("status") or "unknown"),
            "readiness_score": _numeric_or_none(
                routing_ready.get("evidence_density_score")
            )
            or 0.0,
            "missing_evidence": list(routing_ready.get("missing_evidence") or []),
            "operator_explanation": (
                "Routing readiness is not implementation-ready: "
                f"final_recommendation={routing_ready.get('final_recommendation') or 'unknown'}, "
                f"total={routing_ready.get('total')}, "
                f"prioritize_count={routing_ready.get('prioritize_count')}."
            ),
        },
        "sampling_ready_evidence_missing_or_not_ready": {
            "source": "routing_sampling_readiness_density",
            "evidence_status": str(sampling_ready.get("status") or "unknown"),
            "readiness_score": _numeric_or_none(
                sampling_ready.get("evidence_density_score")
            )
            or 0.0,
            "missing_evidence": list(sampling_ready.get("missing_evidence") or []),
            "operator_explanation": (
                "Sampling readiness is not sampling-ready: "
                f"final_recommendation={sampling_ready.get('final_recommendation') or 'unknown'}, "
                f"total={sampling_ready.get('total')}, "
                f"actionable_count={sampling_ready.get('actionable_count')}."
            ),
        },
        "no_strategy_synthesis_scope_authorized": {
            "source": "strategy_synthesis_authority",
            "evidence_status": "blocked_by_governance",
            "readiness_score": 0.0,
            "missing_evidence": ["operator_approved_strategy_synthesis_scope"],
            "operator_explanation": (
                "Strategy synthesis remains outside the approved runtime scope; "
                "this report is read-only and does not authorize strategy, "
                "registry, routing, or execution mutation."
            ),
        },
    }

    active_rows: dict[str, dict[str, Any]] = {}
    unexplained: list[str] = []
    for reason in sorted(dict.fromkeys(block_reasons)):
        template = templates.get(reason)
        if template is None:
            unexplained.append(reason)
            continue
        source = str(template["source"])
        active_rows[reason] = {
            "status": "explained_blocker",
            "active": True,
            "source": source,
            "source_ref": source_refs[source],
            "evidence_status": template["evidence_status"],
            "readiness_score": template["readiness_score"],
            "missing_evidence": template["missing_evidence"],
            "operator_explanation": template["operator_explanation"],
            "read_only": True,
            "enables_strategy_synthesis": False,
        }

    explained_count = len(active_rows)
    active_count = explained_count + len(unexplained)
    return {
        "values": active_rows,
        "active_blocker_count": active_count,
        "explained_blocker_count": explained_count,
        "unexplained_blocker_count": len(unexplained),
        "unexplained_block_reasons": unexplained,
        "overall_status": (
            "blocked_explained" if active_count and not unexplained else "fail_closed"
        ),
        "operator_summary": (
            f"{explained_count}/{active_count} active synthesis blockers have "
            "operator-readable, evidence-derived explanations."
        ),
        "read_only": True,
        "synthesis_remains_blocked": True,
    }


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    reason_records_artifact_dir: Path | None = None,
    routing_artifact_dir: Path | None = None,
    sampling_artifact_dir: Path | None = None,
    observability_artifact_dir: Path | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    rr_dir = reason_records_artifact_dir or _rr.ARTIFACT_DIR
    routing_dir = routing_artifact_dir or _routing.ARTIFACT_DIR
    sampling_dir = sampling_artifact_dir or _sampling.ARTIFACT_DIR
    observability_dir = observability_artifact_dir or _observability.ARTIFACT_DIR

    reason_manifest = _rr.collect_manifest(
        artifact_dir=rr_dir,
        frozen_utc=ts,
    )
    reason_density = _rr_density.collect_snapshot(
        frozen_utc=ts,
        reason_records_artifact_dir=rr_dir,
        routing_minimal_path=routing_dir / _routing.ARTIFACT_LATEST.name,
        sampling_minimal_path=sampling_dir / _sampling.ARTIFACT_LATEST.name,
        failure_action_mapping_path=_observability.FAILURE_ACTION_MAPPING_LATEST,
    )
    routing_snapshot = _routing.collect_snapshot(
        candidates=[],
        frozen_utc=ts,
        emit_reason_records=False,
    )
    sampling_snapshot = _sampling.collect_snapshot(
        candidates=[],
        frozen_utc=ts,
        emit_reason_records=False,
    )
    observability_snapshot = _observability.collect_snapshot(
        routing_minimal_path=routing_dir / _routing.ARTIFACT_LATEST.name,
        sampling_minimal_path=sampling_dir / _sampling.ARTIFACT_LATEST.name,
        reason_records_artifact_dir=rr_dir,
        frozen_utc=ts,
    )
    metrics = _trusted_loop_metric_values(observability_snapshot)
    kpis = _research_quality_kpi_readiness(observability_snapshot)
    routing_sampling_readiness = _routing_sampling_readiness_density(
        routing_snapshot=routing_snapshot,
        sampling_snapshot=sampling_snapshot,
        routing_artifact_path=routing_dir / _routing.ARTIFACT_LATEST.name,
        sampling_artifact_path=sampling_dir / _sampling.ARTIFACT_LATEST.name,
    )
    block_reasons = [
        "failure_action_mapping_not_ready_when_total_failures_zero",
        "no_complete_research_quality_kpi_values",
        "no_strategy_synthesis_scope_authorized",
    ]
    if (
        routing_sampling_readiness["values"]["routing_ready"]["fail_closed"]
        is True
    ):
        block_reasons.append("routing_ready_evidence_missing_or_not_ready")
    if (
        routing_sampling_readiness["values"]["sampling_ready"]["fail_closed"]
        is True
    ):
        block_reasons.append("sampling_ready_evidence_missing_or_not_ready")
    if reason_density["final_recommendation"] != "evidence_density_ready":
        block_reasons.append("reason_record_evidence_density_not_ready")
    blocker_explanation_density = _synthesis_blocker_explanation_density(
        block_reasons=block_reasons,
        failure_action_mapping=(
            observability_snapshot.get("qre_operator_summary", {})
            .get("failure_action_mapping", {})
        ),
        kpi_readiness=kpis,
        routing_sampling_readiness=routing_sampling_readiness,
        reason_density=reason_density,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "materialized_artifacts": {
            "reason_records_manifest": {
                "path": _rel(rr_dir / _rr.MANIFEST_PATH.name),
                "total_records": reason_manifest["total_records"],
                "note": reason_manifest["note"],
            },
            "reason_record_evidence_density": {
                "record_count": reason_density["metrics"]["record_count"],
                "records_with_evidence_refs": reason_density["metrics"][
                    "records_with_evidence_refs"
                ],
                "final_recommendation": reason_density["final_recommendation"],
            },
            "routing_minimal_latest": {
                "path": _rel(routing_dir / _routing.ARTIFACT_LATEST.name),
                "total": routing_snapshot["counts"]["total"],
                "final_recommendation": routing_snapshot["final_recommendation"],
            },
            "sampling_minimal_latest": {
                "path": _rel(sampling_dir / _sampling.ARTIFACT_LATEST.name),
                "total": sampling_snapshot["counts"]["total"],
                "final_recommendation": sampling_snapshot["final_recommendation"],
            },
            "research_observability_latest": {
                "path": _rel(observability_dir / _observability.ARTIFACT_LATEST.name),
                "final_recommendation": observability_snapshot["final_recommendation"],
            },
        },
        "trusted_loop_metric_values": metrics,
        "reason_record_evidence_density": reason_density,
        "research_quality_kpi_readiness": kpis,
        "routing_sampling_readiness_density": routing_sampling_readiness,
        "failure_action_mapping": (
            observability_snapshot.get("qre_operator_summary", {})
            .get("failure_action_mapping", {})
        ),
        "synthesis_remains_blocked": True,
        "block_reasons": block_reasons,
        "synthesis_blocker_explanation_density": blocker_explanation_density,
        "safety_invariants": {
            "read_only": True,
            "emits_reason_records": False,
            "emits_routing_candidates": False,
            "emits_sampling_strata": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    json_now = base / f"{ts}.json"
    json_latest = base / ARTIFACT_LATEST.name
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    _validate_write_target(json_now)
    _validate_write_target(json_latest)
    _validate_write_target(history)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def materialize(
    *,
    frozen_utc: str | None = None,
    write: bool = True,
    reason_records_artifact_dir: Path | None = None,
    routing_artifact_dir: Path | None = None,
    sampling_artifact_dir: Path | None = None,
    observability_artifact_dir: Path | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    rr_dir = reason_records_artifact_dir or _rr.ARTIFACT_DIR
    routing_dir = routing_artifact_dir or _routing.ARTIFACT_DIR
    sampling_dir = sampling_artifact_dir or _sampling.ARTIFACT_DIR
    observability_dir = observability_artifact_dir or _observability.ARTIFACT_DIR

    if write:
        _rr.write_manifest(artifact_dir=rr_dir, frozen_utc=ts)
        _routing.write_outputs(
            _routing.collect_snapshot(
                candidates=[],
                frozen_utc=ts,
                emit_reason_records=False,
            ),
            artifact_dir=routing_dir,
        )
        _sampling.write_outputs(
            _sampling.collect_snapshot(
                candidates=[],
                frozen_utc=ts,
                emit_reason_records=False,
            ),
            artifact_dir=sampling_dir,
        )

    snapshot = collect_snapshot(
        frozen_utc=ts,
        reason_records_artifact_dir=rr_dir,
        routing_artifact_dir=routing_dir,
        sampling_artifact_dir=sampling_dir,
        observability_artifact_dir=observability_dir,
    )

    if write:
        observability_snapshot = _observability.collect_snapshot(
            routing_minimal_path=routing_dir / _routing.ARTIFACT_LATEST.name,
            sampling_minimal_path=sampling_dir / _sampling.ARTIFACT_LATEST.name,
            reason_records_artifact_dir=rr_dir,
            frozen_utc=ts,
        )
        _observability.write_outputs(
            observability_snapshot,
            artifact_dir=observability_dir,
        )
        snapshot["_artifact_paths"] = write_outputs(snapshot, artifact_dir=artifact_dir)
    return snapshot


def read_latest_snapshot(
    *,
    artifact_dir: Path | None = None,
) -> dict[str, Any] | None:
    base = artifact_dir or ARTIFACT_DIR
    path = base / ARTIFACT_LATEST.name
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.trusted_loop_materialization",
        description="Materialize ADE-QRE-012 read-only trusted-loop artifacts.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        snapshot = read_latest_snapshot()
        if snapshot is None:
            snapshot = {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "report_kind": REPORT_KIND,
                "final_recommendation": "not_available",
            }
        print(json.dumps(snapshot, sort_keys=True, indent=2))
        return 0

    snapshot = materialize(
        frozen_utc=args.frozen_utc,
        write=not args.no_write,
    )
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
