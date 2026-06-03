"""Non-executing QRE validation request dry-run runner."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_validation_request_dry_run"
INPUT_REPORT_KIND: Final[str] = "qre_executable_validation_request"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_executable_validation_request/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_validation_request_dry_run"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_validation_request_dry_run/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DRY_RUN_READY: Final[str] = "dry_run_ready"
DRY_RUN_BLOCKED_REQUEST_NOT_READY: Final[str] = "dry_run_blocked_request_not_ready"
DRY_RUN_BLOCKED_MISSING_OPERATOR_APPROVAL: Final[str] = "dry_run_blocked_missing_operator_approval"
DRY_RUN_BLOCKED_MISSING_COMMAND_PREVIEW: Final[str] = "dry_run_blocked_missing_command_preview"
DRY_RUN_MALFORMED: Final[str] = "dry_run_malformed"

DRY_RUN_STATUSES: Final[tuple[str, ...]] = (
    DRY_RUN_READY,
    DRY_RUN_BLOCKED_REQUEST_NOT_READY,
    DRY_RUN_BLOCKED_MISSING_OPERATOR_APPROVAL,
    DRY_RUN_BLOCKED_MISSING_COMMAND_PREVIEW,
    DRY_RUN_MALFORMED,
)

REQUEST_READY: Final[str] = "request_ready_for_operator_review"
NOTE_INPUT_ABSENT: Final[str] = "executable_validation_request_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "executable_validation_request_artifact_unparseable"

FUTURE_OUTPUTS: Final[tuple[str, ...]] = (
    "research/run_candidates_latest.v1.json",
    "research/screening_evidence_latest.v1.json",
    "research/history/<run_id>/...",
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> tuple[bool, dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return (False, None)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (True, None)
    return (True, parsed if isinstance(parsed, dict) else None)


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _base_row(request: dict[str, Any]) -> dict[str, Any]:
    row = {
        "request_id": _bounded_str(request.get("request_id"), max_len=160),
        "qre_hypothesis_id": _bounded_str(request.get("qre_hypothesis_id"), max_len=160),
        "executable_hypothesis_id": _bounded_str(
            request.get("executable_hypothesis_id"),
            max_len=160,
        ),
        "preset_name": _bounded_str(request.get("preset_name"), max_len=160),
        "strategy_template_id": _bounded_str(request.get("strategy_template_id"), max_len=160),
        "asset": _bounded_str(request.get("asset"), max_len=80),
        "symbol": _bounded_str(request.get("symbol"), max_len=80),
        "timeframe": _bounded_str(request.get("timeframe"), max_len=40),
        "interval": _bounded_str(request.get("interval"), max_len=40),
    }
    return {key: value for key, value in row.items() if value}


def _build_dry_run_row(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        return {
            "dry_run_status": DRY_RUN_MALFORMED,
            "would_run_command_preview": None,
            "would_write_artifacts": list(FUTURE_OUTPUTS),
            "backup_required": True,
            "safe_to_execute": False,
            "executed": False,
        }

    row = _base_row(request)
    command_preview = _bounded_str(request.get("allowed_command_preview"), max_len=600)
    if request.get("request_status") != REQUEST_READY:
        status = DRY_RUN_BLOCKED_REQUEST_NOT_READY
    elif (
        request.get("requires_operator_approval") is True
        and request.get("operator_approved") is not True
    ):
        status = DRY_RUN_BLOCKED_MISSING_OPERATOR_APPROVAL
    elif not command_preview:
        status = DRY_RUN_BLOCKED_MISSING_COMMAND_PREVIEW
    else:
        status = DRY_RUN_READY

    row.update(
        {
            "dry_run_status": status,
            "would_run_command_preview": command_preview if command_preview else None,
            "would_write_artifacts": list(FUTURE_OUTPUTS),
            "backup_required": True,
            "safe_to_execute": False,
            "executed": False,
        }
    )
    return row


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(row.get("dry_run_status") for row in rows)
    return {
        "total": len(rows),
        "ready": counter.get(DRY_RUN_READY, 0),
        "blocked": len(rows) - counter.get(DRY_RUN_READY, 0),
        "by_dry_run_status": {status: counter.get(status, 0) for status in DRY_RUN_STATUSES},
    }


def _final_recommendation(rows: list[dict[str, Any]]) -> str:
    if any(row.get("dry_run_status") == DRY_RUN_READY for row in rows):
        return "validation_request_dry_run_ready_for_operator_review"
    if rows:
        return "validation_request_dry_run_blocked_before_execution"
    return "no_validation_request_dry_run_rows_available"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    dry_run_results: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "safe_to_execute": False,
        "read_only": True,
        "launches_subprocess": False,
        "executed_anything": False,
        "final_recommendation": _final_recommendation(dry_run_results),
        "counts": _counts(dry_run_results),
        "dry_run_results": dry_run_results,
        "validation_warnings": validation_warnings,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_research_artifacts": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "eligible_for_direct_execution": False,
    }


def collect_snapshot(
    *,
    input_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    available, payload = _read_json(source)
    if payload is None:
        warning = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            dry_run_results=[],
            validation_warnings=[warning],
        )

    raw_requests = payload.get("validation_requests")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(raw_requests, list):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            dry_run_results=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    dry_run_results = [_build_dry_run_row(row) for row in raw_requests]
    dry_run_results.sort(key=lambda row: row.get("request_id", ""))
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        dry_run_results=dry_run_results,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE validation request dry-run dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_validation_request_dry_run.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_validation_request_dry_run_runner",
        description="Build a non-executing dry-run plan for QRE validation requests.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        input_artifact_path=args.source,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "DRY_RUN_BLOCKED_MISSING_COMMAND_PREVIEW",
    "DRY_RUN_BLOCKED_MISSING_OPERATOR_APPROVAL",
    "DRY_RUN_BLOCKED_REQUEST_NOT_READY",
    "DRY_RUN_MALFORMED",
    "DRY_RUN_READY",
    "DRY_RUN_STATUSES",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
