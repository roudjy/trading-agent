from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_trusted_loop_operational_controls as operational_controls


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_state_sequential_retrieval"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_state_sequential_retrieval")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_research_state_sequential_retrieval/"

RUN_MANIFEST_PATH: Final[Path] = Path("research/run_manifest_latest.v1.json")
RUN_STATE_PATH: Final[Path] = Path("research/run_state.v1.json")
RUN_PROGRESS_PATH: Final[Path] = Path("research/run_progress_latest.v1.json")
RUN_BATCHES_PATH: Final[Path] = Path("research/run_batches_latest.v1.json")
RESEARCH_STATE_PATH: Final[Path] = Path("research/research_state_latest.v1.json")
HISTORY_ROOT: Final[Path] = Path("research/history")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    return value is True


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


def _path_inputs(repo_root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for key, path in {
        "run_manifest": RUN_MANIFEST_PATH,
        "run_state": RUN_STATE_PATH,
        "run_progress": RUN_PROGRESS_PATH,
        "run_batches": RUN_BATCHES_PATH,
        "research_state": RESEARCH_STATE_PATH,
        "history_root": HISTORY_ROOT,
    }.items():
        absolute = repo_root / path
        rows[key] = {
            "path": path.as_posix(),
            "exists": absolute.exists(),
            "is_file": absolute.is_file(),
            "is_dir": absolute.is_dir(),
        }
    return rows


def _current_batch_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    batches = payload.get("batches") if isinstance(payload, Mapping) else None
    if not isinstance(batches, list):
        return {
            "batch_count": 0,
            "status_counts": {},
            "attempt_reason_counts": {},
        }
    status_counts = Counter()
    attempt_reason_counts = Counter()
    for row in batches:
        if not isinstance(row, Mapping):
            continue
        status_counts[_text(row.get("status")) or "unknown"] += 1
        attempt_reason = _text(row.get("last_attempt_reason"))
        if attempt_reason:
            attempt_reason_counts[attempt_reason] += 1
    return {
        "batch_count": sum(status_counts.values()),
        "status_counts": dict(sorted(status_counts.items())),
        "attempt_reason_counts": dict(sorted(attempt_reason_counts.items())),
    }


def _history_sequence_rows(repo_root: Path) -> list[dict[str, Any]]:
    base = repo_root / HISTORY_ROOT
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in base.iterdir() if path.is_dir()), key=lambda item: item.name):
        manifest = _read_json(run_dir / "run_manifest.v1.json")
        state = _read_json(run_dir / "run_state.v1.json")
        progress = _read_json(run_dir / "run_progress.v1.json")
        resume_sidecar_count = len(list(run_dir.glob("batches/*/candidate_resume/*.v1.json")))
        continuation = (
            dict((manifest or {}).get("continuation_summary") or {})
            if isinstance((manifest or {}).get("continuation_summary"), Mapping)
            else {}
        )
        rows.append(
            {
                "source": "history",
                "run_id": _text((manifest or {}).get("run_id")) or _text((state or {}).get("run_id")) or run_dir.name,
                "status": _text((state or {}).get("status")) or _text((manifest or {}).get("status")) or "unknown",
                "lifecycle_mode": _text((manifest or {}).get("lifecycle_mode")) or "unknown",
                "resumed_from_run_id": _text((manifest or {}).get("resumed_from_run_id")) or None,
                "retry_failed_batches": _bool((manifest or {}).get("retry_failed_batches")),
                "config_hash": _text((manifest or {}).get("config_hash")) or None,
                "git_revision": _text((manifest or {}).get("git_revision")) or None,
                "progress_completed": int((progress or {}).get("completed_items") or 0),
                "progress_total": int((progress or {}).get("total_items") or 0),
                "failed_items": int((progress or {}).get("failed_items") or 0),
                "resume_sidecar_count": resume_sidecar_count,
                "continuation_summary": continuation,
                "history_path": _rel(run_dir, root=repo_root),
            }
        )
    return rows


