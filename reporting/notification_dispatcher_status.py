"""N2a — Artifact-only Notification Dispatcher status summary.

Read-only projection that consumes
``logs/notification_dispatcher/latest.json`` and emits a compact
operator-facing status summary, counting events by ``event_kind``,
``event_severity``, ``delivery_intent``, ``source_module``, and
``execution_authority_decision``. Builds an ``operator_action_list``
of ready events at severity ``push_action_required``,
``approval_required``, or ``critical``.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.notification_dispatcher`` (read-only) +
  ``reporting.notification_event`` (read-only) +
  ``reporting.execution_authority`` (read-only) +
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
* Atomic write only under ``logs/notification_dispatcher_status/``.

CLI::

    python -m reporting.notification_dispatcher_status
    python -m reporting.notification_dispatcher_status --indent 2
    python -m reporting.notification_dispatcher_status --no-write
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

from reporting import execution_authority as ea
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N2a"
REPORT_KIND: Final[str] = "notification_dispatcher_status"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "notification_dispatcher_status"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatcher_status/latest.json"
)

_WRITE_PREFIX: Final[str] = "logs/notification_dispatcher_status/"

#: Severities that warrant operator attention.
_OPERATOR_ATTENTION_SEVERITIES: Final[frozenset[str]] = frozenset(
    {"push_action_required", "approval_required", "critical"}
)

#: Maximum operator-action rows surfaced in the status summary.
_MAX_OPERATOR_ACTION_ROWS: Final[int] = 16

#: Bounded length for the per-row operator-action title/summary.
_MAX_OPERATOR_ACTION_TITLE_LEN: Final[int] = 200
_MAX_OPERATOR_ACTION_SUMMARY_LEN: Final[int] = 480


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


def _bounded(s: Any, n: int) -> str:
    if not isinstance(s, str):
        return ""
    return s[:n]


def _schema_pinned() -> dict[str, Any]:
    return {
        "delivery_intents": list(nd.DELIVERY_INTENTS),
        "source_modules": list(nd.SOURCE_MODULES),
        "notification_event_kinds": list(ne.EVENT_KINDS),
        "notification_event_severities": list(ne.EVENT_SEVERITIES),
        "execution_authority_decisions": [
            ea.DECISION_AUTO_ALLOWED,
            ea.DECISION_NEEDS_HUMAN,
            ea.DECISION_PERMANENTLY_DENIED,
        ],
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "ready": 0,
        "suppressed": 0,
        "suppressed_cooldown": 0,
        "duplicate_within_window": 0,
        "rate_limited": 0,
        "operator_attention_ready": 0,
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_delivery_intent": {d: 0 for d in nd.DELIVERY_INTENTS},
        "by_source_module": {m: 0 for m in nd.SOURCE_MODULES},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }


def _build_operator_action_list(
    events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pick out ``ready`` events at attention-warranting severities."""
    out: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("delivery_intent") != "ready":
            continue
        if ev.get("event_severity") not in _OPERATOR_ATTENTION_SEVERITIES:
            continue
        out.append(
            {
                "event_id": ev.get("event_id", ""),
                "event_kind": ev.get("event_kind", ""),
                "event_severity": ev.get("event_severity", ""),
                "source_module": ev.get("source_module", ""),
                "source_id": ev.get("source_id", ""),
                "title": _bounded(
                    ev.get("title"), _MAX_OPERATOR_ACTION_TITLE_LEN
                ),
                "summary": _bounded(
                    ev.get("summary"), _MAX_OPERATOR_ACTION_SUMMARY_LEN
                ),
                "execution_authority_decision": ev.get(
                    "execution_authority_decision", ""
                ),
                "target_path": _bounded(ev.get("target_path"), 300),
                "created_at": ev.get("created_at", ""),
            }
        )
        if len(out) >= _MAX_OPERATOR_ACTION_ROWS:
            break
    return out


