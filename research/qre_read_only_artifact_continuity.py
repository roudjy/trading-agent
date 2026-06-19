from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_hypothesis_disposition_memory as disposition_memory
from research import qre_null_control_falsification_suite as null_suite
from research import qre_preregistered_multiwindow_evidence_run as multiwindow_run
from research import qre_research_cycle_router as cycle_router


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


def _materialization_state(
    *,
    current_payload: Mapping[str, Any] | None,
    projected_payload: Mapping[str, Any] | None,
) -> str:
    if _report_status(projected_payload) != "ready":
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


def build_read_only_artifact_continuity(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    current_status = _current_status_rows(repo_root)
    disposition_row, projected_disposition = _disposition_target(repo_root)
    router_row, projected_router = _router_target(repo_root, projected_disposition)
    null_row, projected_null = _null_control_target(repo_root)
    rows = [disposition_row, router_row, null_row]
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
            "Read-only artifact continuity verifies whether implemented QRE memory, routing, "
            "and null-control surfaces are currently materialized from local inputs. It never "
            "creates evidence authority or runtime execution authority."
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
