from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data.source_quality_readiness import read_source_quality_status
from research.qre_candidate_quality_framework import build_candidate_quality_framework
from research.qre_candidate_identity_lifecycle import build_qre_candidate_identity_lifecycle
from research.qre_evidence_breadth_framework import build_evidence_breadth_framework
from research.qre_trusted_loop_operational_controls import (
    build_trusted_loop_operational_controls,
)


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_shadow_readiness_gates"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_shadow_readiness_gates")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_shadow_readiness_gates/"

QUALITY_PATH: Final[Path] = Path("logs/qre_candidate_quality_framework/latest.json")
BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
NULL_CONTROL_PATH: Final[Path] = Path("logs/qre_null_control_falsification_suite/latest.json")
LIFECYCLE_PATH: Final[Path] = Path("logs/qre_candidate_identity_lifecycle/latest.json")
OPERATIONAL_CONTROLS_PATH: Final[Path] = Path("logs/qre_trusted_loop_operational_controls/latest.json")
TRUSTED_LOOP_REVIEW_PATH: Final[Path] = Path("logs/qre_trusted_loop_review/latest.json")
DISPOSITION_MEMORY_PATH: Final[Path] = Path("logs/qre_hypothesis_disposition_memory/latest.json")
MULTIWINDOW_CLOSURE_PATH: Final[Path] = Path("logs/qre_multiwindow_evidence_closure/latest.json")


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


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_breadth_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / BREADTH_PATH) or build_evidence_breadth_framework(repo_root=repo_root)


def _load_quality_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / QUALITY_PATH) or build_candidate_quality_framework(repo_root=repo_root)


def _load_null_control_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / NULL_CONTROL_PATH) or {}


def _load_lifecycle_report(repo_root: Path) -> dict[str, Any]:
    persisted = _read_json(repo_root / LIFECYCLE_PATH)
    if persisted is not None:
        return persisted
    breadth_report = _load_breadth_report(repo_root)
    disposition_memory = _read_json(repo_root / DISPOSITION_MEMORY_PATH) or {}
    closure_report = _read_json(repo_root / MULTIWINDOW_CLOSURE_PATH) or {}
    return build_qre_candidate_identity_lifecycle(
        breadth_report=breadth_report,
        disposition_memory=disposition_memory,
        closure_report=closure_report,
    )


def _load_operational_controls(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / OPERATIONAL_CONTROLS_PATH) or build_trusted_loop_operational_controls(
        repo_root=repo_root
    )


def _load_trusted_loop_review(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / TRUSTED_LOOP_REVIEW_PATH) or {}