def collect_status(
    *,
    dispatcher_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic status snapshot from the dispatcher
    artifact."""
    dp = (
        dispatcher_artifact_path
        if dispatcher_artifact_path is not None
        else nd.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    payload = _read_json(dp)
    if payload is None:
        snap = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": ts,
            "dispatcher_artifact_path": str(dp),
            "dispatcher_artifact_available": False,
            "dispatcher_module_version": nd.MODULE_VERSION,
            "step5_enabled_substage": nd.STEP5_ENABLED_SUBSTAGE,
            "step5_implementation_allowed": nd.step5_implementation_allowed,
            "schema_pinned": _schema_pinned(),
            "counts": _empty_counts(),
            "operator_action_list": [],
            "validation_warnings": [],
            "note": "dispatcher_artifact_absent",
        }
        assert_no_secrets(snap)
        return snap

    upstream_counts = payload.get("counts") or {}
    if not isinstance(upstream_counts, dict):
        upstream_counts = {}

    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    events = [e for e in events if isinstance(e, dict)]

    counts = _empty_counts()
    counts["total"] = int(upstream_counts.get("total") or len(events))
    counts["ready"] = int(upstream_counts.get("ready") or 0)
    counts["suppressed"] = int(upstream_counts.get("suppressed") or 0)
    counts["suppressed_cooldown"] = int(
        upstream_counts.get("suppressed_cooldown") or 0
    )
    counts["duplicate_within_window"] = int(
        upstream_counts.get("duplicate_within_window") or 0
    )
    counts["rate_limited"] = int(upstream_counts.get("rate_limited") or 0)

    by_kind = upstream_counts.get("by_event_kind") or {}
    if isinstance(by_kind, dict):
        for k in ne.EVENT_KINDS:
            counts["by_event_kind"][k] = int(by_kind.get(k) or 0)

    by_sev = upstream_counts.get("by_event_severity") or {}
    if isinstance(by_sev, dict):
        for s in ne.EVENT_SEVERITIES:
            counts["by_event_severity"][s] = int(by_sev.get(s) or 0)

    by_di = upstream_counts.get("by_delivery_intent") or {}
    if isinstance(by_di, dict):
        for d in nd.DELIVERY_INTENTS:
            counts["by_delivery_intent"][d] = int(by_di.get(d) or 0)

    by_sm = upstream_counts.get("by_source_module") or {}
    if isinstance(by_sm, dict):
        for m in nd.SOURCE_MODULES:
            counts["by_source_module"][m] = int(by_sm.get(m) or 0)

    by_dec = upstream_counts.get("by_execution_authority_decision") or {}
    if isinstance(by_dec, dict):
        for d in (
            ea.DECISION_AUTO_ALLOWED,
            ea.DECISION_NEEDS_HUMAN,
            ea.DECISION_PERMANENTLY_DENIED,
        ):
            counts["by_execution_authority_decision"][d] = int(
                by_dec.get(d) or 0
            )

    operator_action_list = _build_operator_action_list(events)
    counts["operator_attention_ready"] = len(operator_action_list)

    snap = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "dispatcher_artifact_path": str(dp),
        "dispatcher_artifact_available": True,
        "dispatcher_module_version": payload.get("module_version"),
        "dispatcher_schema_version": payload.get("schema_version"),
        "dispatcher_generated_at_utc": payload.get("generated_at_utc"),
        "dispatcher_note": payload.get("note"),
        "step5_enabled_substage": payload.get("step5_enabled_substage")
        or nd.STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": bool(
            payload.get("step5_implementation_allowed")
        ),
        "schema_pinned": _schema_pinned(),
        "counts": counts,
        "operator_action_list": operator_action_list,
        "validation_warnings": list(payload.get("validation_warnings") or []),
        "note": "dispatcher_artifact_present",
    }
    assert_no_secrets(snap)
    return snap


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatcher_status._atomic_write_json refuses "
            f"non-status-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatcher_status.",
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
        prog="python -m reporting.notification_dispatcher_status",
        description=(
            "Read-only summary of "
            "logs/notification_dispatcher/latest.json. Decides nothing; "
            "mutates nothing."
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
            "logs/notification_dispatcher_status/latest.json "
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
