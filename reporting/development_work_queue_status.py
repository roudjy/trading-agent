"""A8 — Development Work Queue status summary.

Read-only projection that consumes
``logs/development_work_queue/latest.json`` and emits a compact
operator-facing status summary.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.development_work_queue``.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``.
* Pure read on the artifact; never mutates ``latest.json``.

CLI::

    python -m reporting.development_work_queue_status
    python -m reporting.development_work_queue_status --indent 2
    python -m reporting.development_work_queue_status --no-write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_work_queue as dwq

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A8"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_work_queue_status"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_work_queue_status/latest.json"


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


def collect_status(
    *,
    queue_artifact_path: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic status snapshot from the queue artifact.

    Args:
        queue_artifact_path: override the default
            ``logs/development_work_queue/latest.json`` source. Tests
            pass a synthetic fixture here.
    """
    qp = (
        queue_artifact_path
        if queue_artifact_path is not None
        else dwq.ARTIFACT_LATEST
    )
    payload = _read_json(qp)
    if payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "development_work_queue_status",
            "generated_at_utc": _utcnow(),
            "queue_artifact_path": str(qp),
            "queue_artifact_available": False,
            "queue_module_version": dwq.MODULE_VERSION,
            "schema_pinned": {
                "agent_roles": list(dwq.AGENT_ROLES),
                "statuses": list(dwq.STATUSES),
                "categories": list(dwq.CATEGORIES),
                "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
            },
            "counts": {
                "total": 0,
                "human_needed": 0,
                "blocked": 0,
                "protected_surface": 0,
                "ready_for_autonomous_action": 0,
                "requiring_human_operator": 0,
                "by_status": {s: 0 for s in dwq.STATUSES},
                "by_role": {r: 0 for r in dwq.AGENT_ROLES},
                "by_category": {c: 0 for c in dwq.CATEGORIES},
            },
            "validation_warnings": [],
            "note": "queue_artifact_absent",
        }

    counts = payload.get("counts") or {}
    if not isinstance(counts, dict):
        counts = {}

    by_status = counts.get("by_status") if isinstance(counts.get("by_status"), dict) else {}
    by_role = counts.get("by_role") if isinstance(counts.get("by_role"), dict) else {}
    by_category = (
        counts.get("by_category")
        if isinstance(counts.get("by_category"), dict)
        else {}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_work_queue_status",
        "generated_at_utc": _utcnow(),
        "queue_artifact_path": str(qp),
        "queue_artifact_available": True,
        "queue_module_version": payload.get("module_version"),
        "queue_schema_version": payload.get("schema_version"),
        "queue_generated_at_utc": payload.get("generated_at_utc"),
        "queue_note": payload.get("note"),
        "schema_pinned": {
            "agent_roles": list(dwq.AGENT_ROLES),
            "statuses": list(dwq.STATUSES),
            "categories": list(dwq.CATEGORIES),
            "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
        },
        "counts": {
            "total": int(counts.get("total") or 0),
            "human_needed": int(counts.get("human_needed") or 0),
            "blocked": int(counts.get("blocked") or 0),
            "protected_surface": int(counts.get("protected_surface") or 0),
            "ready_for_autonomous_action": int(
                counts.get("ready_for_autonomous_action") or 0
            ),
            "requiring_human_operator": int(
                counts.get("requiring_human_operator") or 0
            ),
            "by_status": {s: int(by_status.get(s) or 0) for s in dwq.STATUSES},
            "by_role": {r: int(by_role.get(r) or 0) for r in dwq.AGENT_ROLES},
            "by_category": {
                c: int(by_category.get(c) or 0) for c in dwq.CATEGORIES
            },
        },
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "queue_artifact_present",
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_work_queue_status._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_work_queue_status.",
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
        prog="python -m reporting.development_work_queue_status",
        description=(
            "Read-only summary of logs/development_work_queue/latest.json. "
            "Decides nothing; mutates nothing."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_work_queue_status/latest.json "
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
