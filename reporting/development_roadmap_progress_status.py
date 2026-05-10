"""A19 — Roadmap Progress Tracker status summary."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_roadmap_progress as drp
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A19"
REPORT_KIND: Final[str] = "development_roadmap_progress_status"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_roadmap_progress_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_roadmap_progress_status/latest.json"
)

_WRITE_PREFIX: Final[str] = "logs/development_roadmap_progress_status/"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _empty_counts() -> dict[str, Any]:
    return {
        "phase_count": 0,
        "by_phase_progress_state": {s: 0 for s in drp.PHASE_PROGRESS_STATES},
    }


def collect_status(
    *,
    progress_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    pp = (
        progress_artifact_path
        if progress_artifact_path is not None
        else drp.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(pp)
    if payload is None:
        snap = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": ts,
            "progress_artifact_path": str(pp),
            "progress_artifact_available": False,
            "progress_module_version": drp.MODULE_VERSION,
            "step5_enabled_substage": drp.STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": drp.step5_implementation_allowed,
            "schema_pinned": {
                "phase_progress_states": list(drp.PHASE_PROGRESS_STATES),
                "phase_row_keys": list(drp.PHASE_ROW_KEYS),
            },
            "counts": _empty_counts(),
            "validation_warnings": [],
            "note": "progress_artifact_absent",
        }
        assert_no_secrets(snap)
        return snap

    upstream_counts = payload.get("counts") or {}
    if not isinstance(upstream_counts, dict):
        upstream_counts = {}

    counts = _empty_counts()
    counts["phase_count"] = int(upstream_counts.get("phase_count") or 0)

    by_state = upstream_counts.get("by_phase_progress_state") or {}
    if isinstance(by_state, dict):
        for s in drp.PHASE_PROGRESS_STATES:
            counts["by_phase_progress_state"][s] = int(by_state.get(s) or 0)

    snap = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "progress_artifact_path": str(pp),
        "progress_artifact_available": True,
        "progress_module_version": payload.get("module_version"),
        "progress_schema_version": payload.get("schema_version"),
        "progress_generated_at_utc": payload.get("generated_at_utc"),
        "progress_note": payload.get("note"),
        "step5_enabled_substage": payload.get("step5_enabled_substage")
        or drp.STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": bool(
            payload.get("step5_implementation_allowed")
        ),
        "schema_pinned": {
            "phase_progress_states": list(drp.PHASE_PROGRESS_STATES),
            "phase_row_keys": list(drp.PHASE_ROW_KEYS),
        },
        "counts": counts,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "progress_artifact_present",
    }
    assert_no_secrets(snap)
    return snap


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_roadmap_progress_status._atomic_write_json refuses "
            f"non-status-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_roadmap_progress_status.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_roadmap_progress_status",
        description=(
            "Read-only summary of "
            "logs/development_roadmap_progress/latest.json. Decides "
            "nothing; mutates nothing."
        ),
    )
    p.add_argument(
        "--indent", type=int, default=2, help="JSON indent (0 for compact)."
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_roadmap_progress_status/latest.json "
            "(stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_status()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