def _prerequisite_state(
    *,
    breadth_report: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    null_control_report: Mapping[str, Any],
    lifecycle_report: Mapping[str, Any],
    source_quality_status: Mapping[str, Any],
    operational_controls_report: Mapping[str, Any],
    trusted_loop_review: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    breadth_summary = breadth_report.get("summary") if isinstance(breadth_report.get("summary"), Mapping) else {}
    quality_summary = quality_report.get("summary") if isinstance(quality_report.get("summary"), Mapping) else {}
    lifecycle_summary = (
        lifecycle_report.get("summary") if isinstance(lifecycle_report.get("summary"), Mapping) else {}
    )
    null_evaluation = (
        null_control_report.get("evaluation")
        if isinstance(null_control_report.get("evaluation"), Mapping)
        else {}
    )
    null_summary_status = _text(null_control_report.get("status"))
    operational_summary = (
        operational_controls_report.get("summary")
        if isinstance(operational_controls_report.get("summary"), Mapping)
        else {}
    )
    review_summary = (
        trusted_loop_review.get("summary")
        if isinstance(trusted_loop_review.get("summary"), Mapping)
        else {}
    )
    accepted_oos_count = int(breadth_summary.get("accepted_oos_ref_count") or 0)
    evidence_complete_count = int(lifecycle_summary.get("evidence_complete_count") or 0)
    quality_ready_count = int(quality_summary.get("eligible_candidate_count") or 0)
    null_complete = _text(null_evaluation.get("status")) == "controls_passed_context_only"
    review_present = bool(review_summary)

    return {
        "evidence_breadth": {
            "passed": breadth_summary.get("status") == "ready" or breadth_report.get("status") == "ready",
            "observed": breadth_summary.get("status") or breadth_report.get("status"),
            "source_ref": BREADTH_PATH.as_posix(),
        },
        "evidence_complete_scopes": {
            "passed": evidence_complete_count > 0,
            "observed": evidence_complete_count,
            "source_ref": LIFECYCLE_PATH.as_posix(),
        },
        "candidate_lifecycle": {
            "passed": int(lifecycle_summary.get("candidate_count") or 0) > 0,
            "observed": lifecycle_summary.get("status_counts") or {},
            "source_ref": LIFECYCLE_PATH.as_posix(),
        },
        "candidate_quality": {
            "passed": quality_ready_count > 0,
            "observed": quality_summary.get("status"),
            "source_ref": QUALITY_PATH.as_posix(),
        },
        "null_controls": {
            "passed": null_complete,
            "observed": _text(null_evaluation.get("status")) or null_summary_status or "missing",
            "source_ref": NULL_CONTROL_PATH.as_posix(),
        },
        "accepted_oos": {
            "passed": accepted_oos_count > 0,
            "observed": accepted_oos_count,
            "source_ref": BREADTH_PATH.as_posix(),
        },
        "source_quality": {
            "passed": bool(source_quality_status.get("research_ready")),
            "observed": source_quality_status.get("status"),
            "source_ref": "logs/qre_data_source_quality_readiness/latest.json",
        },
        "replayability": {
            "passed": bool((operational_summary.get("trusted_loop_operational_controls_ready"))),
            "observed": (operational_controls_report.get("replayability") or {}).get(
                "rerun_comparison_ready"
            ),
            "source_ref": OPERATIONAL_CONTROLS_PATH.as_posix(),
        },
        "resumability": {
            "passed": bool((operational_controls_report.get("resumability") or {}).get("idempotent_reentry_ready")),
            "observed": (operational_controls_report.get("resumability") or {}).get("resumable"),
            "source_ref": OPERATIONAL_CONTROLS_PATH.as_posix(),
        },
        "trusted_loop_status": {
            "passed": review_present,
            "observed": review_summary.get("trust_verdict"),
            "source_ref": TRUSTED_LOOP_REVIEW_PATH.as_posix(),
        },
        "auditability": {
            "passed": review_present and bool(review_summary.get("trust_blocker_count") is not None),
            "observed": review_summary.get("final_recommendation"),
            "source_ref": TRUSTED_LOOP_REVIEW_PATH.as_posix(),
        },
        "operator_approval": {
            "passed": False,
            "observed": "not_present",
            "source_ref": "operator_approval_not_materialized",
        },
        "critical_blockers": {
            "passed": False,
            "observed": [],
            "source_ref": "derived_from_prerequisite_failures",
        },
    }


def _blockers(prerequisites: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    mapping = {
        "evidence_breadth": "evidence_breadth_incomplete",
        "evidence_complete_scopes": "evidence_complete_scope_missing",
        "candidate_lifecycle": "candidate_lifecycle_missing",
        "candidate_quality": "candidate_quality_not_ready",
        "null_controls": "null_controls_incomplete",
        "accepted_oos": "accepted_oos_missing",
        "source_quality": "source_quality_not_ready",
        "replayability": "trusted_loop_replayability_incomplete",
        "resumability": "trusted_loop_resumability_incomplete",
        "trusted_loop_status": "trusted_loop_status_missing",
        "auditability": "auditability_incomplete",
        "operator_approval": "operator_shadow_approval_missing",
    }
    rows: list[dict[str, Any]] = []
    for key, prerequisite in prerequisites.items():
        if key == "critical_blockers":
            continue
        if prerequisite.get("passed") is True:
            continue
        rows.append(
            {
                "blocker_code": mapping[key],
                "prerequisite_id": key,
                "observed": prerequisite.get("observed"),
                "source_ref": prerequisite.get("source_ref"),
            }
        )
    return rows


def _next_action(blockers: Sequence[Mapping[str, Any]]) -> str:
    blocker_codes = [str(row.get("blocker_code")) for row in blockers]
    if "accepted_oos_missing" in blocker_codes or "evidence_complete_scope_missing" in blocker_codes:
        return "produce_accepted_oos_and_evidence_complete_scope"
    if "candidate_quality_not_ready" in blocker_codes:
        return "satisfy_candidate_quality_prerequisites"
    if "null_controls_incomplete" in blocker_codes:
        return "complete_preregistered_null_controls"
    if (
        "trusted_loop_replayability_incomplete" in blocker_codes
        or "trusted_loop_resumability_incomplete" in blocker_codes
    ):
        return "stabilize_trusted_loop_operational_controls"
    if "operator_shadow_approval_missing" in blocker_codes:
        return "retain_read_only_mode_until_explicit_operator_shadow_approval"
    return "maintain_fail_closed_shadow_deferral"


def _reason_record(
    *,
    blocker_codes: Sequence[str],
    evidence_refs: Sequence[str],
    next_action: str,
) -> dict[str, Any]:
    payload = {
        "record_id": "rr_qre_shadow_readiness_deferral",
        "record_kind": "qre_shadow_readiness_deferral",
        "subject_id": "qre_shadow_readiness",
        "reason_codes": list(blocker_codes),
        "reason_text": (
            "Shadow readiness remains deferred. All activation flags stay false until evidence breadth, "
            "accepted OOS, candidate quality, null-control completion, trusted-loop controls, auditability, "
            "and explicit operator approval are all present."
        ),
        "evidence_refs": list(dict.fromkeys(_text(value) for value in evidence_refs if _text(value))),
        "recommended_next_action": next_action,
        "accepted_evidence": False,
        "operator_review_required": True,
    }
    payload["deterministic_hash"] = _digest(payload)
    return payload


def build_shadow_readiness_gates(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    breadth_report = _load_breadth_report(repo_root)
    quality_report = _load_quality_report(repo_root)
    null_control_report = _load_null_control_report(repo_root)
    lifecycle_report = _load_lifecycle_report(repo_root)
    source_quality_status = read_source_quality_status(repo_root=repo_root)
    operational_controls_report = _load_operational_controls(repo_root)
    trusted_loop_review = _load_trusted_loop_review(repo_root)

    prerequisites = _prerequisite_state(
        breadth_report=breadth_report,
        quality_report=quality_report,
        null_control_report=null_control_report,
        lifecycle_report=lifecycle_report,
        source_quality_status=source_quality_status,
        operational_controls_report=operational_controls_report,
        trusted_loop_review=trusted_loop_review,
    )
    blockers = _blockers(prerequisites)
    next_action = _next_action(blockers)
    blocker_codes = [str(row["blocker_code"]) for row in blockers]
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "readiness_status": (
                "shadow_readiness_prerequisites_satisfied_context_only"
                if not blockers
                else "shadow_readiness_deferred"
            ),
            "shadow_ready": False,
            "can_activate_shadow": False,
            "can_activate_paper": False,
            "can_activate_live": False,
            "blocker_count": len(blockers),
            "exact_next_action": next_action,
            "operator_summary": (
                "Shadow readiness remains a read-only deferral gate. Activation stays disabled even when some "
                "prerequisites improve, and explicit later authority would still be required."
            ),
        },
        "prerequisite_state": prerequisites,
        "blockers": blockers,
        "reason_records": [
            _reason_record(
                blocker_codes=blocker_codes,
                evidence_refs=[row.get("source_ref") for row in blockers],
                next_action=next_action,
            )
        ],
        "authority_classification": {
            "read_only_deferral_gate": True,
            "operator_approval_materialized": False,
            "can_activate_shadow": False,
            "can_activate_paper": False,
            "can_activate_live": False,
            "deployment_authority": "forbidden",
        },
        "supporting_reports": {
            "breadth_report_kind": breadth_report.get("report_kind"),
            "quality_report_kind": quality_report.get("report_kind"),
            "null_control_report_kind": null_control_report.get("report_kind"),
            "lifecycle_report_kind": lifecycle_report.get("report_kind"),
            "operational_controls_report_kind": operational_controls_report.get("report_kind"),
            "trusted_loop_review_kind": trusted_loop_review.get("report_kind"),
            "source_quality_status": dict(source_quality_status),
        },
        "safety_invariants": {
            "read_only": True,
            "shadow_ready_forced_false": True,
            "paper_ready_forced_false": True,
            "live_ready_forced_false": True,
            "candidate_promotion_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "protected_runtime_paths_untouched": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    lines = [
        "# QRE Shadow Readiness Gates",
        "",
        f"- readiness_status: {summary.get('readiness_status') or 'unknown'}",
        f"- shadow_ready: {summary.get('shadow_ready')}",
        f"- can_activate_shadow: {summary.get('can_activate_shadow')}",
        f"- can_activate_paper: {summary.get('can_activate_paper')}",
        f"- can_activate_live: {summary.get('can_activate_live')}",
        f"- exact_next_action: {summary.get('exact_next_action') or 'unknown'}",
        "",
        "## Blockers",
    ]
    for blocker in blockers:
        if not isinstance(blocker, Mapping):
            continue
        lines.append(
            f"- {blocker.get('blocker_code')} observed={blocker.get('observed')} source_ref={blocker.get('source_ref')}"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": _rel(latest, root=repo_root),
        "operator_summary": _rel(summary_path, root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_shadow_readiness_gates",
        description="Build read-only QRE shadow readiness deferral gates.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_shadow_readiness_gates()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