def _current_sequence_row(
    *,
    manifest: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    progress: Mapping[str, Any] | None,
    research_state: Mapping[str, Any] | None,
    current_batches: Mapping[str, Any] | None,
    operational_summary: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not manifest and not state and not progress and not research_state and not current_batches:
        return None
    continuation = (
        dict((manifest or {}).get("continuation_summary") or {})
        if isinstance((manifest or {}).get("continuation_summary"), Mapping)
        else {}
    )
    batch_summary = _current_batch_summary(current_batches)
    return {
        "source": "current_latest",
        "run_id": _text((manifest or {}).get("run_id")) or _text((state or {}).get("run_id")) or _text((progress or {}).get("run_id")) or None,
        "status": _text((operational_summary or {}).get("status")) or _text((state or {}).get("status")) or _text((manifest or {}).get("status")) or "unknown",
        "lifecycle_mode": _text((manifest or {}).get("lifecycle_mode")) or "unknown",
        "resumed_from_run_id": _text((manifest or {}).get("resumed_from_run_id")) or None,
        "retry_failed_batches": _bool((manifest or {}).get("retry_failed_batches")),
        "config_hash": _text((manifest or {}).get("config_hash")) or None,
        "git_revision": _text((manifest or {}).get("git_revision")) or None,
        "progress_completed": int((progress or {}).get("completed_items") or 0),
        "progress_total": int((progress or {}).get("total_items") or 0),
        "failed_items": int((progress or {}).get("failed_items") or 0),
        "continuation_summary": continuation,
        "batch_count": int(batch_summary.get("batch_count") or 0),
        "batch_status_counts": dict(batch_summary.get("status_counts") or {}),
        "batch_attempt_reason_counts": dict(batch_summary.get("attempt_reason_counts") or {}),
        "hypothesis_state": _text((research_state or {}).get("hypothesis_state")) or None,
        "policy_state": _text((research_state or {}).get("policy_state")) or None,
        "synthesis_gate": _text((research_state or {}).get("synthesis_gate")) or None,
        "next_best_test": _text((research_state or {}).get("next_best_test")) or None,
        "trusted_loop_exact_next_safe_action": _text((operational_summary or {}).get("exact_next_safe_action")) or None,
    }


def _sequence_rows(
    *,
    current_row: Mapping[str, Any] | None,
    history_rows: Sequence[Mapping[str, Any]],
    max_rows: int,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in history_rows]
    if current_row:
        rows.append(dict(current_row))
    rows.sort(
        key=lambda row: (
            _text(row.get("run_id")),
            1 if _text(row.get("source")) == "current_latest" else 0,
        )
    )
    if max_rows > 0:
        rows = rows[-max_rows:]
    start_index = max(0, len(rows) - max_rows) if max_rows > 0 else 0
    for offset, row in enumerate(rows, start=1):
        row["sequence_index"] = start_index + offset
    return rows


def _recovery_context(
    *,
    manifest: Mapping[str, Any] | None,
    current_row: Mapping[str, Any] | None,
    operational_report: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = manifest or {}
    operational_report = operational_report or {}
    resumability = (
        operational_report.get("resumability")
        if isinstance(operational_report.get("resumability"), Mapping)
        else {}
    )
    replayability = (
        operational_report.get("replayability")
        if isinstance(operational_report.get("replayability"), Mapping)
        else {}
    )
    current_row = current_row or {}
    recovery_policy = (
        dict(manifest.get("recovery_policy") or {})
        if isinstance(manifest.get("recovery_policy"), Mapping)
        else {}
    )
    return {
        "lifecycle_mode": _text(manifest.get("lifecycle_mode")) or _text(current_row.get("lifecycle_mode")) or "unknown",
        "resumed_from_run_id": _text(manifest.get("resumed_from_run_id")) or None,
        "retry_failed_batches": _bool(manifest.get("retry_failed_batches")),
        "continuation_summary": dict(current_row.get("continuation_summary") or {}),
        "recovery_policy": recovery_policy,
        "resumable": _bool(resumability.get("resumable")),
        "resume_sidecar_count": int(resumability.get("resume_sidecar_count") or 0),
        "duplicate_run_suppressed": _bool(replayability.get("duplicate_run_suppressed")),
        "same_input_history_count": int(replayability.get("same_input_history_count") or 0),
        "replay_manifest_ready": _bool(replayability.get("replay_manifest_ready")),
    }


def _blockers(
    *,
    path_inputs: Mapping[str, Mapping[str, Any]],
    history_rows: Sequence[Mapping[str, Any]],
    current_row: Mapping[str, Any] | None,
    operational_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact_key in ("run_manifest", "run_state", "run_progress", "research_state"):
        row = path_inputs.get(artifact_key) if isinstance(path_inputs.get(artifact_key), Mapping) else {}
        if not row.get("exists"):
            rows.append(
                {
                    "blocker_code": f"missing_{artifact_key}",
                    "severity": "high",
                    "reason": f"{artifact_key} is required for deterministic current-state retrieval.",
                    "evidence_ref": str(row.get("path") or ""),
                }
            )
    if not history_rows:
        rows.append(
            {
                "blocker_code": "missing_history_sequence",
                "severity": "medium",
                "reason": "No history checkpoints are visible, so ordered multi-run retrieval is incomplete.",
                "evidence_ref": HISTORY_ROOT.as_posix(),
            }
        )
    operational_summary = (
        operational_report.get("summary")
        if isinstance(operational_report.get("summary"), Mapping)
        else {}
    )
    reconciliation = (
        operational_report.get("state_reconciliation")
        if isinstance(operational_report.get("state_reconciliation"), Mapping)
        else {}
    )
    if _text((operational_summary or {}).get("artifact_freshness_status")) == "stale_or_missing":
        rows.append(
            {
                "blocker_code": "stale_or_missing_current_run_artifacts",
                "severity": "medium",
                "reason": "Current trusted-loop artifacts are stale or missing relative to run history.",
                "evidence_ref": "logs/qre_trusted_loop_operational_controls/latest.json",
            }
        )
    for mismatch in reconciliation.get("mismatches") or []:
        mismatch_text = _text(mismatch)
        if not mismatch_text:
            continue
        rows.append(
            {
                "blocker_code": f"state_reconciliation_{mismatch_text}",
                "severity": "medium",
                "reason": f"Trusted-loop state reconciliation reported {mismatch_text}.",
                "evidence_ref": "logs/qre_trusted_loop_operational_controls/latest.json",
            }
        )
    if current_row is None:
        rows.append(
            {
                "blocker_code": "missing_current_sequence_row",
                "severity": "high",
                "reason": "No current run artifacts were available to materialize the latest sequence row.",
                "evidence_ref": "research/run_manifest_latest.v1.json",
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = _digest(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_research_state_sequential_retrieval(
    *,
    repo_root: Path = Path("."),
    max_rows: int = 8,
) -> dict[str, Any]:
    path_inputs = _path_inputs(repo_root)
    manifest = _read_json(repo_root / RUN_MANIFEST_PATH)
    state = _read_json(repo_root / RUN_STATE_PATH)
    progress = _read_json(repo_root / RUN_PROGRESS_PATH)
    current_batches = _read_json(repo_root / RUN_BATCHES_PATH)
    research_state = _read_json(repo_root / RESEARCH_STATE_PATH)
    operational_report = operational_controls.build_trusted_loop_operational_controls(
        repo_root=repo_root
    )
    operational_summary = (
        operational_report.get("summary")
        if isinstance(operational_report.get("summary"), Mapping)
        else {}
    )
    history_rows = _history_sequence_rows(repo_root)
    current_row = _current_sequence_row(
        manifest=manifest,
        state=state,
        progress=progress,
        research_state=research_state,
        current_batches=current_batches,
        operational_summary=operational_summary,
    )
    sequence_rows = _sequence_rows(current_row=current_row, history_rows=history_rows, max_rows=max_rows)
    blockers = _blockers(
        path_inputs=path_inputs,
        history_rows=history_rows,
        current_row=current_row,
        operational_report=operational_report,
    )
    recovery_context = _recovery_context(
        manifest=manifest,
        current_row=current_row,
        operational_report=operational_report,
    )
    exact_next_action = (
        "restore_current_run_artifacts"
        if current_row is None
        else _text(operational_summary.get("exact_next_safe_action"))
        or _text((research_state or {}).get("next_best_test"))
        or ("restore_current_run_artifacts" if blockers else "preserve_research_state_sequence_visibility")
    )
    ready = current_row is not None and bool(sequence_rows)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "research_state_sequential_retrieval_ready": ready,
            "current_run_id": _text((current_row or {}).get("run_id")) or None,
            "current_status": _text((current_row or {}).get("status")) or "missing",
            "history_run_count": len(history_rows),
            "visible_sequence_row_count": len(sequence_rows),
            "blocked_count": len(blockers),
            "resumable": bool(recovery_context.get("resumable")),
            "duplicate_run_suppressed": bool(recovery_context.get("duplicate_run_suppressed")),
            "same_input_history_count": int(recovery_context.get("same_input_history_count") or 0),
            "replay_manifest_ready": bool(recovery_context.get("replay_manifest_ready")),
            "current_hypothesis_state": _text((current_row or {}).get("hypothesis_state")) or None,
            "current_policy_state": _text((current_row or {}).get("policy_state")) or None,
            "current_next_best_test": _text((current_row or {}).get("next_best_test")) or None,
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Research-state sequential retrieval reconstructs ordered run history, current fail-closed "
                "research state, and recovery/replay context from existing local artifacts only."
            ),
        },
        "path_inputs": path_inputs,
        "sequence_rows": sequence_rows,
        "recovery_context": recovery_context,
        "blockers": blockers,
        "state_reconciliation": dict(operational_report.get("state_reconciliation") or {}),
        "current_run": dict(operational_report.get("current_run") or {}),
        "replayability": dict(operational_report.get("replayability") or {}),
        "resumability": dict(operational_report.get("resumability") or {}),
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_resume_runtime_directly": False,
            "can_replay_runtime_directly": False,
            "can_mutate_run_state": False,
            "can_activate_shadow": False,
            "can_promote_candidate": False,
        },
        "supporting_reports": {
            "trusted_loop_operational_controls": "logs/qre_trusted_loop_operational_controls/latest.json",
            "research_state": RESEARCH_STATE_PATH.as_posix(),
            "run_manifest": RUN_MANIFEST_PATH.as_posix(),
            "run_state": RUN_STATE_PATH.as_posix(),
            "run_progress": RUN_PROGRESS_PATH.as_posix(),
            "run_batches": RUN_BATCHES_PATH.as_posix(),
            "history_root": HISTORY_ROOT.as_posix(),
        },
        "safety_invariants": {
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_current_run_state": False,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "summary": report["summary"],
            "sequence_rows": report["sequence_rows"],
            "recovery_context": report["recovery_context"],
            "blockers": report["blockers"],
            "state_reconciliation": report["state_reconciliation"],
            "current_run": report["current_run"],
            "replayability": report["replayability"],
            "resumability": report["resumability"],
            "authority_boundary": report["authority_boundary"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    lines = [
        "# QRE Research State Sequential Retrieval",
        "",
        f"- research_state_sequential_retrieval_ready: {summary.get('research_state_sequential_retrieval_ready', False)}",
        f"- current_run_id: {summary.get('current_run_id') or 'none'}",
        f"- current_status: {summary.get('current_status') or 'missing'}",
        f"- history_run_count: {summary.get('history_run_count', 0)}",
        f"- visible_sequence_row_count: {summary.get('visible_sequence_row_count', 0)}",
        f"- blocked_count: {summary.get('blocked_count', 0)}",
        f"- resumable: {summary.get('resumable', False)}",
        f"- replay_manifest_ready: {summary.get('replay_manifest_ready', False)}",
        f"- current_next_best_test: {summary.get('current_next_best_test') or 'none'}",
        f"- exact_next_action: {summary.get('exact_next_action') or ''}",
        "",
        "## Blockers",
    ]
    if blockers:
        for row in blockers:
            if not isinstance(row, Mapping):
                continue
            lines.append(f"- {row.get('blocker_code')}: {row.get('reason')}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path("."), max_rows: int = 8) -> dict[str, str]:
    operational_payload = operational_controls.build_trusted_loop_operational_controls(repo_root=repo_root)
    operational_controls.write_outputs(operational_payload, repo_root=repo_root)
    refreshed = build_research_state_sequential_retrieval(repo_root=repo_root, max_rows=max_rows)
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_research_state_sequential_retrieval",
        description="Build a deterministic read-only QRE research-state sequential retrieval report.",
    )
    parser.add_argument("--write", action="store_true", help="Write allowlisted report outputs.")
    parser.add_argument("--max-rows", type=int, default=8, help="Maximum visible sequence rows to emit.")
    args = parser.parse_args()

    report = build_research_state_sequential_retrieval(max_rows=args.max_rows)
    if args.write:
        report["_artifact_paths"] = write_outputs(report, max_rows=args.max_rows)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
