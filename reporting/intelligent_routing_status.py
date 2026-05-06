"""v3.15.16 PR-D — Intelligent Routing status reporter (advisory).

Stand-alone status reporter for the advisory Intelligent Routing
Layer artifact at ``logs/intelligent_routing/latest.json``.

Per Critical-review item 3, this is a **separate** module — it does
**not** modify ``reporting/governance_status.py``.

What it reports
---------------

A single envelope summarising the latest routing artifact:

* artifact presence (``present`` / ``not_available`` / ``malformed``)
* total decisions
* counts by ``advisory_suppression_reason`` (none / dead_zone /
  near_duplicate)
* counts by ``info_gain_bucket``
* counts by ``orthogonality_bucket``
* the routing-effect framing (``advisory_only`` / ``none``) re-stated
  verbatim so a downstream consumer does not need to read the
  decisions array

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib-only. No subprocess. No network. No git. No gh.
* No imports from ``automation``, ``agent.risk``, ``agent.execution``,
  ``broker``, ``live``, ``paper``, ``shadow``, ``trading``,
  ``dashboard``, or ``reporting.governance_status``.
* Importing the module performs no I/O.
* Default CLI mode is ``--no-write``: prints JSON to stdout, writes
  nothing. ``--write`` persists exactly one file at
  ``logs/intelligent_routing_status/latest.json``.
* Never writes to ``research/**``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final, Sequence

from reporting.intelligent_routing import (
    LATEST_OUTPUT_PATH as _ROUTING_LATEST_OUTPUT_PATH,
    REPO_ROOT,
    ROUTING_EFFECT_ADVISORY_ONLY,
    QUEUE_ORDERING_EFFECT_NONE,
    SCHEMA_VERSION as _ROUTING_SCHEMA_VERSION,
)

MODULE_VERSION: Final[str] = "v3.15.16"
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "intelligent_routing_status"

STATUS_OUTPUT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "intelligent_routing_status"
)
STATUS_LATEST_OUTPUT_PATH: Final[Path] = STATUS_OUTPUT_DIR / "latest.json"

ARTIFACT_PRESENT: Final[str] = "present"
ARTIFACT_NOT_AVAILABLE: Final[str] = "not_available"
ARTIFACT_MALFORMED: Final[str] = "malformed"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _provenance_entry(path: Path) -> dict[str, str]:
    try:
        if not path.exists() or not path.is_file():
            return {"status": ARTIFACT_NOT_AVAILABLE}
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        mtime_dt = _dt.datetime.fromtimestamp(
            path.stat().st_mtime, tz=_dt.timezone.utc,
        )
        return {
            "status": ARTIFACT_PRESENT,
            "sha256": digest,
            "mtime_utc": mtime_dt.isoformat(),
        }
    except OSError:
        return {"status": ARTIFACT_NOT_AVAILABLE}


def _now_utc_default() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _count_by(decisions: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        v = d.get(key)
        if v is None:
            label = "none"
        elif isinstance(v, str):
            label = v
        else:
            label = str(v)
        out[label] = out.get(label, 0) + 1
    return out


def build_status(
    *,
    routing_artifact_path: Path = _ROUTING_LATEST_OUTPUT_PATH,
    now_utc: _dt.datetime | None = None,
) -> dict[str, Any]:
    """Build the deterministic status envelope from the latest routing
    artifact. Pure (modulo file read). Never writes.
    """
    as_of = now_utc if isinstance(now_utc, _dt.datetime) else _now_utc_default()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=_dt.timezone.utc)
    try:
        rel = str(
            routing_artifact_path.resolve().relative_to(REPO_ROOT)
        ).replace("\\", "/")
    except ValueError:
        rel = str(routing_artifact_path)
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "version": MODULE_VERSION,
        "generated_at_utc": as_of.astimezone(_dt.timezone.utc).isoformat(),
        "routing_artifact_path": rel,
        "routing_artifact_status": ARTIFACT_NOT_AVAILABLE,
        "routing_artifact_provenance": _provenance_entry(routing_artifact_path),
        "routing_effect": ROUTING_EFFECT_ADVISORY_ONLY,
        "queue_ordering_effect": QUEUE_ORDERING_EFFECT_NONE,
        "routing_schema_version": _ROUTING_SCHEMA_VERSION,
        "summary": {
            "total": 0,
            "by_advisory_suppression_reason": {},
            "by_info_gain_bucket": {},
            "by_orthogonality_bucket": {},
        },
        "error": None,
    }
    payload = _read_json(routing_artifact_path)
    if not routing_artifact_path.exists():
        envelope["error"] = "routing_artifact_not_found"
        return envelope
    if payload is None:
        envelope["routing_artifact_status"] = ARTIFACT_MALFORMED
        envelope["error"] = "routing_artifact_unreadable_or_invalid_json"
        return envelope
    decisions = payload.get("decisions") or []
    if not isinstance(decisions, list):
        envelope["routing_artifact_status"] = ARTIFACT_MALFORMED
        envelope["error"] = "decisions_field_not_a_list"
        return envelope
    envelope["routing_artifact_status"] = ARTIFACT_PRESENT
    envelope["summary"] = {
        "total": len(decisions),
        "by_advisory_suppression_reason": _count_by(
            decisions, "advisory_suppression_reason",
        ),
        "by_info_gain_bucket": _count_by(decisions, "info_gain_bucket"),
        "by_orthogonality_bucket": _count_by(
            decisions, "orthogonality_bucket",
        ),
    }
    return envelope


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


CLI_DESCRIPTION: Final[str] = (
    "v3.15.16 advisory Intelligent Routing status reporter. "
    "Default: --no-write (prints JSON, writes nothing). "
    "Pass --write to persist logs/intelligent_routing_status/latest.json. "
    "Routing effect: advisory_only. Queue ordering effect: none."
)


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.intelligent_routing_status",
        description=CLI_DESCRIPTION,
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument(
        "--no-write",
        dest="write",
        action="store_false",
        help="Print the status to stdout; write nothing (default).",
    )
    grp.add_argument(
        "--write",
        dest="write",
        action="store_true",
        help="Persist logs/intelligent_routing_status/latest.json.",
    )
    parser.set_defaults(write=False)
    parser.add_argument(
        "--indent", type=int, default=2,
        help="JSON indent for stdout (default: 2).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)
    payload = build_status()
    if args.write:
        _atomic_write_json(STATUS_LATEST_OUTPUT_PATH, payload)
    sys.stdout.write(
        json.dumps(payload, indent=int(args.indent), sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_MALFORMED",
    "ARTIFACT_NOT_AVAILABLE",
    "ARTIFACT_PRESENT",
    "MODULE_VERSION",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STATUS_LATEST_OUTPUT_PATH",
    "STATUS_OUTPUT_DIR",
    "build_status",
    "main",
]
