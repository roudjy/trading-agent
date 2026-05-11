"""A24 — Autonomous Development Workloop event-taxonomy projector.

Pure stdlib-only projector that reads the existing
``logs/autonomous_workloop/latest.json`` digest (produced by
``reporting.autonomous_workloop``, which is allowed to call ``git``
/ ``gh`` itself) and projects each significant workloop signal into
the closed N1 ``notification_event`` taxonomy.

A24 is the read-only **wiring layer** between the workloop and the
notification engine. It does NOT replace the workloop. It does NOT
emit notifications. It does NOT call ``git``, ``gh``, or any
network/subprocess surface itself — it only reads the workloop's
already-collected digest.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.notification_event`` (read-only) +
  ``reporting.autonomous_workloop`` (imported only for
  ``MODULE_VERSION`` constant pinning; no function call) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* AST-pinned: no callable in this module invokes any function from
  ``reporting.autonomous_workloop``. The upstream module is imported
  only for its ``MODULE_VERSION`` constant.
* Atomic write only under ``logs/development_workloop_events/...``.
* Per-row schema is closed and exact. Bounded scalars only — no
  diff content, no PR body, no command summary.
* The projector NEVER emits a notification, NEVER mints an approval
  token, NEVER merges or deploys.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.
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

from reporting import autonomous_workloop as _aw  # for MODULE_VERSION only
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A24"
REPORT_KIND: Final[str] = "development_workloop_events"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed workloop signal-source vocabulary. Each value is one of
#: the known workloop digest sections A24 projects from.
WORKLOOP_SIGNAL_SOURCES: Final[tuple[str, ...]] = (
    "pr_queue",
    "dependabot_queue",
    "roadmap_queue",
    "blocked_items",
    "audit_chain_status",
    "governance_status",
    "actions_taken",
)

#: Closed validation-warning vocabulary.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "workloop_digest_absent",
    "workloop_digest_unparseable",
    "workloop_signal_invalid",
)

#: Per-row schema, exact and ordered.
EVENT_ROW_KEYS: Final[tuple[str, ...]] = (
    "workloop_event_id",
    "source_signal",
    "source_index",
    "event_kind",
    "event_severity",
    "decision_or_outcome",
    "title",
    "summary",
    "extracted_at",
)

#: Maximum rows kept in any single snapshot. Bounds the artefact
#: regardless of how large the upstream workloop digest grows.
MAX_EVENT_ROWS: Final[int] = 128

#: Bounded length for free-text scalars. The workloop carries
#: bounded strings already; this is defense-in-depth.
MAX_TITLE_LEN: Final[int] = 200
MAX_SUMMARY_LEN: Final[int] = 480

#: Wrapper-level note vocabulary.
NOTE_NO_DIGEST: Final[str] = "workloop_digest_absent"
NOTE_NO_SIGNALS: Final[str] = "no_workloop_signals"
NOTE_SIGNALS_PRESENT: Final[str] = "workloop_signals_present"

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_workloop_events"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_workloop_events/latest.json"
)

#: Upstream workloop digest path. Produced by
#: ``reporting.autonomous_workloop``; A24 reads it only.
UPSTREAM_WORKLOOP_DIGEST_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "autonomous_workloop" / "latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_workloop_events/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "calls_workloop_functions": False,
    "calls_gh_cli": False,
    "calls_git_cli": False,
    "uses_subprocess_or_network": False,
    "emits_real_notification": False,
    "mints_approval_token": False,
    "merges_or_deploys": False,
    "mutates_research_artifacts": False,
    "writes_to_seed_jsonl": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "diagnostics_do_not_trade": True,
    "no_approval_from_notification_click_alone": True,
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


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


def _bounded(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def _workloop_event_id(source_signal: str, source_index: int, key: str) -> str:
    """Stable id derived from source signal + index + identity key."""
    return f"awe_{source_signal}_{source_index:04d}_{key[:32]}"


# ---------------------------------------------------------------------------
# Signal-to-N1 mapping (closed table)
# ---------------------------------------------------------------------------


def _classify_pr_queue_item(item: dict[str, Any]) -> tuple[str, str]:
    """Return ``(event_kind, decision_or_outcome)`` for one PR-queue
    item. Closed N1 kind only."""
    decision = str(item.get("decision") or "operator_click")
    if decision == "auto_merge_eligible":
        return ("pr_lifecycle_event", "auto_merge_eligible")
    if decision == "operator_click":
        return ("pr_lifecycle_event", "operator_click")
    if decision == "blocked":
        return ("pr_lifecycle_event", "blocked")
    return ("pr_lifecycle_event", decision)


def _classify_dependabot_item(item: dict[str, Any]) -> tuple[str, str]:
    decision = str(item.get("decision") or "operator_click")
    return ("pr_lifecycle_event", decision)


def _classify_roadmap_item(item: dict[str, Any]) -> tuple[str, str]:
    risk = str(item.get("risk_class") or "")
    if "blocked" in risk.lower():
        return ("queue_item_blocked", risk or "blocked")
    return ("queue_item_proposed", risk or "proposed")


def _classify_blocked_item(item: dict[str, Any]) -> tuple[str, str]:
    return ("queue_item_blocked", str(item.get("reason") or "blocked"))


def _classify_audit_chain(status: dict[str, Any]) -> tuple[str, str]:
    s = str(status.get("status") or "unknown").lower()
    if s == "intact":
        return ("audit_chain_anomaly", "intact")  # severity routes to critical regardless of value
    return ("audit_chain_anomaly", s or "anomaly")


def _classify_governance(status: dict[str, Any]) -> tuple[str, str]:
    s = str(status.get("status") or "unknown").lower()
    if s == "ok":
        return ("operational_digest_emitted", "ok")
    return ("governance_violation_detected", s or "anomaly")


def _classify_action(action: dict[str, Any]) -> tuple[str, str]:
    outcome = str(action.get("outcome") or "ok")
    return ("operational_digest_emitted", outcome)


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _build_row(
    *,
    source_signal: str,
    source_index: int,
    item: dict[str, Any],
    classifier,
    title: str,
    summary: str,
    extracted_at: str,
) -> dict[str, Any]:
    event_kind, decision = classifier(item)
    severity = ne.route_for(event_kind)
    identity_key = (
        item.get("item_id")
        or item.get("branch_or_pr")
        or item.get("target")
        or item.get("kind")
        or item.get("status")
        or "anon"
    )
    row: dict[str, Any] = {
        "workloop_event_id": _workloop_event_id(
            source_signal, source_index, str(identity_key)
        ),
        "source_signal": source_signal,
        "source_index": source_index,
        "event_kind": event_kind,
        "event_severity": severity,
        "decision_or_outcome": decision,
        "title": _bounded(title, MAX_TITLE_LEN),
        "summary": _bounded(summary, MAX_SUMMARY_LEN),
        "extracted_at": extracted_at,
    }
    assert set(row.keys()) == set(EVENT_ROW_KEYS)
    return row


# ---------------------------------------------------------------------------
# Per-signal projection
# ---------------------------------------------------------------------------


def _project_pr_queue(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    items = payload.get("pr_queue") or []
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if len(rows) >= MAX_EVENT_ROWS:
            return
        rows.append(
            _build_row(
                source_signal="pr_queue",
                source_index=i,
                item=item,
                classifier=_classify_pr_queue_item,
                title=str(item.get("title") or ""),
                summary=f"decision={item.get('decision')}; risk={item.get('risk_class')}",
                extracted_at=extracted_at,
            )
        )


def _project_dependabot_queue(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    items = payload.get("dependabot_queue") or []
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if len(rows) >= MAX_EVENT_ROWS:
            return
        rows.append(
            _build_row(
                source_signal="dependabot_queue",
                source_index=i,
                item=item,
                classifier=_classify_dependabot_item,
                title=str(item.get("title") or ""),
                summary=f"decision={item.get('decision')}; risk={item.get('risk_class')}",
                extracted_at=extracted_at,
            )
        )


def _project_roadmap_queue(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    items = payload.get("roadmap_queue") or []
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if len(rows) >= MAX_EVENT_ROWS:
            return
        rows.append(
            _build_row(
                source_signal="roadmap_queue",
                source_index=i,
                item=item,
                classifier=_classify_roadmap_item,
                title=str(item.get("title") or ""),
                summary=f"risk={item.get('risk_class')}",
                extracted_at=extracted_at,
            )
        )


def _project_blocked_items(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    items = payload.get("blocked_items") or []
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if len(rows) >= MAX_EVENT_ROWS:
            return
        rows.append(
            _build_row(
                source_signal="blocked_items",
                source_index=i,
                item=item,
                classifier=_classify_blocked_item,
                title=str(item.get("title") or item.get("item_id") or ""),
                summary=f"reason={item.get('reason')}",
                extracted_at=extracted_at,
            )
        )


def _project_audit_chain(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    status = payload.get("audit_chain_status")
    if not isinstance(status, dict):
        return
    if len(rows) >= MAX_EVENT_ROWS:
        return
    rows.append(
        _build_row(
            source_signal="audit_chain_status",
            source_index=0,
            item=status,
            classifier=_classify_audit_chain,
            title="audit_chain_status",
            summary=f"status={status.get('status')}; ledger={status.get('ledger_path')}",
            extracted_at=extracted_at,
        )
    )


def _project_governance(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    status = payload.get("governance_status")
    if not isinstance(status, dict):
        return
    if len(rows) >= MAX_EVENT_ROWS:
        return
    rows.append(
        _build_row(
            source_signal="governance_status",
            source_index=0,
            item=status,
            classifier=_classify_governance,
            title="governance_status",
            summary=f"status={status.get('status')}",
            extracted_at=extracted_at,
        )
    )


def _project_actions(
    payload: dict[str, Any], *, extracted_at: str, rows: list[dict[str, Any]]
) -> None:
    actions = payload.get("actions_taken") or []
    if not isinstance(actions, list):
        return
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        if len(rows) >= MAX_EVENT_ROWS:
            return
        rows.append(
            _build_row(
                source_signal="actions_taken",
                source_index=i,
                item=action,
                classifier=_classify_action,
                title=str(action.get("kind") or "action"),
                summary=f"outcome={action.get('outcome')}; target={action.get('target')}",
                extracted_at=extracted_at,
            )
        )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_source_signal": {s: 0 for s in WORKLOOP_SIGNAL_SOURCES},
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        sig = row.get("source_signal")
        if isinstance(sig, str) and sig in counts["by_source_signal"]:
            counts["by_source_signal"][sig] += 1
        kind = row.get("event_kind")
        if isinstance(kind, str) and kind in counts["by_event_kind"]:
            counts["by_event_kind"][kind] += 1
        sev = row.get("event_severity")
        if isinstance(sev, str) and sev in counts["by_event_severity"]:
            counts["by_event_severity"][sev] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    workloop_digest_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic workloop-events snapshot."""
    wp = (
        workloop_digest_path
        if workloop_digest_path is not None
        else UPSTREAM_WORKLOOP_DIGEST_PATH
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(wp)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    upstream_controller_version = ""
    upstream_mode = ""
    upstream_cycle_id: int | None = None

    if payload is None:
        warnings.append("workloop_digest_absent")
        note = NOTE_NO_DIGEST
    elif not isinstance(payload, dict):
        warnings.append("workloop_digest_unparseable")
        note = NOTE_NO_DIGEST
    else:
        upstream_controller_version = str(payload.get("controller_version") or "")
        upstream_mode = str(payload.get("mode") or "")
        cid = payload.get("cycle_id")
        upstream_cycle_id = cid if isinstance(cid, int) else None
        _project_pr_queue(payload, extracted_at=ts, rows=rows)
        _project_dependabot_queue(payload, extracted_at=ts, rows=rows)
        _project_roadmap_queue(payload, extracted_at=ts, rows=rows)
        _project_blocked_items(payload, extracted_at=ts, rows=rows)
        _project_audit_chain(payload, extracted_at=ts, rows=rows)
        _project_governance(payload, extracted_at=ts, rows=rows)
        _project_actions(payload, extracted_at=ts, rows=rows)
        note = NOTE_SIGNALS_PRESENT if rows else NOTE_NO_SIGNALS

    rows.sort(key=lambda r: (r["source_signal"], r["source_index"], r["workloop_event_id"]))

    counts = _aggregate_counts(rows)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "workloop_digest_path": str(wp),
        "workloop_digest_available": payload is not None,
        "upstream_controller_version": upstream_controller_version,
        "upstream_mode": upstream_mode,
        "upstream_cycle_id": upstream_cycle_id,
        "max_event_rows": MAX_EVENT_ROWS,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "workloop_signal_sources": list(WORKLOOP_SIGNAL_SOURCES),
            "notification_event_kinds": list(ne.EVENT_KINDS),
            "notification_event_severities": list(ne.EVENT_SEVERITIES),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "event_row_keys": list(EVENT_ROW_KEYS),
        },
        "counts": counts,
        "rows": rows,
        "autonomous_workloop_module_version": _aw.CONTROLLER_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_workloop_events._atomic_write_json refuses "
            f"non-workloop-events-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_workloop_events.",
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_workloop_events",
        description=(
            "A24 Autonomous Development Workloop event-taxonomy "
            "projector. Read-only deterministic projector of "
            "logs/autonomous_workloop/latest.json. Never calls "
            "git, gh, or any workloop function. Never emits a "
            "real notification."
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
            "logs/development_workloop_events/latest.json "
            "(stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
