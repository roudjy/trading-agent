"""Read-only QRE controlled artifact regeneration backup plan."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_artifact_regeneration_backup_plan"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_artifact_regeneration_backup_plan"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_controlled_artifact_regeneration_backup_plan/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DEFAULT_BACKUP_ROOT_RELATIVE: Final[str] = "logs/qre_controlled_artifact_regeneration/backups"

DEFAULT_ARTIFACT_RELATIVE_PATHS: Final[tuple[str, ...]] = (
    "research/run_candidates_latest.v1.json",
    "research/screening_evidence_latest.v1.json",
    "research/research_latest.json",
    "research/run_filter_summary_latest.v1.json",
    "research/run_screening_candidates_latest.v1.json",
    "research/run_batches_latest.v1.json",
    "research/run_state.v1.json",
    "research/run_manifest_latest.v1.json",
    "logs/qre_market_observations/latest.json",
    "logs/qre_hypothesis_candidates/latest.json",
    "logs/qre_hypothesis_validation_plans/latest.json",
    "logs/qre_research_run_manifest/latest.json",
    "logs/qre_hypothesis_validation_results/latest.json",
    "logs/qre_evidence_quality_gate/latest.json",
    "logs/qre_validated_hypothesis_promotion_intent/latest.json",
)

BLOCKED_REFERENCE_PATHS: Final[tuple[str, ...]] = (
    "research/strategy_matrix.csv",
    "research/presets.py",
    "agent/backtesting/strategies.py",
    "registry.py",
    "logs/qre_shadow/latest.json",
    "logs/qre_paper/latest.json",
    "logs/qre_live/latest.json",
    "logs/qre_broker/latest.json",
    "logs/qre_risk/latest.json",
    "logs/qre_execution/latest.json",
)

PROTECTED_SEGMENTS: Final[frozenset[str]] = frozenset(
    {
        "presets",
        "strategy_matrix.csv",
        "strategies.py",
        "registry.py",
        "shadow",
        "paper",
        "live",
        "broker",
        "risk",
        "execution",
    }
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _modified_utc(path: Path) -> str | None:
    if not path.exists():
        return None
    return (
        _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _segments(relative_path: str) -> set[str]:
    path = Path(relative_path)
    return {part.lower() for part in path.parts}


def _classification(relative_path: str) -> str:
    parts = _segments(relative_path)
    if "research" in parts and Path(relative_path).name.endswith(".json"):
        return "allowed_mutable_research_artifact"
    if "logs" in parts and any(part.startswith("qre_") for part in parts):
        return "allowed_qre_reporting_artifact"
    if PROTECTED_SEGMENTS & parts:
        return "blocked_protected_runtime_or_authority_path"
    return "blocked_unknown_or_unapproved_path"


def _safe_to_backup(relative_path: str) -> bool:
    return _classification(relative_path).startswith("allowed_")


def _backup_target(relative_path: str, *, backup_root: Path) -> Path:
    return backup_root / relative_path.replace("/", "__")


def _restore_preview(relative_path: str, target: Path) -> str:
    return f"Copy-Item -LiteralPath '{_rel(target)}' -Destination '{relative_path}' -Force"


def _artifact_row(relative_path: str, *, backup_root: Path) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    target = _backup_target(relative_path, backup_root=backup_root)
    exists = path.exists() and path.is_file()
    safe = _safe_to_backup(relative_path)
    return {
        "artifact_path": relative_path,
        "artifact_exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "fingerprint_sha256": _sha256(path),
        "modified_utc": _modified_utc(path),
        "backup_target_path": _rel(target),
        "restore_command_preview": _restore_preview(relative_path, target),
        "protected_path_classification": _classification(relative_path),
        "safe_to_backup": safe,
    }


def _blocked_row(relative_path: str) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    exists = path.exists() and path.is_file()
    return {
        "artifact_path": relative_path,
        "artifact_exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "fingerprint_sha256": _sha256(path),
        "modified_utc": _modified_utc(path),
        "protected_path_classification": _classification(relative_path),
        "safe_to_backup": False,
    }


def _final_recommendation(rows: list[dict[str, Any]], blocked: list[dict[str, Any]]) -> str:
    unsafe = [row for row in rows if row["artifact_exists"] and not row["safe_to_backup"]]
    blocked_existing = [row for row in blocked if row["artifact_exists"]]
    if unsafe or blocked_existing:
        return "backup_plan_ready_with_protected_paths_blocked"
    if any(row["artifact_exists"] for row in rows):
        return "backup_plan_ready_for_controlled_regeneration"
    return "backup_plan_has_no_existing_artifacts_to_copy"


def collect_snapshot(
    *,
    artifact_relative_paths: tuple[str, ...] | None = None,
    backup_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    root = backup_root or (REPO_ROOT / DEFAULT_BACKUP_ROOT_RELATIVE / "<timestamp>")
    paths = artifact_relative_paths or DEFAULT_ARTIFACT_RELATIVE_PATHS
    artifacts = [_artifact_row(_bounded_str(path), backup_root=root) for path in paths]
    blocked_paths = [_blocked_row(path) for path in BLOCKED_REFERENCE_PATHS]
    warnings = [
        f"missing_artifact:{row['artifact_path']}"
        for row in artifacts
        if row["artifact_exists"] is False
    ]
    warnings.extend(
        f"blocked_existing_path:{row['artifact_path']}"
        for row in blocked_paths
        if row["artifact_exists"] is True
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "safe_to_execute": False,
        "read_only": True,
        "artifacts_to_backup": artifacts,
        "blocked_paths": blocked_paths,
        "validation_warnings": warnings,
        "final_recommendation": _final_recommendation(artifacts, blocked_paths),
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
        raise ValueError(f"refusing write outside QRE backup plan dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_artifact_regeneration_backup_plan.",
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
        prog="reporting.qre_controlled_artifact_regeneration_backup_plan",
        description="Create a read-only backup plan for controlled QRE artifact regeneration.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "BLOCKED_REFERENCE_PATHS",
    "DEFAULT_ARTIFACT_RELATIVE_PATHS",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
