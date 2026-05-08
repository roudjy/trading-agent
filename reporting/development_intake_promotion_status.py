"""A16a — Intake Candidate Promotion Staging status summary.

Read-only projection that consumes
``logs/development_intake_promotion/latest.json`` and emits a compact
operator-facing status summary, counting rows by ``decision_state``,
``notification_event_kind``, ``notification_event_severity``,
``reclassified_execution_authority_decision``,
``already_in_seed_jsonl``, and ``already_in_delegation_seed``.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.development_intake_promotion`` (read-only) +
  ``reporting.notification_event`` (read-only) +
  ``reporting.execution_authority`` (read-only).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* Pure read on the upstream artefact; never mutates ``latest.json``.
* Atomic write only under
  ``logs/development_intake_promotion_status/``.

CLI::

    python -m reporting.development_intake_promotion_status
    python -m reporting.development_intake_promotion_status --indent 2
    python -m reporting.development_intake_promotion_status --no-write
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

from reporting import development_intake_promotion as dip
from reporting import execution_authority as ea
from reporting import notification_event as ne

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A16a"
REPORT_KIND: Final[str] = "development_intake_promotion_status"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_intake_promotion_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_intake_promotion_status/latest.json"
)

_WRITE_PREFIX: Final[str] = "logs/development_intake_promotion_status/"


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
        "decision_states": list(dip.DECISION_STATES),
        "promotion_targets": list(dip.PROMOTION_TARGETS),
        "validation_warnings": list(dip.VALIDATION_WARNINGS),
        "notification_event_kinds": list(ne.EVENT_KINDS),
        "notification_event_severities": list(ne.EVENT_SEVERITIES),
        "reclassified_execution_authority_decisions": [
            ea.DECISION_AUTO_ALLOWED,
            ea.DECISION_NEEDS_HUMAN,
            ea.DECISION_PERMANENTLY_DENIED,
        ],
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "eligible": 0,
        "human_needed": 0,
        "blocked": 0,
        "already_promoted": 0,
        "classification_drift": 0,
        "already_in_seed_jsonl": 0,
        "already_in_delegation_seed": 0,
        "by_decision_state": {s: 0 for s in dip.DECISION_STATES},
        "by_notification_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_notification_event_severity": {
            s: 0 for s in ne.EVENT_SEVERITIES
        },
        "by_reclassified_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }


def collect_status(
    *,
    promotion_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic status snapshot from the promotion
    artifact."""
    pp = (
        promotion_artifact_path
        if promotion_artifact_path is not None
        else dip.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(pp)
    if payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": ts,
            "promotion_artifact_path": str(pp),
            "promotion_artifact_available": False,
            "promotion_module_version": dip.MODULE_VERSION,
            "step5_enabled_substage": dip.STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": dip.step5_implementation_allowed,
            "schema_pinned": _schema_pinned(),
            "counts": _empty_counts(),
            "validation_warnings": [],
            "note": "promotion_artifact_absent",
        }

    upstream_counts = payload.get("counts") or {}
    if not isinstance(upstream_counts, dict):
        upstream_counts = {}

    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    rows = [r for r in rows if isinstance(r, dict)]

    counts = _empty_counts()
    counts["total"] = int(upstream_counts.get("total") or len(rows))
    counts["eligible"] = int(upstream_counts.get("eligible") or 0)
    counts["human_needed"] = int(upstream_counts.get("human_needed") or 0)
    counts["blocked"] = int(upstream_counts.get("blocked") or 0)
    counts["already_promoted"] = int(
        upstream_counts.get("already_promoted") or 0
    )
    counts["classification_drift"] = int(
        upstream_counts.get("classification_drift") or 0
    )
    counts["already_in_seed_jsonl"] = int(
        upstream_counts.get("already_in_seed_jsonl") or 0
    )
    counts["already_in_delegation_seed"] = int(
        upstream_counts.get("already_in_delegation_seed") or 0
    )

    by_ds = upstream_counts.get("by_decision_state") or {}
    if isinstance(by_ds, dict):
        for s in dip.DECISION_STATES:
            counts["by_decision_state"][s] = int(by_ds.get(s) or 0)

    by_kind = upstream_counts.get("by_notification_event_kind") or {}
    if isinstance(by_kind, dict):
        for k in ne.EVENT_KINDS:
            counts["by_notification_event_kind"][k] = int(by_kind.get(k) or 0)

    by_sev = upstream_counts.get("by_notification_event_severity") or {}
    if isinstance(by_sev, dict):
        for s in ne.EVENT_SEVERITIES:
            counts["by_notification_event_severity"][s] = int(
                by_sev.get(s) or 0
            )

    by_dec = (
        upstream_counts.get("by_reclassified_execution_authority_decision")
        or {}
    )
    if isinstance(by_dec, dict):
        for d in (
            ea.DECISION_AUTO_ALLOWED,
            ea.DECISION_NEEDS_HUMAN,
            ea.DECISION_PERMANENTLY_DENIED,
        ):
            counts["by_reclassified_execution_authority_decision"][d] = int(
                by_dec.get(d) or 0
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "promotion_artifact_path": str(pp),
        "promotion_artifact_available": True,
        "promotion_module_version": payload.get("module_version"),
        "promotion_schema_version": payload.get("schema_version"),
        "promotion_generated_at_utc": payload.get("generated_at_utc"),
        "promotion_note": payload.get("note"),
        "step5_enabled_substage": payload.get("step5_enabled_substage")
        or dip.STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": bool(
            payload.get("step5_implementation_allowed")
        ),
        "schema_pinned": _schema_pinned(),
        "counts": counts,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "promotion_artifact_present",
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_intake_promotion_status._atomic_write_json "
            f"refuses non-status-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_intake_promotion_status.",
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
        prog="python -m reporting.development_intake_promotion_status",
        description=(
            "Read-only summary of "
            "logs/development_intake_promotion/latest.json. "
            "Decides nothing; mutates nothing."
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
            "logs/development_intake_promotion_status/latest.json "
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
