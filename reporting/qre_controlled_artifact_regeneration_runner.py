"""Controlled QRE artifact regeneration runner with backup support."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from reporting import (
    qre_closed_loop_materialization_runner,
    qre_executable_hypothesis_identity_bridge_diagnostics,
    qre_executable_validation_request,
    qre_market_observation_hypothesis_readiness,
    qre_validation_request_dry_run_runner,
)
from reporting import qre_controlled_artifact_regeneration_backup_plan as backup_plan

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_artifact_regeneration"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_artifact_regeneration"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_controlled_artifact_regeneration/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH
BACKUP_ROOT: Final[Path] = ARTIFACT_DIR / "backups"

MODE_DRY_RUN: Final[str] = "dry_run"
MODE_WRITE_REPORTING_ONLY: Final[str] = "write_reporting_only"
MODE_ALLOW_RESEARCH_REGENERATION: Final[str] = "allow_research_regeneration"
MODE_RESTORE_FROM_BACKUP: Final[str] = "restore_from_backup"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_dir(generated_at_utc: str) -> str:
    return generated_at_utc.replace(":", "").replace("-", "").replace("+0000", "Z").replace("Z", "")


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


def _counts(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    counts = payload.get("counts")
    return counts if isinstance(counts, dict) else {}


def _route_snapshot(*, generated_at_utc: str) -> dict[str, Any]:
    readiness = qre_market_observation_hypothesis_readiness.collect_snapshot(
        generated_at_utc=generated_at_utc
    )
    requests = qre_executable_validation_request.collect_snapshot(generated_at_utc=generated_at_utc)
    dry_run = qre_validation_request_dry_run_runner.collect_snapshot(
        generated_at_utc=generated_at_utc
    )
    bridge = qre_executable_hypothesis_identity_bridge_diagnostics.collect_snapshot(
        generated_at_utc=generated_at_utc,
    )
    return {
        "hypothesis_readiness": {
            "final_recommendation": readiness.get("final_recommendation"),
            "counts": _counts(readiness),
            "by_readiness_class": readiness.get("by_readiness_class", {}),
        },
        "executable_validation_request": {
            "final_recommendation": requests.get("final_recommendation"),
            "counts": _counts(requests),
        },
        "validation_request_dry_run": {
            "final_recommendation": dry_run.get("final_recommendation"),
            "counts": _counts(dry_run),
            "executed_anything": dry_run.get("executed_anything") is True,
        },
        "identity_bridge": {
            "final_recommendation": bridge.get("final_recommendation"),
            "regeneration_linkage_expected": (
                bridge.get("bridge", {}).get("regeneration_linkage_expected") is True
                if isinstance(bridge.get("bridge"), dict)
                else False
            ),
        },
    }


def _approved_backup_rows(plan_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan_snapshot.get("artifacts_to_backup")
    if not isinstance(rows, list):
        return []
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("safe_to_backup") is True
        and row.get("artifact_exists") is True
    ]


def _copy_backups(plan_snapshot: dict[str, Any], *, backup_dir: Path) -> list[dict[str, Any]]:
    backup_dir_resolved = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for row in _approved_backup_rows(plan_snapshot):
        relative = str(row.get("artifact_path") or "")
        source = (REPO_ROOT / relative).resolve()
        target = (backup_dir / relative.replace("/", "__")).resolve()
        if not target.is_relative_to(backup_dir_resolved):
            raise ValueError(f"refusing backup target outside backup dir: {target}")
        shutil.copy2(source, target)
        copied.append(
            {
                "artifact_path": relative,
                "backup_path": _rel(target),
                "restore_command": f"Copy-Item -LiteralPath '{_rel(target)}' -Destination '{relative}' -Force",
            }
        )
    return copied


def _restore_instructions_from_backup(backup_dir: Path) -> list[str]:
    if not backup_dir.exists() or not backup_dir.is_dir():
        return [f"backup_dir_missing:{backup_dir.as_posix()}"]
    commands: list[str] = []
    for item in sorted(backup_dir.glob("*")):
        if not item.is_file():
            continue
        relative = item.name.replace("__", "/")
        commands.append(f"Copy-Item -LiteralPath '{_rel(item)}' -Destination '{relative}' -Force")
    return commands


def _write_reporting_materialization(generated_at_utc: str) -> dict[str, Any]:
    snapshot = qre_closed_loop_materialization_runner.collect_snapshot(
        no_write=False,
        generated_at_utc=generated_at_utc,
    )
    out = qre_closed_loop_materialization_runner.write_outputs(snapshot)
    return {
        "executed": True,
        "artifact_path": _rel(out),
        "final_recommendation": snapshot.get("final_recommendation"),
        "counts": _counts(snapshot),
    }


def _final_recommendation(
    *,
    mode: str,
    route_after: dict[str, Any],
    executed_reporting_materialization: bool,
) -> str:
    request_counts = route_after.get("executable_validation_request", {}).get("counts", {})
    dry_counts = route_after.get("validation_request_dry_run", {}).get("counts", {})
    ready_requests = request_counts.get("ready", 0) if isinstance(request_counts, dict) else 0
    dry_ready = dry_counts.get("ready", 0) if isinstance(dry_counts, dict) else 0
    if mode == MODE_ALLOW_RESEARCH_REGENERATION:
        return "controlled_regeneration_requires_operator_manual_command"
    if ready_requests and dry_ready:
        return "qre_route_ready_for_operator_review_after_reporting_materialization"
    if executed_reporting_materialization:
        return "reporting_materialized_but_qre_route_still_blocked"
    return "dry_run_only_controlled_regeneration_not_executed"


def collect_snapshot(
    *,
    dry_run: bool = True,
    write_reporting_only: bool = False,
    allow_research_regeneration: bool = False,
    restore_from_backup: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    mode = MODE_DRY_RUN
    if restore_from_backup is not None:
        mode = MODE_RESTORE_FROM_BACKUP
    elif allow_research_regeneration:
        mode = MODE_ALLOW_RESEARCH_REGENERATION
    elif write_reporting_only:
        mode = MODE_WRITE_REPORTING_ONLY
    elif dry_run:
        mode = MODE_DRY_RUN

    backup_dir = BACKUP_ROOT / _timestamp_dir(generated)
    plan_snapshot = backup_plan.collect_snapshot(
        backup_root=backup_dir,
        generated_at_utc=generated,
    )
    route_before = _route_snapshot(generated_at_utc=generated)
    backups_created: list[dict[str, Any]] = []
    executed_reporting_materialization: dict[str, Any] = {"executed": False}
    research_regeneration = {
        "executed": False,
        "reason": "research_regeneration_not_requested",
    }
    restore_instructions = [
        str(row.get("restore_command_preview") or "")
        for row in plan_snapshot.get("artifacts_to_backup", [])
        if isinstance(row, dict) and row.get("artifact_exists") is True
    ]

    if mode in {MODE_WRITE_REPORTING_ONLY, MODE_ALLOW_RESEARCH_REGENERATION}:
        backups_created = _copy_backups(plan_snapshot, backup_dir=backup_dir)
        restore_instructions = [row["restore_command"] for row in backups_created]

    if mode == MODE_WRITE_REPORTING_ONLY:
        executed_reporting_materialization = _write_reporting_materialization(generated)
    elif mode == MODE_ALLOW_RESEARCH_REGENERATION:
        research_regeneration = {
            "executed": False,
            "reason": "no_narrow_safe_research_regeneration_api_identified",
            "blocked_recommendation": "controlled_regeneration_requires_operator_manual_command",
        }
    elif mode == MODE_RESTORE_FROM_BACKUP and restore_from_backup is not None:
        restore_instructions = _restore_instructions_from_backup(restore_from_backup)

    route_after = _route_snapshot(generated_at_utc=generated)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "safe_to_execute": False,
        "mode": mode,
        "backups_created": backups_created,
        "backup_dir": _rel(backup_dir) if backups_created else None,
        "backup_plan": plan_snapshot,
        "executed_research_regeneration": research_regeneration["executed"],
        "research_regeneration": research_regeneration,
        "executed_reporting_materialization": executed_reporting_materialization["executed"],
        "reporting_materialization": executed_reporting_materialization,
        "route_before": route_before,
        "route_after": route_after,
        "final_recommendation": _final_recommendation(
            mode=mode,
            route_after=route_after,
            executed_reporting_materialization=executed_reporting_materialization["executed"],
        ),
        "restore_instructions": restore_instructions,
        "validation_warnings": plan_snapshot.get("validation_warnings", []),
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "launches_subprocess": False,
        "eligible_for_direct_execution": False,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE controlled regeneration dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_artifact_regeneration.",
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


def write_outputs(snapshot: dict[str, Any], *, output_path: Path | None = None) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_controlled_artifact_regeneration_runner",
        description="Run controlled QRE artifact regeneration in dry-run or explicit write modes.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-reporting-only", action="store_true")
    parser.add_argument("--allow-research-regeneration", action="store_true")
    parser.add_argument("--restore-from-backup", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        dry_run=args.dry_run or not (args.write_reporting_only or args.allow_research_regeneration),
        write_reporting_only=args.write_reporting_only,
        allow_research_regeneration=args.allow_research_regeneration,
        restore_from_backup=args.restore_from_backup,
        generated_at_utc=args.frozen_utc,
    )
    write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "BACKUP_ROOT",
    "MODE_ALLOW_RESEARCH_REGENERATION",
    "MODE_DRY_RUN",
    "MODE_RESTORE_FROM_BACKUP",
    "MODE_WRITE_REPORTING_ONLY",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
