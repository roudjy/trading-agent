from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research.run_state import _pid_is_live


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_trusted_loop_operational_controls"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_trusted_loop_operational_controls")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_trusted_loop_operational_controls/"

RUN_STATE_PATH: Final[Path] = Path("research/run_state.v1.json")
RUN_MANIFEST_PATH: Final[Path] = Path("research/run_manifest_latest.v1.json")
RUN_PROGRESS_PATH: Final[Path] = Path("research/run_progress_latest.v1.json")
RESEARCH_STATE_PATH: Final[Path] = Path("research/research_state_latest.v1.json")
TRUSTED_LOOP_REVIEW_PATH: Final[Path] = Path("logs/qre_trusted_loop_review/latest.json")
HISTORY_ROOT: Final[Path] = Path("research/history")


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
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _bool(value: Any) -> bool:
    return value is True


def _history_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = repo_root / HISTORY_ROOT
    if not base.is_dir():
        return rows
    for run_dir in sorted((path for path in base.iterdir() if path.is_dir()), key=lambda item: item.name):
        manifest = _read_json(run_dir / "run_manifest.v1.json")
        state = _read_json(run_dir / "run_state.v1.json")
        progress = _read_json(run_dir / "run_progress.v1.json")
        resume_sidecars = list(run_dir.glob("batches/*/candidate_resume/*.v1.json"))
        run_id = (
            _text((manifest or {}).get("run_id"))
            or _text((state or {}).get("run_id"))
            or run_dir.name
        )
        rows.append(
            {
                "run_id": run_id,
                "status": _text((state or {}).get("status")) or _text((manifest or {}).get("status")) or "unknown",
                "git_revision": _text((manifest or {}).get("git_revision")),
                "config_hash": _text((manifest or {}).get("config_hash")),
                "manifest": manifest or {},
                "state": state or {},
                "progress": progress or {},
                "resume_sidecar_count": len(resume_sidecars),
                "path": _rel(run_dir, root=repo_root),
            }
        )
    rows.sort(key=lambda row: str(row["run_id"]))
    return rows


