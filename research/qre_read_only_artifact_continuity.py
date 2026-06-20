from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_candidate_identity_lifecycle as lifecycle_report
from research import qre_candidate_quality_framework as quality_framework
from research import qre_evidence_breadth_framework as breadth_framework
from research import qre_hypothesis_disposition_memory as disposition_memory
from research import qre_multibasket_portfolio_intelligence as portfolio_intelligence
from research import qre_null_control_falsification_suite as null_suite
from research import qre_preregistered_multiwindow_evidence_run as multiwindow_run
from research import qre_research_cycle_router as cycle_router
from research import qre_shadow_readiness_gates as shadow_gates


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_read_only_artifact_continuity"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_read_only_artifact_continuity")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_read_only_artifact_continuity/"

DISPOSITION_PATH: Final[Path] = disposition_memory.DEFAULT_OUTPUT_DIR / disposition_memory.LATEST_NAME
ROUTER_PATH: Final[Path] = cycle_router.DEFAULT_OUTPUT_DIR / cycle_router.LATEST_NAME
NULL_CONTROL_PATH: Final[Path] = null_suite.DEFAULT_OUTPUT_DIR / null_suite.LATEST_NAME
RESEARCH_MEMORY_PATH: Final[Path] = cycle_router.DEFAULT_RESEARCH_MEMORY_PATH
BREADTH_PATH: Final[Path] = breadth_framework.DEFAULT_OUTPUT_DIR / breadth_framework.LATEST_NAME
LIFECYCLE_PATH: Final[Path] = lifecycle_report.DEFAULT_OUTPUT_DIR / lifecycle_report.LATEST_NAME
QUALITY_PATH: Final[Path] = quality_framework.DEFAULT_OUTPUT_DIR / quality_framework.LATEST_NAME
PORTFOLIO_PATH: Final[Path] = portfolio_intelligence.DEFAULT_OUTPUT_DIR / portfolio_intelligence.LATEST_NAME
SHADOW_PATH: Final[Path] = shadow_gates.DEFAULT_OUTPUT_DIR / shadow_gates.LATEST_NAME
CLOSURE_PATH: Final[Path] = quality_framework.DEFAULT_CLOSURE_PATH
QUALITY_REASON_CONTRACT_PATH: Final[Path] = quality_framework.DEFAULT_REASON_RECORD_CONTRACT_PATH
QUALITY_SOURCE_AUTHORITY_PATH: Final[Path] = quality_framework.DEFAULT_SOURCE_AUTHORITY_PATH
SHADOW_TRUSTED_LOOP_PATH: Final[Path] = shadow_gates.TRUSTED_LOOP_REVIEW_PATH
SHADOW_OPERATIONAL_CONTROLS_PATH: Final[Path] = shadow_gates.OPERATIONAL_CONTROLS_PATH


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _current_status_rows(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "hypothesis_disposition_memory": disposition_memory.read_hypothesis_disposition_memory_status(
            repo_root=repo_root
        ),
        "research_cycle_router": cycle_router.read_research_cycle_router_status(
            repo_root=repo_root
        ),
        "null_control_falsification_suite": null_suite.read_null_control_suite_status(
            repo_root=repo_root
        ),
    }


def _report_kind_ready(report: Mapping[str, Any] | None, *, expected_kind: str) -> bool:
    return isinstance(report, Mapping) and _text(report.get("report_kind")) == expected_kind


def _report_status(report: Mapping[str, Any] | None) -> str:
    if not isinstance(report, Mapping):
        return "blocked"
    if _text(report.get("status")) in {"ready", "suite_ready_preregistered_context"}:
        return "ready"
    return "blocked"


def _report_hash(report: Mapping[str, Any] | None) -> str:
    if not isinstance(report, Mapping):
        return ""
    for key in ("deterministic_hash", "hash"):
        value = _text(report.get(key))
        if value:
            return value
    return _digest(report)


