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
from reporting import reason_records as _rr
from reporting import research_observability_minimal as _observability
from reporting import sampling_intelligence_minimal as _sampling

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-012-2026-05-23"
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
    """Surface KPI numeric readiness without inventing values.

    Of the seven pinned research-quality KPIs, ADE-QRE-012 can only
    expose OAB components from the current observability snapshot.
    The other KPI values require paper-readiness, survivor, null,
    dead-zone-compute, or robustness evidence that is not present in
    the current trusted-loop artifacts.
    """
    oab = observability_snapshot.get("operator_attention_budget")
    oab = oab if isinstance(oab, Mapping) else {}
    oab_components = {
        key: oab.get(key)
        for key in (
            "visible_surfaces_per_campaign_cap",
            "subjects_observed",
            "attention_overflow_count",
            "near_cap_count",
        )
        if _is_number(oab.get(key))
    }
    readiness = {
        "TTFPRC": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "paper_readiness_checklist_overall_yes",
        },
        "OOS_DSR": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "oos_survivor_deflated_sharpe_distribution",
        },
        "MASQ": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "active_survivor_multiplicity_adjusted_sharpe",
        },
        "NMBR": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "promotion_candidate_null_model_results",
        },
        "DZCR": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "dead_zone_compute_telemetry_baseline",
        },
        "OAB": {
            "status": "partial",
            "value": None,
            "numeric_components": oab_components,
            "missing_evidence": "operator_decisions_per_week_component",
        },
        "CRSR": {
            "status": "not_ready",
            "value": None,
            "missing_evidence": "promotion_candidate_robustness_checks",
        },
    }
    return {
        "kpi_ids": list(_observability.RESEARCH_QUALITY_KPI_IDS),
        "values": readiness,
        "complete_value_count": sum(
            1 for row in readiness.values() if row.get("status") == "ready"
        ),
        "partial_value_count": sum(
            1 for row in readiness.values() if row.get("status") == "partial"
        ),
        "note": (
            "No complete seven-KPI numeric value is created without its "
            "required evidence. OAB components are surfaced because the "
            "observability snapshot already computes them."
        ),
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
        "research_quality_kpi_readiness": kpis,
        "failure_action_mapping": (
            observability_snapshot.get("qre_operator_summary", {})
            .get("failure_action_mapping", {})
        ),
        "synthesis_remains_blocked": True,
        "block_reasons": [
            "failure_action_mapping_not_ready_when_total_failures_zero",
            "no_complete_research_quality_kpi_values",
            "no_strategy_synthesis_scope_authorized",
        ],
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
