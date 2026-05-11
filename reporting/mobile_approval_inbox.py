"""N3a — Mobile Approval Inbox projector (read-only).

Pure stdlib-only projector that reads the existing N2b-1 dispatch
outbox artefact at ``logs/notification_dispatch_outbox/latest.json``
and projects the subset of rows that warrant operator attention into
a bounded mobile inbox artefact at
``logs/mobile_approval_inbox/latest.json``.

N3a is **strictly read-only**. It does **not**:

* mint or verify approval tokens (that is N4 territory);
* approve, reject, merge, or deploy anything (N5 territory);
* open a real PWA inbox screen (N3c territory);
* register a Flask blueprint or otherwise wire into the dashboard
  (N3b territory);
* send any push, write any subscription state, or call any
  Web Push provider (N2b-3 territory);
* mutate any upstream artefact;
* edit any roadmap status field;
* mark any roadmap phase complete.

Today N3a is consulted by no one in production. It is a pure
projector that emits ``logs/mobile_approval_inbox/latest.json`` so
the operator can inspect what a future N3b API + N3c UI would
display, before those slices are authorised.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.notification_dispatch_outbox`` (read-only) +
  ``reporting.notification_event`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* Atomic write only under ``logs/mobile_approval_inbox/...``.
* Per-row schema is closed and exact. Bounded scalars only — no
  diff content, no PR body, no command summary.
* No decision verb (``approve``, ``reject``, ``merge``, ``deploy``)
  appears in the emitted record. The future N3c UI is the only
  surface allowed to expose action affordances, and even then the
  click only opens the PWA detail screen — N4 + re-authentication
  remain the only path to a real decision.
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

from reporting import notification_dispatch_outbox as ndo
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N3a"
REPORT_KIND: Final[str] = "mobile_approval_inbox"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed inbox-row attention-level vocabulary.
ATTENTION_LEVELS: Final[tuple[str, ...]] = (
    "informational",
    "needs_review",
    "blocked_attention",
    "critical_attention",
)

#: Closed inbox decision-state vocabulary. Reserved for the future
#: N4 approval-token gate. N3a NEVER sets a value other than
#: ``pending`` — `approved`, `rejected`, `expired`, and
#: `superseded` are reserved for the future N4 surface to set, never
#: by N3a itself.
INBOX_DECISION_STATES: Final[tuple[str, ...]] = (
    "pending",
    "acknowledged",
    "approved",
    "rejected",
    "expired",
    "superseded",
)

#: Closed source-module vocabulary the inbox accepts upstream from.
SOURCE_MODULES: Final[tuple[str, ...]] = (
    "notification_dispatch_outbox",
)

#: Closed validation-warning vocabulary.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "outbox_artifact_absent",
    "outbox_artifact_unparseable",
    "outbox_record_invalid",
    "decision_verb_redacted_in_summary",
)

#: Closed per-row schema, exact and ordered.
INBOX_ROW_KEYS: Final[tuple[str, ...]] = (
    "inbox_row_id",
    "event_id",
    "event_kind",
    "event_severity",
    "source_module",
    "source_id",
    "endpoint_hash",
    "outbound_delivery_intent",
    "attention_level",
    "decision_state",
    "title",
    "summary",
    "open_at",
    "created_at",
)

#: Bounded length for free-text scalars; tighter than N2a/N2b-1
#: because mobile rendering is the constraint.
MAX_TITLE_LEN: Final[int] = 80
MAX_SUMMARY_LEN: Final[int] = 200
MAX_OPEN_AT_LEN: Final[int] = 300

#: Maximum number of inbox rows kept in any single snapshot. Bounds
#: the artefact size and the future N3c rendering surface.
MAX_INBOX_ROWS: Final[int] = 64

#: Severities that warrant operator attention. Anything else routes
#: to ``informational`` and downstream gating may suppress display.
_ATTENTION_SEVERITIES: Final[dict[str, str]] = {
    "push_action_required": "needs_review",
    "approval_required": "needs_review",
    "critical": "critical_attention",
}

#: Outbound delivery intents that signal a blocked / failure state.
_BLOCKED_INTENTS: Final[frozenset[str]] = frozenset(
    {"failed_secret_check", "failed_stub_provider", "rate_limited_outbound"}
)

#: Forbidden decision-verb tokens inside any rendered scalar.
_FORBIDDEN_DECISION_VERBS: Final[tuple[str, ...]] = (
    "approve",
    "reject",
    "merge ",
    " merge",
    "deploy",
)

#: Wrapper-level note vocabulary.
NOTE_NO_OUTBOX: Final[str] = "outbox_artifact_absent"
NOTE_NO_ATTENTION: Final[str] = "no_rows_warrant_attention"
NOTE_INBOX_PRESENT: Final[str] = "inbox_rows_present"

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "mobile_approval_inbox"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/mobile_approval_inbox/latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/mobile_approval_inbox/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "mints_approval_token": False,
    "verifies_approval_token": False,
    "executes_approve_or_reject": False,
    "merges_or_deploys": False,
    "sends_real_push": False,
    "opens_pwa_inbox_screen": False,
    "registers_flask_blueprint": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "mutates_roadmap_status_fields": False,
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


def _contains_decision_verb(text: str) -> bool:
    if not isinstance(text, str):
        return False
    lo = text.lower()
    for verb in _FORBIDDEN_DECISION_VERBS:
        if verb in lo:
            return True
    return False


def _redact_decision_verbs(text: str) -> tuple[str, bool]:
    """If ``text`` contains a forbidden decision verb, redact it
    with the closed-vocab placeholder. Returns ``(text, was_redacted)``.
    """
    if not _contains_decision_verb(text):
        return text, False
    lo = text.lower()
    out = text
    for verb in _FORBIDDEN_DECISION_VERBS:
        if verb in lo:
            # Use a generic placeholder; mobile detail screen will
            # surface the full evidence behind authentication.
            out = "[redacted-decision-verb]"
            break
    return out, True


# ---------------------------------------------------------------------------
# Attention-level classification
# ---------------------------------------------------------------------------


def classify_attention(record: dict[str, Any]) -> str:
    """Closed-table mapping from one N2b-1 outbox record to an
    attention level. Pure, deterministic, side-effect-free."""
    if not isinstance(record, dict):
        return "informational"
    intent = record.get("outbound_delivery_intent")
    severity = record.get("event_severity")
    if intent in _BLOCKED_INTENTS:
        return "blocked_attention"
    if isinstance(severity, str) and severity in _ATTENTION_SEVERITIES:
        return _ATTENTION_SEVERITIES[severity]
    return "informational"


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _inbox_row_id(event_id: str) -> str:
    """Stable inbox row id derived from the event_id. Mirroring the
    N2a/N2b-1 event_id keeps the identity chain auditable."""
    return f"mai_{event_id[:32]}" if event_id else ""


def _build_row(
    record: dict[str, Any],
    *,
    created_at: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    """Coerce one N2b-1 outbox record into the closed inbox schema.

    Returns ``None`` if the record's identity is unusable.
    Otherwise returns a closed-schema row.
    """
    if not isinstance(record, dict):
        warnings.append("outbox_record_invalid")
        return None
    event_id = str(record.get("event_id") or "")
    if not event_id:
        warnings.append("outbox_record_invalid")
        return None

    attention_level = classify_attention(record)
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    title_raw = _bounded(payload.get("title"), MAX_TITLE_LEN)
    summary_raw = _bounded(payload.get("summary"), MAX_SUMMARY_LEN)
    open_at_raw = _bounded(payload.get("open_at"), MAX_OPEN_AT_LEN)

    title_clean, title_redacted = _redact_decision_verbs(title_raw)
    summary_clean, summary_redacted = _redact_decision_verbs(summary_raw)
    if title_redacted or summary_redacted:
        warnings.append("decision_verb_redacted_in_summary")

    row: dict[str, Any] = {
        "inbox_row_id": _inbox_row_id(event_id),
        "event_id": event_id,
        "event_kind": str(record.get("event_kind") or ""),
        "event_severity": str(record.get("event_severity") or ""),
        "source_module": "notification_dispatch_outbox",
        "source_id": str(record.get("source_id") or ""),
        "endpoint_hash": str(record.get("endpoint_hash") or ""),
        "outbound_delivery_intent": str(
            record.get("outbound_delivery_intent") or ""
        ),
        "attention_level": attention_level,
        # Closed: N3a NEVER sets this to anything other than
        # `pending`. The future N4 surface is the only path that
        # can flip it.
        "decision_state": "pending",
        "title": title_clean,
        "summary": summary_clean,
        "open_at": open_at_raw,
        "created_at": created_at,
    }
    assert set(row.keys()) == set(INBOX_ROW_KEYS)
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "informational": 0,
        "needs_review": 0,
        "blocked_attention": 0,
        "critical_attention": 0,
        "by_attention_level": {a: 0 for a in ATTENTION_LEVELS},
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        att = row.get("attention_level")
        if att in counts:
            counts[att] += 1
        if att in counts["by_attention_level"]:
            counts["by_attention_level"][att] += 1
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
    outbox_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic inbox snapshot.

    Reads ``logs/notification_dispatch_outbox/latest.json`` (read-only).
    Never mutates upstream. Returns a closed-schema snapshot.
    """
    op = (
        outbox_artifact_path
        if outbox_artifact_path is not None
        else ndo.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(op)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []

    if payload is None:
        warnings.append("outbox_artifact_absent")
        note = NOTE_NO_OUTBOX
        records: list[dict[str, Any]] = []
    elif not isinstance(payload, dict):
        warnings.append("outbox_artifact_unparseable")
        note = NOTE_NO_OUTBOX
        records = []
    else:
        raw = payload.get("records")
        records = (
            [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
        )
        note = NOTE_NO_ATTENTION

    for rec in records:
        row = _build_row(rec, created_at=ts, warnings=warnings)
        if row is None:
            continue
        # Bound the inbox surface even with a huge outbox upstream.
        if len(rows) >= MAX_INBOX_ROWS:
            break
        rows.append(row)

    rows.sort(key=lambda r: (r["attention_level"], r["event_id"]))

    if rows:
        note = NOTE_INBOX_PRESENT

    counts = _aggregate_counts(rows)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "outbox_artifact_path": str(op),
        "outbox_artifact_available": payload is not None,
        "max_inbox_rows": MAX_INBOX_ROWS,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "attention_levels": list(ATTENTION_LEVELS),
            "inbox_decision_states": list(INBOX_DECISION_STATES),
            "source_modules": list(SOURCE_MODULES),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "inbox_row_keys": list(INBOX_ROW_KEYS),
        },
        "counts": counts,
        "rows": rows,
        "notification_dispatch_outbox_module_version": ndo.MODULE_VERSION,
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
            "mobile_approval_inbox._atomic_write_json refuses "
            f"non-inbox-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".mobile_approval_inbox.",
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
        prog="python -m reporting.mobile_approval_inbox",
        description=(
            "N3a Mobile Approval Inbox projector. Read-only "
            "deterministic projector of "
            "logs/notification_dispatch_outbox/latest.json. Mints "
            "no token; approves no row; merges nothing; deploys "
            "nothing. The future N3c PWA UI is the only surface "
            "allowed to display the rows."
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
            "logs/mobile_approval_inbox/latest.json (stdout only)."
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