def _breadth_report_status(report: Mapping[str, Any] | None) -> str:
    if not _report_kind_ready(report, expected_kind=breadth_framework.REPORT_KIND):
        return "blocked"
    return "ready" if _text(report.get("status")) == "ready" else "blocked"


def _lifecycle_report_status(report: Mapping[str, Any] | None) -> str:
    if not _report_kind_ready(report, expected_kind=lifecycle_report.REPORT_KIND):
        return "blocked"
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "ready" if _text(summary.get("final_recommendation")) == "qre_candidate_lifecycle_fail_closed" else "blocked"


def _quality_report_status(report: Mapping[str, Any] | None) -> str:
    if not _report_kind_ready(report, expected_kind=quality_framework.REPORT_KIND):
        return "blocked"
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "ready" if _text(summary.get("final_recommendation")) == "candidate_quality_fail_closed" else "blocked"


def _portfolio_report_status(report: Mapping[str, Any] | None) -> str:
    if not _report_kind_ready(report, expected_kind=portfolio_intelligence.REPORT_KIND):
        return "blocked"
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "ready" if _text(summary.get("final_recommendation")) == "portfolio_research_fail_closed" else "blocked"


def _shadow_report_status(report: Mapping[str, Any] | None) -> str:
    if not _report_kind_ready(report, expected_kind=shadow_gates.REPORT_KIND):
        return "blocked"
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return (
        "ready"
        if _text(summary.get("readiness_status"))
        in {"shadow_readiness_deferred", "shadow_readiness_prerequisites_satisfied_context_only"}
        else "blocked"
    )


def _materialization_state(
    *,
    current_payload: Mapping[str, Any] | None,
    projected_payload: Mapping[str, Any] | None,
    status_reader=_report_status,
) -> str:
    if status_reader(projected_payload) != "ready":
        return "blocked_missing_prerequisites"
    if not isinstance(current_payload, Mapping):
        return "materializable_missing_current_artifact"
    if _report_hash(current_payload) == _report_hash(projected_payload):
        return "current_artifact_matches_projected"
    return "materializable_stale_or_mismatched_current_artifact"


def _disposition_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current = _read_json(repo_root / DISPOSITION_PATH)
    projected = disposition_memory.build_hypothesis_disposition_memory(repo_root=repo_root)
    row = {
        "artifact_key": "hypothesis_disposition_memory",
        "artifact_path": DISPOSITION_PATH.as_posix(),
        "current_status": _text(
            disposition_memory.read_hypothesis_disposition_memory_status(repo_root=repo_root).get("status")
        ),
        "projected_status": _report_status(projected),
        "materialization_state": _materialization_state(
            current_payload=current,
            projected_payload=projected,
            status_reader=_report_status,
        ),
        "reason_codes": [],
        "source_artifact_refs": [
            disposition_memory.DEFAULT_CAMPAIGN_REPORT.as_posix(),
            disposition_memory.DEFAULT_CLOSURE_REPORT.as_posix(),
        ],
        "projected_hash": _report_hash(projected),
        "current_hash": _report_hash(current),
        "exact_next_action": (
            "write_disposition_memory_artifact"
            if _report_status(projected) == "ready"
            else "restore_disposition_memory_inputs"
        ),
    }
    if _report_status(projected) != "ready":
        row["reason_codes"] = ["disposition_memory_prerequisites_missing"]
    elif row["materialization_state"] == "current_artifact_matches_projected":
        row["reason_codes"] = ["current_artifact_already_current"]
    else:
        row["reason_codes"] = ["deterministic_write_available_from_local_inputs"]
    return row, projected


