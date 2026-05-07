"""A9 — Release-gate status summary.

Read-only projection that consumes
``logs/development_release_gate/latest.json`` and emits a compact
operator-facing summary with closed-vocabulary buckets.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.development_release_gate`` (read-only API).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* Pure read on the artifact; never mutates ``latest.json``.

CLI::

    python -m reporting.development_release_gate_status
    python -m reporting.development_release_gate_status --indent 2
    python -m reporting.development_release_gate_status --no-write
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

from reporting import development_release_gate as drg

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A9"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_release_gate_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_release_gate_status/latest.json"
)


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
        "total": 0,
        "human_needed": 0,
        "protected_surface": 0,
        "by_verdict": {v: 0 for v in drg.VERDICTS},
        "by_verdict_reason": {r: 0 for r in drg.VERDICT_REASONS},
        "ready_for_merge": 0,
        "requiring_human_operator": 0,
    }


def collect_status(
    *,
    gate_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic status snapshot from the gate artifact."""
    gp = (
        gate_artifact_path
        if gate_artifact_path is not None
        else drg.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(gp)
    if payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "development_release_gate_status",
            "generated_at_utc": ts,
            "gate_artifact_path": str(gp),
            "gate_artifact_available": False,
            "gate_module_version": drg.MODULE_VERSION,
            "schema_pinned": {
                "verdicts": list(drg.VERDICTS),
                "verdict_reasons": list(drg.VERDICT_REASONS),
                "evidence_keys": list(drg.EVIDENCE_KEYS),
            },
            "counts": _empty_counts(),
            "validation_warnings": [],
            "note": "gate_artifact_absent",
        }

    src_counts = payload.get("counts") or {}
    if not isinstance(src_counts, dict):
        src_counts = {}
    by_verdict_src = (
        src_counts.get("by_verdict")
        if isinstance(src_counts.get("by_verdict"), dict)
        else {}
    )
    by_reason_src = (
        src_counts.get("by_verdict_reason")
        if isinstance(src_counts.get("by_verdict_reason"), dict)
        else {}
    )

    by_verdict = {v: int(by_verdict_src.get(v) or 0) for v in drg.VERDICTS}
    by_reason = {r: int(by_reason_src.get(r) or 0) for r in drg.VERDICT_REASONS}

    ready_for_merge = (
        by_verdict.get(drg.VERDICT_GO, 0)
        + by_verdict.get(drg.VERDICT_GO_WITH_FOLLOWUPS, 0)
    )
    requiring_human = by_verdict.get(drg.VERDICT_NO_GO_HUMAN_NEEDED, 0)

    counts = {
        "total": int(src_counts.get("total") or 0),
        "human_needed": int(src_counts.get("human_needed") or 0),
        "protected_surface": int(src_counts.get("protected_surface") or 0),
        "by_verdict": by_verdict,
        "by_verdict_reason": by_reason,
        "ready_for_merge": ready_for_merge,
        "requiring_human_operator": requiring_human,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_release_gate_status",
        "generated_at_utc": ts,
        "gate_artifact_path": str(gp),
        "gate_artifact_available": True,
        "gate_module_version": payload.get("module_version"),
        "gate_schema_version": payload.get("schema_version"),
        "gate_generated_at_utc": payload.get("generated_at_utc"),
        "gate_note": payload.get("note"),
        "evidence_input_present": bool(payload.get("evidence_input_present")),
        "queue_artifact_present": bool(payload.get("queue_artifact_present")),
        "schema_pinned": {
            "verdicts": list(drg.VERDICTS),
            "verdict_reasons": list(drg.VERDICT_REASONS),
            "evidence_keys": list(drg.EVIDENCE_KEYS),
        },
        "counts": counts,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "gate_artifact_present",
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_release_gate_status._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_release_gate_status.",
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
        prog="python -m reporting.development_release_gate_status",
        description=(
            "Read-only summary of logs/development_release_gate/"
            "latest.json. Decides nothing; mutates nothing."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_release_gate_status/latest.json "
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