def _latest_history_row(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return rows[-1] if rows else None


def _execution_identity(
    manifest: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    payload = {
        "run_id": _text(manifest.get("run_id")) or _text(state.get("run_id")),
        "git_revision": _text(manifest.get("git_revision")),
        "config_hash": _text(manifest.get("config_hash")),
        "feature_version": _text(manifest.get("feature_version")),
        "evaluation_version": _text(manifest.get("evaluation_version")),
        "lifecycle_mode": _text(manifest.get("lifecycle_mode")),
        "resumed_from_run_id": manifest.get("resumed_from_run_id"),
    }
    payload["execution_identity_hash"] = _digest(payload)
    payload["input_hash"] = _text(manifest.get("config_hash")) or None
    payload["code_version_hash"] = (
        _digest(
            {
                "git_revision": payload["git_revision"],
                "feature_version": payload["feature_version"],
                "evaluation_version": payload["evaluation_version"],
            }
        )
        if payload["git_revision"] or payload["feature_version"] or payload["evaluation_version"]
        else None
    )
    return payload


def _artifact_set_hash(repo_root: Path) -> dict[str, Any]:
    files = {
        "run_state": repo_root / RUN_STATE_PATH,
        "run_manifest": repo_root / RUN_MANIFEST_PATH,
        "run_progress": repo_root / RUN_PROGRESS_PATH,
        "research_state": repo_root / RESEARCH_STATE_PATH,
        "trusted_loop_review": repo_root / TRUSTED_LOOP_REVIEW_PATH,
    }
    digests = {
        key: digest
        for key, path in files.items()
        if (digest := _file_digest(path)) is not None
    }
    return {
        "artifact_count": len(digests),
        "artifact_digests": digests,
        "artifact_set_hash": _digest(digests) if digests else None,
    }


def _state_reconciliation(
    *,
    manifest: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    progress: Mapping[str, Any] | None,
    latest_history: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    progress = progress or {}
    run_ids = {
        "manifest_run_id": _text(manifest.get("run_id")),
        "state_run_id": _text(state.get("run_id")),
        "progress_run_id": _text(progress.get("run_id")),
        "latest_history_run_id": _text((latest_history or {}).get("run_id")),
    }
    latest_ids = [value for value in run_ids.values() if value]
    aligned = len(set(latest_ids[:3])) <= 1 if latest_ids[:3] else False
    status_values = {
        "manifest_status": _text(manifest.get("status")),
        "state_status": _text(state.get("status")),
        "progress_status": _text(progress.get("status")),
    }
    non_empty_statuses = [value for value in status_values.values() if value]
    status_aligned = len(set(non_empty_statuses)) <= 1 if non_empty_statuses else False
    latest_current_run_id = run_ids["manifest_run_id"] or run_ids["state_run_id"] or run_ids["progress_run_id"]
    superseded = bool(
        latest_current_run_id
        and run_ids["latest_history_run_id"]
        and latest_current_run_id != run_ids["latest_history_run_id"]
    )
    mismatches: list[str] = []
    if not aligned:
        mismatches.append("run_id_mismatch")
    if not status_aligned:
        mismatches.append("status_mismatch")
    if superseded:
        mismatches.append("latest_artifacts_superseded_by_history")
    if not latest_current_run_id:
        mismatches.append("missing_current_run_artifacts")
    return {
        "status": "reconciled" if not mismatches else "reconciliation_required",
        "run_ids": run_ids,
        "statuses": status_values,
        "current_artifacts_aligned": aligned,
        "status_fields_aligned": status_aligned,
        "superseded_artifacts_detected": superseded,
        "mismatches": mismatches,
    }


def _current_run_classification(
    *,
    manifest: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    progress: Mapping[str, Any] | None,
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    progress = progress or {}
    state_status = _text(state.get("status"))
    pid = state.get("pid") if isinstance(state.get("pid"), int) else None
    pid_live = _pid_is_live(pid)
    progress_total = int(progress.get("total_items") or 0)
    progress_completed = int(progress.get("completed_items") or 0)
    failed_items = int(progress.get("failed_items") or 0)
    if not manifest and not state and not progress:
        status = "missing_current_artifacts"
    elif state_status == "running" and pid_live:
        status = "running_active"
    elif state_status == "running" and not pid_live:
        status = "running_stale"
    elif _bool(reconciliation.get("superseded_artifacts_detected")):
        status = "stale_latest_artifacts"
    elif state_status in {"failed", "aborted"} and (failed_items > 0 or progress_completed < progress_total):
        status = "failed_resumable"
    elif state_status in {"failed", "aborted"}:
        status = "failed_terminal"
    elif state_status == "completed":
        status = "completed_terminal"
    else:
        status = "reconciliation_required"
    return {
        "status": status,
        "pid_live": pid_live,
        "state_status": state_status or _text(manifest.get("status")) or "unknown",
        "progress_total": progress_total,
        "progress_completed": progress_completed,
        "failed_items": failed_items,
        "status_reason": _text(state.get("status_reason")),
        "error_type": _text((state.get("error") or {}).get("error_type"))
        if isinstance(state.get("error"), Mapping)
        else "",
        "error_message": _text((state.get("error") or {}).get("error_message"))
        if isinstance(state.get("error"), Mapping)
        else "",
    }


def _replayability(
    *,
    execution_identity: Mapping[str, Any],
    history_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    identity_hash = _text(execution_identity.get("execution_identity_hash"))
    input_hash = _text(execution_identity.get("input_hash"))
    same_identity = [
        row
        for row in history_rows
        if _digest(
            {
                "run_id": _text((row.get("manifest") or {}).get("run_id")) or _text((row.get("state") or {}).get("run_id")),
                "git_revision": _text(row.get("git_revision")),
                "config_hash": _text(row.get("config_hash")),
                "feature_version": _text((row.get("manifest") or {}).get("feature_version")),
                "evaluation_version": _text((row.get("manifest") or {}).get("evaluation_version")),
                "lifecycle_mode": _text((row.get("manifest") or {}).get("lifecycle_mode")),
                "resumed_from_run_id": (row.get("manifest") or {}).get("resumed_from_run_id"),
            }
        )
        == identity_hash
    ]
    same_input = [row for row in history_rows if _text(row.get("config_hash")) and _text(row.get("config_hash")) == input_hash]
    return {
        "replay_manifest_ready": bool(identity_hash and input_hash),
        "same_execution_identity_count": len(same_identity),
        "same_input_history_count": len(same_input),
        "duplicate_run_suppressed": len(same_identity) > 1,
        "history_status_counts": dict(
            sorted(Counter(_text(row.get("status")) or "unknown" for row in same_input).items())
        ),
        "rerun_comparison_ready": len(same_input) > 0,
    }


def _resumability(
    *,
    manifest: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    current_run: Mapping[str, Any],
    history_rows: Sequence[Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    current_run_id = _text(manifest.get("run_id")) or _text(state.get("run_id"))
    history_row = next((row for row in history_rows if _text(row.get("run_id")) == current_run_id), None)
    resume_sidecar_count = int((history_row or {}).get("resume_sidecar_count") or 0)
    recovery_policy = manifest.get("recovery_policy") if isinstance(manifest.get("recovery_policy"), Mapping) else {}
    resumable_status = current_run.get("status") in {"running_stale", "failed_resumable"}
    if current_run.get("status") == "failed_resumable" and not recovery_policy:
        resumable_status = False
    return {
        "resumable": resumable_status,
        "resume_sidecar_count": resume_sidecar_count,
        "recovery_policy_present": bool(recovery_policy),
        "history_checkpoint_present": history_row is not None,
        "idempotent_reentry_ready": _bool(reconciliation.get("current_artifacts_aligned"))
        and _bool(reconciliation.get("status_fields_aligned")),
        "checkpoint_manifest_ref": (
            f"{history_row['path']}/run_manifest.v1.json" if history_row else None
        ),
    }


def _artifact_freshness(
    *,
    repo_root: Path,
    latest_history: Mapping[str, Any] | None,
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    current_paths = {
        "run_state": repo_root / RUN_STATE_PATH,
        "run_manifest": repo_root / RUN_MANIFEST_PATH,
        "run_progress": repo_root / RUN_PROGRESS_PATH,
    }
    present = {name: path.is_file() for name, path in current_paths.items()}
    missing = sorted(name for name, exists in present.items() if not exists)
    stale = list(reconciliation.get("mismatches") or [])
    return {
        "status": "fresh" if not missing and not stale else "stale_or_missing",
        "present_artifacts": present,
        "missing_artifacts": missing,
        "stale_reasons": stale,
        "latest_history_run_id": _text((latest_history or {}).get("run_id")) or None,
    }


def _next_safe_action(
    *,
    current_run: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    replayability: Mapping[str, Any],
    resumability: Mapping[str, Any],
) -> str:
    if current_run.get("status") == "running_active":
        return "wait_for_active_run_completion"
    if current_run.get("status") in {"running_stale", "stale_latest_artifacts"}:
        return "reconcile_stale_or_mismatched_run_artifacts"
    if _bool(resumability.get("resumable")):
        return "resume_from_existing_run_history"
    if _bool(replayability.get("duplicate_run_suppressed")):
        return "suppress_duplicate_rerun_and_compare_history"
    if current_run.get("status") == "completed_terminal":
        return "preserve_terminal_run_and_compare_before_rerun"
    if "missing_current_run_artifacts" in list(reconciliation.get("mismatches") or []):
        return "inspect_missing_run_artifacts"
    return "operator_review_required_before_retry"


def build_trusted_loop_operational_controls(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    manifest = _read_json(repo_root / RUN_MANIFEST_PATH)
    state = _read_json(repo_root / RUN_STATE_PATH)
    progress = _read_json(repo_root / RUN_PROGRESS_PATH)
    research_state = _read_json(repo_root / RESEARCH_STATE_PATH)
    trusted_loop_review = _read_json(repo_root / TRUSTED_LOOP_REVIEW_PATH)
    history_rows = _history_rows(repo_root)
    latest_history = _latest_history_row(history_rows)
    execution_identity = _execution_identity(manifest, state)
    reconciliation = _state_reconciliation(
        manifest=manifest,
        state=state,
        progress=progress,
        latest_history=latest_history,
    )
    current_run = _current_run_classification(
        manifest=manifest,
        state=state,
        progress=progress,
        reconciliation=reconciliation,
    )
    replayability = _replayability(
        execution_identity=execution_identity,
        history_rows=history_rows,
    )
    resumability = _resumability(
        manifest=manifest,
        state=state,
        current_run=current_run,
        history_rows=history_rows,
        reconciliation=reconciliation,
    )
    freshness = _artifact_freshness(
        repo_root=repo_root,
        latest_history=latest_history,
        reconciliation=reconciliation,
    )
    next_safe_action = _next_safe_action(
        current_run=current_run,
        reconciliation=reconciliation,
        replayability=replayability,
        resumability=resumability,
    )
    failure_retry_reasons = {
        "status_reason": _text(current_run.get("status_reason")) or None,
        "error_type": _text(current_run.get("error_type")) or None,
        "error_message": _text(current_run.get("error_message")) or None,
        "research_next_best_test": _text((research_state or {}).get("next_best_test")) or None,
    }
    checkpoint_manifest = {
        "run_id": _text((manifest or {}).get("run_id")) or None,
        "lifecycle_mode": _text((manifest or {}).get("lifecycle_mode")) or None,
        "resumed_from_run_id": (manifest or {}).get("resumed_from_run_id"),
        "continuation_summary": dict((manifest or {}).get("continuation_summary") or {}),
        "history_run_count": len(history_rows),
        "history_checkpoint_count": sum(1 for row in history_rows if row.get("manifest") and row.get("state")),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": current_run["status"],
            "trusted_loop_operational_controls_ready": (
                current_run["status"] in {"completed_terminal", "failed_terminal", "failed_resumable"}
                and reconciliation["status"] == "reconciled"
                and freshness["status"] == "fresh"
            ),
            "current_run_status": current_run["status"],
            "resumable": resumability["resumable"],
            "duplicate_run_suppressed": replayability["duplicate_run_suppressed"],
            "reconciliation_status": reconciliation["status"],
            "artifact_freshness_status": freshness["status"],
            "exact_next_safe_action": next_safe_action,
            "operator_summary": (
                "Trusted-loop operational controls reconcile latest run artifacts, history checkpoints, "
                "resume sidecars, and replay comparators without mutating runtime state."
            ),
        },
        "execution_identity": execution_identity,
        "artifact_set": _artifact_set_hash(repo_root),
        "checkpoint_manifest": checkpoint_manifest,
        "state_reconciliation": reconciliation,
        "current_run": current_run,
        "resumability": resumability,
        "replayability": replayability,
        "artifact_freshness": freshness,
        "failure_retry_reason_records": failure_retry_reasons,
        "supporting_context": {
            "research_state_summary": {
                "hypothesis_state": _text((research_state or {}).get("hypothesis_state")) or None,
                "policy_state": _text((research_state or {}).get("policy_state")) or None,
                "synthesis_gate": _text((research_state or {}).get("synthesis_gate")) or None,
                "next_best_test": _text((research_state or {}).get("next_best_test")) or None,
            },
            "trusted_loop_review_summary": dict((trusted_loop_review or {}).get("summary") or {}),
            "history_paths": [str(row["path"]) for row in history_rows[-5:]],
        },
        "authority": {
            "read_only": True,
            "context_only": True,
            "can_resume_runtime_directly": False,
            "can_replay_runtime_directly": False,
            "can_overwrite_artifacts": False,
            "can_promote_candidate": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "no_silent_overwrite": True,
            "duplicate_run_suppression_context_only": True,
            "candidate_promotion_forbidden": True,
            "shadow_paper_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    current_run = report.get("current_run") if isinstance(report.get("current_run"), Mapping) else {}
    resumability = report.get("resumability") if isinstance(report.get("resumability"), Mapping) else {}
    replayability = report.get("replayability") if isinstance(report.get("replayability"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Trusted-Loop Operational Controls",
            "",
            f"- status: {summary.get('status') or 'unknown'}",
            f"- trusted_loop_operational_controls_ready: {summary.get('trusted_loop_operational_controls_ready')}",
            f"- exact_next_safe_action: {summary.get('exact_next_safe_action')}",
            f"- reconciliation_status: {summary.get('reconciliation_status')}",
            f"- artifact_freshness_status: {summary.get('artifact_freshness_status')}",
            f"- resumable: {resumability.get('resumable')}",
            f"- duplicate_run_suppressed: {replayability.get('duplicate_run_suppressed')}",
            f"- current_run_status_reason: {current_run.get('status_reason') or 'none'}",
            "",
        ]
    )


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
        prog="python -m research.qre_trusted_loop_operational_controls",
        description="Build read-only trusted-loop operational controls.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_trusted_loop_operational_controls()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