def _router_target(
    repo_root: Path,
    projected_disposition: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current = _read_json(repo_root / ROUTER_PATH)
    research_memory_payload = _read_json(repo_root / RESEARCH_MEMORY_PATH)
    projected = cycle_router._build_research_cycle_router_from_payloads(
        disposition_memory=projected_disposition,
        research_memory=research_memory_payload,
        generated_at_utc=None,
        disposition_memory_path=DISPOSITION_PATH,
    )
    row = {
        "artifact_key": "research_cycle_router",
        "artifact_path": ROUTER_PATH.as_posix(),
        "current_status": _text(cycle_router.read_research_cycle_router_status(repo_root=repo_root).get("status")),
        "projected_status": _report_status(projected),
        "materialization_state": _materialization_state(
            current_payload=current,
            projected_payload=projected,
            status_reader=_report_status,
        ),
        "reason_codes": [],
        "source_artifact_refs": [
            DISPOSITION_PATH.as_posix(),
            RESEARCH_MEMORY_PATH.as_posix(),
        ],
        "projected_hash": _report_hash(projected),
        "current_hash": _report_hash(current),
        "exact_next_action": (
            "write_research_cycle_router_artifact"
            if _report_status(projected) == "ready"
            else "restore_disposition_memory_before_router"
        ),
    }
    if _report_status(projected) != "ready":
        row["reason_codes"] = ["router_prerequisites_missing"]
    elif row["materialization_state"] == "current_artifact_matches_projected":
        row["reason_codes"] = ["current_artifact_already_current"]
    else:
        row["reason_codes"] = ["deterministic_write_available_from_local_inputs"]
    return row, projected


def _null_control_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current = _read_json(repo_root / NULL_CONTROL_PATH)
    approval_manifest = _read_json(repo_root / multiwindow_run.DEFAULT_APPROVAL_PATH)
    if not isinstance(approval_manifest, Mapping):
        projected = {
            "schema_version": null_suite.SCHEMA_VERSION,
            "report_kind": null_suite.REPORT_KIND,
            "status": "blocked_invalid_sampling_plan",
            "blocked_reasons": ["missing_multiwindow_approval_manifest"],
            "evaluation": {
                "status": "controls_not_run",
                "recommended_next_action": "restore_multiwindow_approval_manifest",
                "blockers": ["missing_multiwindow_approval_manifest"],
            },
        }
    else:
        try:
            sampling_plan_payload = multiwindow_run.build_sampling_plan_for_multiwindow_approval(
                approval_manifest=approval_manifest,
                repo_root=repo_root,
            )
            campaign_plan = multiwindow_run.build_campaign_for_multiwindow_approval(
                approval_manifest=approval_manifest,
                sampling_plan_payload=sampling_plan_payload,
            )
            projected = null_suite.build_preregistered_null_control_suite(
                sampling_plan_payload=sampling_plan_payload
            )
            projected = null_suite.evaluate_null_control_suite(
                projected,
                candidate_context={
                    "campaign_id": campaign_plan.get("campaign_id"),
                    "sampling_plan_id": sampling_plan_payload.get("sampling_plan_id"),
                },
                control_results=[],
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            projected = {
                "schema_version": null_suite.SCHEMA_VERSION,
                "report_kind": null_suite.REPORT_KIND,
                "status": "blocked_invalid_sampling_plan",
                "blocked_reasons": [f"null_control_prerequisites_unavailable:{type(exc).__name__}"],
                "evaluation": {
                    "status": "controls_not_run",
                    "recommended_next_action": "restore_sampling_plan_or_approval_inputs",
                    "blockers": ["null_control_prerequisites_unavailable"],
                },
            }
    row = {
        "artifact_key": "null_control_falsification_suite",
        "artifact_path": NULL_CONTROL_PATH.as_posix(),
        "current_status": _text(null_suite.read_null_control_suite_status(repo_root=repo_root).get("status")),
        "projected_status": _report_status(projected),
        "materialization_state": _materialization_state(
            current_payload=current,
            projected_payload=projected,
            status_reader=_report_status,
        ),
        "reason_codes": [],
        "source_artifact_refs": [
            multiwindow_run.DEFAULT_APPROVAL_PATH.as_posix(),
            multiwindow_run.DEFAULT_OUTPUT_DIR.as_posix() + "/latest.json",
        ],
        "projected_hash": _report_hash(projected),
        "current_hash": _report_hash(current),
        "exact_next_action": (
            "write_null_control_suite_artifact"
            if _report_status(projected) == "ready"
            else _text((projected.get("evaluation") or {}).get("recommended_next_action"))
            or "restore_sampling_plan_or_approval_inputs"
        ),
    }
    if _report_status(projected) != "ready":
        row["reason_codes"] = list(projected.get("blocked_reasons") or ["null_control_prerequisites_missing"])
    elif row["materialization_state"] == "current_artifact_matches_projected":
        row["reason_codes"] = ["current_artifact_already_current"]
    else:
        row["reason_codes"] = ["deterministic_write_available_from_local_inputs"]
    return row, projected


def _projected_artifact_row(
    *,
    repo_root: Path,
    artifact_key: str,
    artifact_path: Path,
    current_status: str,
    projected: Mapping[str, Any] | None,
    source_artifact_refs: list[str],
    write_action: str,
    restore_action: str,
    status_reader,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current = _read_json(repo_root / artifact_path)
    projected_status = status_reader(projected)
    row = {
        "artifact_key": artifact_key,
        "artifact_path": artifact_path.as_posix(),
        "current_status": current_status,
        "projected_status": projected_status,
        "materialization_state": _materialization_state(
            current_payload=current,
            projected_payload=projected,
            status_reader=status_reader,
        ),
        "reason_codes": [],
        "source_artifact_refs": source_artifact_refs,
        "projected_hash": _report_hash(projected),
        "current_hash": _report_hash(current),
        "exact_next_action": write_action if projected_status == "ready" else restore_action,
    }
    if projected_status != "ready":
        row["reason_codes"] = [f"{artifact_key}_prerequisites_missing"]
    elif row["materialization_state"] == "current_artifact_matches_projected":
        row["reason_codes"] = ["current_artifact_already_current"]
    else:
        row["reason_codes"] = ["deterministic_write_available_from_local_inputs"]
    return row, projected


def _breadth_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    projected = breadth_framework.build_evidence_breadth_framework(repo_root=repo_root)
    current = _read_json(repo_root / BREADTH_PATH)
    current_status = _text(current.get("status")) if isinstance(current, Mapping) else "missing_evidence_breadth_framework"
    return _projected_artifact_row(
        repo_root=repo_root,
        artifact_key="evidence_breadth_framework",
        artifact_path=BREADTH_PATH,
        current_status=current_status,
        projected=projected,
        source_artifact_refs=[DISPOSITION_PATH.as_posix(), CLOSURE_PATH.as_posix()],
        write_action="write_evidence_breadth_framework_artifact",
        restore_action="restore_evidence_breadth_prerequisites",
        status_reader=_breadth_report_status,
    )


def _lifecycle_target(
    repo_root: Path,
    *,
    projected_breadth: Mapping[str, Any] | None,
    projected_disposition: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    closure_report = _read_json(repo_root / CLOSURE_PATH) or {}
    projected = lifecycle_report.build_qre_candidate_identity_lifecycle(
        breadth_report=projected_breadth or {},
        disposition_memory=projected_disposition or {},
        closure_report=closure_report,
    )
    current = _read_json(repo_root / LIFECYCLE_PATH)
    current_summary = (
        current.get("summary")
        if isinstance(current, Mapping) and isinstance(current.get("summary"), Mapping)
        else {}
    )
    current_status = _text(current_summary.get("final_recommendation")) or "missing_candidate_identity_lifecycle"
    return _projected_artifact_row(
        repo_root=repo_root,
        artifact_key="candidate_identity_lifecycle",
        artifact_path=LIFECYCLE_PATH,
        current_status=current_status,
        projected=projected,
        source_artifact_refs=[BREADTH_PATH.as_posix(), DISPOSITION_PATH.as_posix(), CLOSURE_PATH.as_posix()],
        write_action="write_candidate_identity_lifecycle_artifact",
        restore_action="restore_candidate_lifecycle_prerequisites",
        status_reader=_lifecycle_report_status,
    )


def _quality_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    projected = quality_framework.build_candidate_quality_framework(repo_root=repo_root)
    current = _read_json(repo_root / QUALITY_PATH)
    current_summary = (
        current.get("summary")
        if isinstance(current, Mapping) and isinstance(current.get("summary"), Mapping)
        else {}
    )
    current_status = _text(current_summary.get("status")) or "missing_candidate_quality_framework"
    return _projected_artifact_row(
        repo_root=repo_root,
        artifact_key="candidate_quality_framework",
        artifact_path=QUALITY_PATH,
        current_status=current_status,
        projected=projected,
        source_artifact_refs=[
            BREADTH_PATH.as_posix(),
            LIFECYCLE_PATH.as_posix(),
            CLOSURE_PATH.as_posix(),
            NULL_CONTROL_PATH.as_posix(),
            QUALITY_REASON_CONTRACT_PATH.as_posix(),
            QUALITY_SOURCE_AUTHORITY_PATH.as_posix(),
        ],
        write_action="write_candidate_quality_framework_artifact",
        restore_action="restore_candidate_quality_prerequisites",
        status_reader=_quality_report_status,
    )


def _portfolio_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    projected = portfolio_intelligence.build_portfolio_intelligence_report(repo_root=repo_root)
    current = _read_json(repo_root / PORTFOLIO_PATH)
    current_summary = (
        current.get("summary")
        if isinstance(current, Mapping) and isinstance(current.get("summary"), Mapping)
        else {}
    )
    current_status = _text(current_summary.get("status")) or "missing_multibasket_portfolio_intelligence"
    return _projected_artifact_row(
        repo_root=repo_root,
        artifact_key="multibasket_portfolio_intelligence",
        artifact_path=PORTFOLIO_PATH,
        current_status=current_status,
        projected=projected,
        source_artifact_refs=[QUALITY_PATH.as_posix(), BREADTH_PATH.as_posix()],
        write_action="write_multibasket_portfolio_intelligence_artifact",
        restore_action="restore_multibasket_portfolio_prerequisites",
        status_reader=_portfolio_report_status,
    )


def _shadow_target(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    projected = shadow_gates.build_shadow_readiness_gates(repo_root=repo_root)
    current = _read_json(repo_root / SHADOW_PATH)
    current_summary = (
        current.get("summary")
        if isinstance(current, Mapping) and isinstance(current.get("summary"), Mapping)
        else {}
    )
    current_status = _text(current_summary.get("readiness_status")) or "missing_shadow_readiness_gates"
    return _projected_artifact_row(
        repo_root=repo_root,
        artifact_key="shadow_readiness_gates",
        artifact_path=SHADOW_PATH,
        current_status=current_status,
        projected=projected,
        source_artifact_refs=[
            BREADTH_PATH.as_posix(),
            LIFECYCLE_PATH.as_posix(),
            QUALITY_PATH.as_posix(),
            NULL_CONTROL_PATH.as_posix(),
            QUALITY_SOURCE_AUTHORITY_PATH.as_posix(),
            SHADOW_OPERATIONAL_CONTROLS_PATH.as_posix(),
            SHADOW_TRUSTED_LOOP_PATH.as_posix(),
        ],
        write_action="write_shadow_readiness_gates_artifact",
        restore_action="restore_shadow_readiness_prerequisites",
        status_reader=_shadow_report_status,
    )


def build_read_only_artifact_continuity(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    current_status = _current_status_rows(repo_root)
    disposition_row, projected_disposition = _disposition_target(repo_root)
    router_row, projected_router = _router_target(repo_root, projected_disposition)
    null_row, projected_null = _null_control_target(repo_root)
    breadth_row, projected_breadth = _breadth_target(repo_root)
    lifecycle_row, projected_lifecycle = _lifecycle_target(
        repo_root,
        projected_breadth=projected_breadth,
        projected_disposition=projected_disposition,
    )
    quality_row, projected_quality = _quality_target(repo_root)
    portfolio_row, projected_portfolio = _portfolio_target(repo_root)
    shadow_row, projected_shadow = _shadow_target(repo_root)
    rows = [
        disposition_row,
        router_row,
        null_row,
        breadth_row,
        lifecycle_row,
        quality_row,
        portfolio_row,
        shadow_row,
    ]
    ready_rows = [row for row in rows if row["projected_status"] == "ready"]
    blocked_rows = [row for row in rows if row["projected_status"] != "ready"]
    current_rows = [row for row in rows if row["materialization_state"] == "current_artifact_matches_projected"]
    materializable_rows = [
        row
        for row in rows
        if row["materialization_state"] in {
            "materializable_missing_current_artifact",
            "materializable_stale_or_mismatched_current_artifact",
        }
    ]
    summary = {
        "artifact_continuity_ready": len(blocked_rows) == 0,
        "target_count": len(rows),
        "ready_target_count": len(ready_rows),
        "blocked_target_count": len(blocked_rows),
        "current_target_count": len(current_rows),
        "materializable_target_count": len(materializable_rows),
        "exact_next_action": (
            "materialize_read_only_qre_artifacts"
            if materializable_rows and not blocked_rows
            else "restore_read_only_artifact_prerequisites"
            if blocked_rows
            else "preserve_current_read_only_artifacts"
        ),
        "operator_summary": (
            "Read-only artifact continuity verifies whether implemented QRE routing, breadth, "
            "lifecycle, quality, portfolio, null-control, and shadow-gate surfaces are currently "
            "materialized from local inputs. It never creates evidence authority or runtime execution authority."
        ),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": summary,
        "current_status": current_status,
        "targets": rows,
        "projected_reports": {
            "hypothesis_disposition_memory": {
                "status": _text(projected_disposition.get("status")),
                "hash": _report_hash(projected_disposition),
            },
            "research_cycle_router": {
                "status": _text(projected_router.get("status")),
                "hash": _report_hash(projected_router),
            },
            "null_control_falsification_suite": {
                "status": _text(projected_null.get("status")),
                "hash": _report_hash(projected_null),
            },
            "evidence_breadth_framework": {
                "status": _text(projected_breadth.get("status")),
                "hash": _report_hash(projected_breadth),
            },
            "candidate_identity_lifecycle": {
                "status": _text(((projected_lifecycle.get("summary") or {}).get("final_recommendation"))),
                "hash": _report_hash(projected_lifecycle),
            },
            "candidate_quality_framework": {
                "status": _text(((projected_quality.get("summary") or {}).get("status"))),
                "hash": _report_hash(projected_quality),
            },
            "multibasket_portfolio_intelligence": {
                "status": _text(((projected_portfolio.get("summary") or {}).get("status"))),
                "hash": _report_hash(projected_portfolio),
            },
            "shadow_readiness_gates": {
                "status": _text(((projected_shadow.get("summary") or {}).get("readiness_status"))),
                "hash": _report_hash(projected_shadow),
            },
        },
        "authority_boundary": {
            "read_only": True,
            "operator_review_required": True,
            "can_authorize_execution": False,
            "can_clear_evidence_blockers": False,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
        },
        "safety_invariants": {
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "schema_version": report["schema_version"],
            "report_kind": report["report_kind"],
            "summary": report["summary"],
            "current_status": report["current_status"],
            "targets": report["targets"],
            "projected_reports": report["projected_reports"],
            "authority_boundary": report["authority_boundary"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    targets = report.get("targets") if isinstance(report.get("targets"), list) else []
    lines = [
        "# QRE Read-Only Artifact Continuity",
        "",
        f"- artifact_continuity_ready: {summary.get('artifact_continuity_ready', False)}",
        f"- target_count: {summary.get('target_count', 0)}",
        f"- ready_target_count: {summary.get('ready_target_count', 0)}",
        f"- blocked_target_count: {summary.get('blocked_target_count', 0)}",
        f"- materializable_target_count: {summary.get('materializable_target_count', 0)}",
        f"- exact_next_action: {summary.get('exact_next_action', '')}",
        "",
        "## Targets",
    ]
    for row in targets:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('artifact_key')}: {row.get('materialization_state')} "
            f"(current={row.get('current_status')}, projected={row.get('projected_status')})"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    disposition_report = disposition_memory.build_hypothesis_disposition_memory(repo_root=repo_root)
    if _report_status(disposition_report) == "ready":
        disposition_memory.write_outputs(disposition_report, repo_root=repo_root)

    research_memory_payload = _read_json(repo_root / RESEARCH_MEMORY_PATH)
    router_report = cycle_router._build_research_cycle_router_from_payloads(
        disposition_memory=disposition_report,
        research_memory=research_memory_payload,
        generated_at_utc=None,
        disposition_memory_path=DISPOSITION_PATH,
    )
    if _report_status(router_report) == "ready":
        cycle_router.write_outputs(router_report, repo_root=repo_root)

    approval_manifest = _read_json(repo_root / multiwindow_run.DEFAULT_APPROVAL_PATH)
    if isinstance(approval_manifest, Mapping):
        try:
            sampling_plan_payload = multiwindow_run.build_sampling_plan_for_multiwindow_approval(
                approval_manifest=approval_manifest,
                repo_root=repo_root,
            )
            campaign_plan = multiwindow_run.build_campaign_for_multiwindow_approval(
                approval_manifest=approval_manifest,
                sampling_plan_payload=sampling_plan_payload,
            )
            null_report = null_suite.build_preregistered_null_control_suite(
                sampling_plan_payload=sampling_plan_payload
            )
            null_report = null_suite.evaluate_null_control_suite(
                null_report,
                candidate_context={
                    "campaign_id": campaign_plan.get("campaign_id"),
                    "sampling_plan_id": sampling_plan_payload.get("sampling_plan_id"),
                },
                control_results=[],
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            null_report = None
        if _report_status(null_report) == "ready":
            null_suite.write_outputs(null_report, repo_root=repo_root)

    breadth_report = breadth_framework.build_evidence_breadth_framework(repo_root=repo_root)
    if _breadth_report_status(breadth_report) == "ready":
        breadth_framework.write_outputs(breadth_report, repo_root=repo_root)

    closure_report = _read_json(repo_root / CLOSURE_PATH) or {}
    lifecycle_payload = lifecycle_report.build_qre_candidate_identity_lifecycle(
        breadth_report=breadth_report,
        disposition_memory=disposition_report,
        closure_report=closure_report,
    )
    if _lifecycle_report_status(lifecycle_payload) == "ready":
        lifecycle_report.write_outputs(lifecycle_payload, repo_root=repo_root)

    quality_report = quality_framework.build_candidate_quality_framework(repo_root=repo_root)
    if _quality_report_status(quality_report) == "ready":
        quality_framework.write_outputs(quality_report, repo_root=repo_root)

    portfolio_report = portfolio_intelligence.build_portfolio_intelligence_report(repo_root=repo_root)
    if _portfolio_report_status(portfolio_report) == "ready":
        portfolio_intelligence.write_outputs(portfolio_report, repo_root=repo_root)

    shadow_report = shadow_gates.build_shadow_readiness_gates(repo_root=repo_root)
    if _shadow_report_status(shadow_report) == "ready":
        shadow_gates.write_outputs(shadow_report, repo_root=repo_root)

    refreshed = build_read_only_artifact_continuity(repo_root=repo_root)
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(refreshed) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_read_only_artifact_continuity",
        description="Materialize deterministic read-only continuity for QRE artifact-backed memory and control surfaces.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_read_only_artifact_continuity()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
