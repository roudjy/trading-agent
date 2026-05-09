"""N2b-1 — Notification Dispatch Outbox status summary.

Read-only projection that consumes
``logs/notification_dispatch_outbox/latest.json`` and emits a compact
operator-facing status summary, counting records by
``outbound_delivery_intent``, ``event_kind``, ``event_severity``, and
``source_module``. Surfaces an ``operator_attention_count`` of failure
records (``failed_secret_check`` + ``failed_stub_provider``).

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.notification_dispatch_outbox`` (read-only) +
  ``reporting.notification_event`` (read-only) +
  ``reporting.notification_dispatcher`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no ``socket``,
  no ``urllib``, no ``requests``, no ``httpx``, no ``aiohttp``, no
  Web Push library.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  or ``trading``.
* Pure read on the upstream artefact; never mutates ``latest.json``.
* Atomic write only under
  ``logs/notification_dispatch_outbox_status/``.

CLI::

    python -m reporting.notification_dispatch_outbox_status
    python -m reporting.notification_dispatch_outbox_status --indent 2
    python -m reporting.notification_dispatch_outbox_status --no-write
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

from reporting import notification_dispatch_outbox as ndo
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N2b1"
REPORT_KIND: Final[str] = "notification_dispatch_outbox_status"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "notification_dispatch_outbox_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatch_outbox_status/latest.json"
)

_WRITE_PREFIX: Final[str] = "logs/notification_dispatch_outbox_status/"

#: Failure intents that warrant operator attention.
_FAILURE_INTENTS: Final[frozenset[str]] = frozenset(
    {"failed_secret_check", "failed_stub_provider"}
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


def _schema_pinned() -> dict[str, Any]:
    return {
        "outbound_delivery_intents": list(ndo.OUTBOUND_DELIVERY_INTENTS),
        "audit_event_names": list(ndo.AUDIT_EVENT_NAMES),
        "push_payload_keys": list(ndo.PUSH_PAYLOAD_KEYS),
        "outbox_record_schema_keys": list(ndo.OUTBOX_RECORD_SCHEMA_KEYS),
        "notification_event_kinds": list(ne.EVENT_KINDS),
        "notification_event_severities": list(ne.EVENT_SEVERITIES),
        "source_modules": list(nd.SOURCE_MODULES),
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "sent": 0,
        "duplicate": 0,
        "skipped_not_ready": 0,
        "rate_limited_outbound": 0,
        "failed_secret_check": 0,
        "failed_stub_provider": 0,
        "by_outbound_delivery_intent": {
            v: 0 for v in ndo.OUTBOUND_DELIVERY_INTENTS
        },
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_source_module": {m: 0 for m in nd.SOURCE_MODULES},
    }


def collect_status(
    *,
    outbox_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    op = (
        outbox_artifact_path
        if outbox_artifact_path is not None
        else ndo.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(op)
    if payload is None:
        snap = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": ts,
            "outbox_artifact_path": str(op),
            "outbox_artifact_available": False,
            "outbox_module_version": ndo.MODULE_VERSION,
            "step5_enabled_substage": ndo.STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": ndo.step5_implementation_allowed,
            "schema_pinned": _schema_pinned(),
            "counts": _empty_counts(),
            "operator_attention_count": 0,
            "validation_warnings": [],
            "note": "outbox_artifact_absent",
        }
        assert_no_secrets(snap)
        return snap

    upstream_counts = payload.get("counts") or {}
    if not isinstance(upstream_counts, dict):
        upstream_counts = {}

    records = (
        payload.get("records") if isinstance(payload.get("records"), list) else []
    )
    records = [r for r in records if isinstance(r, dict)]

    counts = _empty_counts()
    counts["total"] = int(upstream_counts.get("total") or len(records))
    for v in ndo.OUTBOUND_DELIVERY_INTENTS:
        counts[v] = int(upstream_counts.get(v) or 0)

    by_di = upstream_counts.get("by_outbound_delivery_intent") or {}
    if isinstance(by_di, dict):
        for v in ndo.OUTBOUND_DELIVERY_INTENTS:
            counts["by_outbound_delivery_intent"][v] = int(by_di.get(v) or 0)

    by_kind = upstream_counts.get("by_event_kind") or {}
    if isinstance(by_kind, dict):
        for k in ne.EVENT_KINDS:
            counts["by_event_kind"][k] = int(by_kind.get(k) or 0)

    by_sev = upstream_counts.get("by_event_severity") or {}
    if isinstance(by_sev, dict):
        for s in ne.EVENT_SEVERITIES:
            counts["by_event_severity"][s] = int(by_sev.get(s) or 0)

    by_sm = upstream_counts.get("by_source_module") or {}
    if isinstance(by_sm, dict):
        for m in nd.SOURCE_MODULES:
            counts["by_source_module"][m] = int(by_sm.get(m) or 0)

    operator_attention_count = sum(
        1 for r in records
        if r.get("outbound_delivery_intent") in _FAILURE_INTENTS
    )

    snap = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "outbox_artifact_path": str(op),
        "outbox_artifact_available": True,
        "outbox_module_version": payload.get("module_version"),
        "outbox_schema_version": payload.get("schema_version"),
        "outbox_generated_at_utc": payload.get("generated_at_utc"),
        "outbox_note": payload.get("note"),
        "step5_enabled_substage": payload.get("step5_enabled_substage")
        or ndo.STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": bool(
            payload.get("step5_implementation_allowed")
        ),
        "schema_pinned": _schema_pinned(),
        "counts": counts,
        "operator_attention_count": operator_attention_count,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "outbox_artifact_present",
    }
    assert_no_secrets(snap)
    return snap


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatch_outbox_status._atomic_write_json "
            f"refuses non-status-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatch_outbox_status.",
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
        prog="python -m reporting.notification_dispatch_outbox_status",
        description=(
            "Read-only summary of "
            "logs/notification_dispatch_outbox/latest.json. Decides "
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
            "logs/notification_dispatch_outbox_status/latest.json "
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
