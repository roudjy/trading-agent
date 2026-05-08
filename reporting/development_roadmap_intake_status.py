"""Step 5.0.1 — Roadmap Intake Bridge status summary.

Read-only projection that consumes
``logs/development_roadmap_intake/latest.json`` and emits a compact
operator-facing status summary, counting candidates by ``source_kind``,
``candidate_kind``, ``intake_status``, and
``execution_authority_decision``.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.development_roadmap_intake``.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* Pure read on the upstream artifact; never mutates ``latest.json``.
* Atomic write only under ``logs/development_roadmap_intake_status/``.

CLI::

    python -m reporting.development_roadmap_intake_status
    python -m reporting.development_roadmap_intake_status --indent 2
    python -m reporting.development_roadmap_intake_status --no-write
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

from reporting import development_roadmap_intake as dri
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A14.5_0_1"
REPORT_KIND: Final[str] = "development_roadmap_intake_status"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_roadmap_intake_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_roadmap_intake_status/latest.json"
)

_WRITE_PREFIX: Final[str] = "logs/development_roadmap_intake_status/"


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


def _schema_pinned() -> dict[str, Any]:
    return {
        "source_kinds": list(dri.SOURCE_KINDS),
        "candidate_kinds": list(dri.CANDIDATE_KINDS),
        "intake_statuses": list(dri.INTAKE_STATUSES),
        "promotion_targets": list(dri.PROMOTION_TARGETS),
        "agent_roles": list(dwq.AGENT_ROLES),
        "risk_levels": list(ea.RISK_CLASSES),
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "human_needed": 0,
        "eligible": 0,
        "blocked": 0,
        "by_source_kind": {k: 0 for k in dri.SOURCE_KINDS},
        "by_candidate_kind": {k: 0 for k in dri.CANDIDATE_KINDS},
        "by_intake_status": {s: 0 for s in dri.INTAKE_STATUSES},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }


def collect_status(
    *,
    intake_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic status snapshot from the intake artifact.

    Args:
        intake_artifact_path: override the default
            ``logs/development_roadmap_intake/latest.json`` source.
            Tests pass a synthetic fixture here.
        generated_at_utc: override the wrapper's report timestamp.
            Tests inject this for byte-stable output.
    """
    ip = (
        intake_artifact_path
        if intake_artifact_path is not None
        else dri.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(ip)
    if payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": ts,
            "intake_artifact_path": str(ip),
            "intake_artifact_available": False,
            "intake_module_version": dri.MODULE_VERSION,
            "step5_enabled_substage": dri.STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": dri.step5_implementation_allowed,
            "schema_pinned": _schema_pinned(),
            "counts": _empty_counts(),
            "validation_warnings": [],
            "note": "intake_artifact_absent",
        }

    upstream_counts = payload.get("counts") or {}
    if not isinstance(upstream_counts, dict):
        upstream_counts = {}

    by_source_kind = (
        upstream_counts.get("by_source_kind")
        if isinstance(upstream_counts.get("by_source_kind"), dict)
        else {}
    )
    by_candidate_kind = (
        upstream_counts.get("by_candidate_kind")
        if isinstance(upstream_counts.get("by_candidate_kind"), dict)
        else {}
    )
    by_intake_status = (
        upstream_counts.get("by_intake_status")
        if isinstance(upstream_counts.get("by_intake_status"), dict)
        else {}
    )
    by_decision = (
        upstream_counts.get("by_execution_authority_decision")
        if isinstance(
            upstream_counts.get("by_execution_authority_decision"), dict
        )
        else {}
    )

    counts: dict[str, Any] = {
        "total": int(upstream_counts.get("total") or 0),
        "human_needed": int(upstream_counts.get("human_needed") or 0),
        "eligible": int(upstream_counts.get("eligible") or 0),
        "blocked": int(upstream_counts.get("blocked") or 0),
        "by_source_kind": {
            k: int(by_source_kind.get(k) or 0) for k in dri.SOURCE_KINDS
        },
        "by_candidate_kind": {
            k: int(by_candidate_kind.get(k) or 0) for k in dri.CANDIDATE_KINDS
        },
        "by_intake_status": {
            s: int(by_intake_status.get(s) or 0) for s in dri.INTAKE_STATUSES
        },
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: int(
                by_decision.get(ea.DECISION_AUTO_ALLOWED) or 0
            ),
            ea.DECISION_NEEDS_HUMAN: int(
                by_decision.get(ea.DECISION_NEEDS_HUMAN) or 0
            ),
            ea.DECISION_PERMANENTLY_DENIED: int(
                by_decision.get(ea.DECISION_PERMANENTLY_DENIED) or 0
            ),
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "intake_artifact_path": str(ip),
        "intake_artifact_available": True,
        "intake_module_version": payload.get("module_version"),
        "intake_schema_version": payload.get("schema_version"),
        "intake_generated_at_utc": payload.get("generated_at_utc"),
        "intake_note": payload.get("note"),
        "step5_enabled_substage": payload.get("step5_enabled_substage")
        or dri.STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": bool(
            payload.get("step5_implementation_allowed")
        ),
        "schema_pinned": _schema_pinned(),
        "counts": counts,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "intake_artifact_present",
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_roadmap_intake_status._atomic_write_json refuses "
            f"non-intake-status-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_roadmap_intake_status.",
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
        prog="python -m reporting.development_roadmap_intake_status",
        description=(
            "Read-only summary of "
            "logs/development_roadmap_intake/latest.json. Decides "
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
            "logs/development_roadmap_intake_status/latest.json "
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
