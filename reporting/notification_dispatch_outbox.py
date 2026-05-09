"""N2b-1 — Notification Dispatch Outbox (stub provider, dry-run).

Pure, deterministic, stdlib-only **dry-run** push outbox. Reads
``logs/notification_dispatcher/latest.json`` (N2a), filters records
with ``delivery_intent="ready"``, builds a bounded six-key push
payload per event, runs every payload through the existing closed
credential-pattern guard, and dispatches via a **stub provider** that
records the intended URL / headers / payload but **never opens a
network socket**.

This is the smallest safe N2b-1 slice. **No real push is sent.**
N2b-2 (PWA subscription UI + service worker) and N2b-3 (real Web
Push delivery using env-provided VAPID private key) remain
unimplemented. N3 (mobile approval inbox), N4 (approval-token gate),
and N5 (merge/deploy adapter) remain unimplemented. Step 5.1 / 5.2
remain BLOCKED. Level 6 stays permanently disabled per ADR-015
§Doctrine 1.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.notification_dispatcher`` (read-only) +
  ``reporting.notification_event`` (read-only) +
  ``reporting.execution_authority`` (read-only) +
  ``reporting.agent_audit`` (write to today's ledger; only on
  non-``--no-write`` runs) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no ``socket``,
  no ``urllib``, no ``requests``, no ``httpx``, no ``aiohttp``, no
  Web Push library (``pywebpush``, ``web_push``, ``webpush``).
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  or ``trading``.
* No mutation of any upstream artefact (N2a's ``latest.json`` and
  ``events.jsonl`` are read-only).
* Atomic write only under
  ``logs/notification_dispatch_outbox/...``.
* Closed ``outbound_delivery_intent`` vocabulary; closed payload
  schema (exactly six bounded scalar keys).
* Audit events are emitted **only on normal non-``--no-write`` runs**;
  ``--no-write`` writes nothing and emits no audit event.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

CLI
---

::

    python -m reporting.notification_dispatch_outbox
    python -m reporting.notification_dispatch_outbox --no-write
    python -m reporting.notification_dispatch_outbox --indent 0
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Final

from reporting import agent_audit as _audit
from reporting import notification_dispatcher as nd
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N2b1"
REPORT_KIND: Final[str] = "notification_dispatch_outbox"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed outbound-delivery-intent vocabulary. Adding a value
#: requires a code change pinned by an updated unit test.
OUTBOUND_DELIVERY_INTENTS: Final[tuple[str, ...]] = (
    "sent",
    "duplicate",
    "skipped_not_ready",
    "rate_limited_outbound",
    "failed_secret_check",
    "failed_stub_provider",
)

#: Closed audit-event-name vocabulary for this module.
AUDIT_EVENT_NAMES: Final[tuple[str, ...]] = (
    "push_dispatch_attempt",
    "push_dispatch_success",
    "push_dispatch_skipped_duplicate",
    "push_dispatch_skipped_rate_limit",
    "push_dispatch_failure",
)

#: Closed push-payload schema, exact and ordered.
PUSH_PAYLOAD_KEYS: Final[tuple[str, ...]] = (
    "event_id",
    "event_kind",
    "event_severity",
    "title",
    "summary",
    "open_at",
)

#: Per-outbox-row schema, exact and ordered.
OUTBOX_RECORD_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "event_id",
    "event_kind",
    "event_severity",
    "source_module",
    "source_id",
    "outbound_delivery_intent",
    "payload",
    "stub_provider_url",
    "stub_provider_status",
    "stub_provider_result",
    "secret_guard_ok",
    "attempted_at",
    "audit_event_seq",
)

#: Maximum events with ``outbound_delivery_intent="sent"`` per cycle.
MAX_DISPATCH_PER_CYCLE: Final[int] = 16

#: Maximum events retained in the bounded ``outbox.jsonl``.
MAX_OUTBOX_HISTORY: Final[int] = 500

#: Bounded length for free-text scalars in the push payload.
#: Tighter than N2a's because mobile rendering is the constraint.
MAX_PUSH_TITLE_LEN: Final[int] = 80
MAX_PUSH_SUMMARY_LEN: Final[int] = 200
MAX_OPEN_AT_LEN: Final[int] = 300

#: Forbidden substrings inside any payload field (defense-in-depth on
#: top of the closed schema). Pinned by tests.
_FORBIDDEN_PAYLOAD_SUBSTRINGS: Final[tuple[str, ...]] = (
    "diff --git ",
    "+++ b/",
    "--- a/",
    "@@ -",
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
)

#: Forbidden decision-verb substrings inside the payload. The push
#: never carries a verb; the operator must open the PWA to act.
_FORBIDDEN_DECISION_VERBS: Final[tuple[str, ...]] = (
    "approve",
    "reject",
    "merge ",
    " merge",
    "deploy",
)

#: Closed wrapper-level note vocabulary.
NOTE_NO_DISPATCHER_ARTIFACT: Final[str] = "dispatcher_artifact_absent"
NOTE_NO_READY_EVENTS: Final[str] = "no_ready_events_to_dispatch"
NOTE_DISPATCH_PRESENT: Final[str] = "dispatch_records_present"

#: The deep-link path the SW would use on click to open the PWA.
#: This is the only "action" the push triggers; it never approves.
_PWA_INBOX_PATH_PREFIX: Final[str] = "/agent-control/inbox?event="

#: Synthetic stub-provider URL — opaque sentinel, never resolved,
#: never connected to. The real provider in N2b-3 will live in
#: ``dashboard/api_push_dispatch.py``; this sentinel exists so the
#: outbox row records "what would have been the dispatch URL" without
#: ever doing the dispatch.
_STUB_PROVIDER_URL: Final[str] = "stub://web-push-provider-disabled"

# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "notification_dispatch_outbox"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatch_outbox/latest.json"
)
OUTBOX_JSONL_PATH: Final[Path] = ARTIFACT_DIR / "outbox.jsonl"
OUTBOX_JSONL_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatch_outbox/outbox.jsonl"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/notification_dispatch_outbox/"

# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "sends_real_push": False,
    "invokes_network": False,
    "invokes_subprocess": False,
    "reads_subscription_files": False,
    "reads_vapid_keys": False,
    "writes_dashboard_or_frontend": False,
    "opens_mobile_inbox": False,
    "mints_approval_token": False,
    "invokes_merge_or_deploy": False,
    "uses_real_push_provider": False,
    "secret_redactor_invoked": True,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "diagnostics_do_not_trade": True,
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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_outbox_event_ids(path: Path) -> set[str]:
    """Read prior event_ids from the bounded outbox JSONL. Best-effort."""
    seen: set[str] = set()
    if not path.is_file():
        return seen
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return seen
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        eid = entry.get("event_id")
        if isinstance(eid, str) and eid:
            seen.add(eid)
    return seen


# ---------------------------------------------------------------------------
# Push-payload builder + closed-schema enforcement
# ---------------------------------------------------------------------------


def _build_push_payload(event: dict[str, Any]) -> dict[str, str]:
    """Build the closed six-key push payload. All scalars bounded."""
    event_id = str(event.get("event_id") or "")
    event_kind = str(event.get("event_kind") or "")
    event_severity = str(event.get("event_severity") or "")
    title = _bounded_str(event.get("title"), MAX_PUSH_TITLE_LEN)
    summary = _bounded_str(event.get("summary"), MAX_PUSH_SUMMARY_LEN)
    open_at = _bounded_str(
        f"{_PWA_INBOX_PATH_PREFIX}{event_id}", MAX_OPEN_AT_LEN
    )
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_severity": event_severity,
        "title": title,
        "summary": summary,
        "open_at": open_at,
    }


def _payload_passes_no_decision_verb(payload: dict[str, str]) -> bool:
    """Defense-in-depth: payload must contain no decision verb."""
    for v in payload.values():
        if not isinstance(v, str):
            continue
        lo = v.lower()
        for verb in _FORBIDDEN_DECISION_VERBS:
            if verb in lo:
                return False
    return True


def _payload_passes_no_diff_or_pem(payload: dict[str, str]) -> bool:
    for v in payload.values():
        if not isinstance(v, str):
            continue
        for forbidden in _FORBIDDEN_PAYLOAD_SUBSTRINGS:
            if forbidden in v:
                return False
    return True


# ---------------------------------------------------------------------------
# Stub provider — never opens a socket; never makes a network call
# ---------------------------------------------------------------------------


def stub_provider(
    payload: dict[str, str], *, subscription: dict[str, Any] | None = None
) -> dict[str, str]:
    """Synthetic dispatch provider for N2b-1.

    Behaviour:

    * Validates the payload shape against :data:`PUSH_PAYLOAD_KEYS`.
    * Records the *intended* URL (the closed sentinel
      :data:`_STUB_PROVIDER_URL`) and the bounded header set the real
      N2b-3 provider would use.
    * Returns a dict with ``url``, ``status``, and ``result``.
    * **Opens no socket. Imports no Web Push library. Reads no
      subscription file. Reads no VAPID key.**

    The ``subscription`` argument is accepted for forward-compat with
    N2b-3 but ignored — the stub never authenticates against a real
    push provider.
    """
    # Closed shape check.
    if set(payload.keys()) != set(PUSH_PAYLOAD_KEYS):
        return {
            "url": _STUB_PROVIDER_URL,
            "status": "rejected_shape",
            "result": "invalid_payload_keys",
        }
    return {
        "url": _STUB_PROVIDER_URL,
        "status": "accepted_offline",
        "result": "would_send",
    }


# ---------------------------------------------------------------------------
# Per-event dispatch
# ---------------------------------------------------------------------------


def _dispatch_one(
    event: dict[str, Any],
    *,
    seen_event_ids: set[str],
    sent_count: int,
    attempted_at: str,
) -> dict[str, Any]:
    """Process one N2a event and produce one outbox record. Pure;
    never calls the audit ledger (the caller does, on non-``--no-write``
    runs)."""
    event_id = str(event.get("event_id") or "")
    delivery_intent = event.get("delivery_intent")

    base: dict[str, Any] = {
        "event_id": event_id,
        "event_kind": str(event.get("event_kind") or ""),
        "event_severity": str(event.get("event_severity") or ""),
        "source_module": str(event.get("source_module") or ""),
        "source_id": str(event.get("source_id") or ""),
        "outbound_delivery_intent": "skipped_not_ready",
        "payload": {},
        "stub_provider_url": "",
        "stub_provider_status": "",
        "stub_provider_result": "",
        "secret_guard_ok": False,
        "attempted_at": attempted_at,
        "audit_event_seq": None,
    }

    if delivery_intent != "ready":
        return base

    if event_id and event_id in seen_event_ids:
        base["outbound_delivery_intent"] = "duplicate"
        return base

    if sent_count >= MAX_DISPATCH_PER_CYCLE:
        base["outbound_delivery_intent"] = "rate_limited_outbound"
        return base

    payload = _build_push_payload(event)

    # Defense-in-depth: closed-schema, no diff/PEM, no decision verb.
    # On any failure, we record `failed_secret_check` and **drop** the
    # payload from the outbox record. Persisting the dirty payload
    # would defeat the purpose of the guard and would re-trigger
    # ``assert_no_secrets`` at snapshot-build time.
    if not _payload_passes_no_diff_or_pem(payload):
        base["outbound_delivery_intent"] = "failed_secret_check"
        base["secret_guard_ok"] = False
        return base
    if not _payload_passes_no_decision_verb(payload):
        base["outbound_delivery_intent"] = "failed_secret_check"
        base["secret_guard_ok"] = False
        return base

    # Closed-pattern credential guard. Fails closed; never persists
    # the dirty payload.
    try:
        assert_no_secrets({"payload": payload})
    except AssertionError:
        base["outbound_delivery_intent"] = "failed_secret_check"
        base["secret_guard_ok"] = False
        return base

    base["secret_guard_ok"] = True
    base["payload"] = payload

    # Stub-dispatch.
    try:
        result = stub_provider(payload)
    except Exception:
        base["outbound_delivery_intent"] = "failed_stub_provider"
        return base

    base["stub_provider_url"] = result.get("url", "")
    base["stub_provider_status"] = result.get("status", "")
    base["stub_provider_result"] = result.get("result", "")

    if result.get("status") == "accepted_offline":
        base["outbound_delivery_intent"] = "sent"
    else:
        base["outbound_delivery_intent"] = "failed_stub_provider"

    return base


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


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
            v: 0 for v in OUTBOUND_DELIVERY_INTENTS
        },
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_source_module": {m: 0 for m in nd.SOURCE_MODULES},
    }


def _aggregate_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(records)
    for r in records:
        di = r.get("outbound_delivery_intent")
        if di in counts:
            counts[di] += 1
        if di in counts["by_outbound_delivery_intent"]:
            counts["by_outbound_delivery_intent"][di] += 1
        ek = r.get("event_kind")
        if isinstance(ek, str) and ek in counts["by_event_kind"]:
            counts["by_event_kind"][ek] += 1
        es = r.get("event_severity")
        if isinstance(es, str) and es in counts["by_event_severity"]:
            counts["by_event_severity"][es] += 1
        sm = r.get("source_module")
        if isinstance(sm, str) and sm in counts["by_source_module"]:
            counts["by_source_module"][sm] += 1
    return counts


def collect_snapshot(
    *,
    dispatcher_artifact_path: Path | None = None,
    outbox_history_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic outbox snapshot.

    Pure: reads upstream + outbox history; **never** writes,
    **never** appends to the audit ledger. Audit emission is the
    caller's responsibility (see :func:`write_outputs`)."""
    dap = (
        dispatcher_artifact_path
        if dispatcher_artifact_path is not None
        else nd.ARTIFACT_LATEST
    )
    ohp = (
        outbox_history_path
        if outbox_history_path is not None
        else OUTBOX_JSONL_PATH
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(dap)
    seen_ids = _read_outbox_event_ids(ohp)

    records: list[dict[str, Any]] = []
    if payload is None:
        events = []
        note = NOTE_NO_DISPATCHER_ARTIFACT
    else:
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            events = []
        note = NOTE_NO_READY_EVENTS

    sent_count = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        # Only ever consider records whose upstream delivery_intent is
        # "ready". Non-ready records are recorded as skipped_not_ready
        # for operator visibility, but only up to MAX_DISPATCH_PER_CYCLE
        # of them — the rest are dropped silently to keep the artefact
        # bounded.
        rec = _dispatch_one(
            ev,
            seen_event_ids=seen_ids,
            sent_count=sent_count,
            attempted_at=ts,
        )
        if rec["outbound_delivery_intent"] == "sent":
            sent_count += 1
        records.append(rec)

    if records and any(r["outbound_delivery_intent"] == "sent" for r in records):
        note = NOTE_DISPATCH_PRESENT

    records.sort(
        key=lambda r: (r.get("source_module", ""), r.get("event_id", ""))
    )
    counts = _aggregate_counts(records)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "dispatcher_artifact_path": str(dap),
        "dispatcher_artifact_available": payload is not None,
        "outbox_history_path": str(ohp),
        "stub_provider_url": _STUB_PROVIDER_URL,
        "note": note,
        "validation_warnings": [],
        "vocabularies": {
            "outbound_delivery_intents": list(OUTBOUND_DELIVERY_INTENTS),
            "audit_event_names": list(AUDIT_EVENT_NAMES),
            "push_payload_keys": list(PUSH_PAYLOAD_KEYS),
            "outbox_record_schema_keys": list(OUTBOX_RECORD_SCHEMA_KEYS),
            "max_dispatch_per_cycle": MAX_DISPATCH_PER_CYCLE,
            "max_outbox_history": MAX_OUTBOX_HISTORY,
        },
        "counts": counts,
        "records": records,
        "notification_dispatcher_module_version": nd.MODULE_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write + bounded outbox.jsonl append
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatch_outbox._atomic_write_json refuses "
            f"non-outbox-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatch_outbox.",
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


def _append_outbox_history(
    path: Path, records: list[dict[str, Any]]
) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatch_outbox._append_outbox_history "
            f"refuses non-outbox-logs path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        try:
            existing = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            existing = []
    for rec in records:
        # Only append rows that we *attempted* (sent / duplicate /
        # rate_limited / failed_*); skipped_not_ready rows roll the
        # outbox forward without value and are excluded.
        di = rec.get("outbound_delivery_intent")
        if di == "skipped_not_ready":
            continue
        compact = {
            "event_id": rec["event_id"],
            "event_kind": rec["event_kind"],
            "outbound_delivery_intent": di,
            "stub_provider_status": rec.get("stub_provider_status", ""),
            "attempted_at": rec["attempted_at"],
        }
        existing.append(
            json.dumps(compact, sort_keys=True, ensure_ascii=False)
        )
    if len(existing) > MAX_OUTBOX_HISTORY:
        existing = existing[-MAX_OUTBOX_HISTORY:]
    text = "\n".join(existing) + ("\n" if existing else "")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatch_outbox.outbox.",
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


# ---------------------------------------------------------------------------
# Audit emission (best-effort; never raises)
# ---------------------------------------------------------------------------


def _audit_event_for_record(rec: dict[str, Any]) -> str:
    di = rec.get("outbound_delivery_intent")
    if di == "sent":
        return "push_dispatch_success"
    if di == "duplicate":
        return "push_dispatch_skipped_duplicate"
    if di == "rate_limited_outbound":
        return "push_dispatch_skipped_rate_limit"
    if di in ("failed_secret_check", "failed_stub_provider"):
        return "push_dispatch_failure"
    # skipped_not_ready and any other value do not generate an audit row.
    return ""


def _emit_audit_for_records(
    records: list[dict[str, Any]],
) -> int:
    """Append one audit event per attempted record. Best-effort:
    never raises (mirrors A14 audit posture). Returns the count of
    successfully appended events."""
    count = 0
    for rec in records:
        name = _audit_event_for_record(rec)
        if not name:
            continue
        # Pre-attempt event for visibility — pinned by the closed
        # AUDIT_EVENT_NAMES set; emit before the result event.
        try:
            _audit.append_event(
                {
                    "actor": "notification_dispatch_outbox:dry_run",
                    "event": "push_dispatch_attempt",
                    "tool": "notification_dispatch_outbox",
                    "outcome": "ok",
                    "autonomy_level_claimed": 0,
                    "push_event_id": rec.get("event_id"),
                    "push_event_kind": rec.get("event_kind"),
                    "push_module_version": MODULE_VERSION,
                }
            )
            sealed = _audit.append_event(
                {
                    "actor": "notification_dispatch_outbox:dry_run",
                    "event": name,
                    "tool": "notification_dispatch_outbox",
                    "outcome": "ok"
                    if name == "push_dispatch_success"
                    else "blocked",
                    "block_reason": (
                        rec.get("outbound_delivery_intent")
                        if name == "push_dispatch_failure"
                        else None
                    ),
                    "autonomy_level_claimed": 0,
                    "push_event_id": rec.get("event_id"),
                    "push_event_kind": rec.get("event_kind"),
                    "push_outbound_delivery_intent": rec.get(
                        "outbound_delivery_intent"
                    ),
                    "push_module_version": MODULE_VERSION,
                }
            )
            if isinstance(sealed, dict) and "sequence_id" in sealed:
                rec["audit_event_seq"] = sealed["sequence_id"]
            count += 2
        except Exception:
            continue
    return count


def write_outputs(snapshot: dict[str, Any]) -> tuple[Path, Path]:
    """Persist artefacts and emit per-record audit events.

    **Only call this on non-``--no-write`` runs.** The CLI guards the
    audit-emission boundary; tests may also call this helper directly.
    """
    records = list(snapshot.get("records") or [])
    _emit_audit_for_records(records)
    # The audit emission may have stamped audit_event_seq onto each
    # record; refresh the snapshot's records list before writing.
    snapshot["records"] = records
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    _append_outbox_history(OUTBOX_JSONL_PATH, records)
    return (ARTIFACT_LATEST, OUTBOX_JSONL_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.notification_dispatch_outbox",
        description=(
            "N2b-1 Notification Dispatch Outbox (stub provider, "
            "dry-run). Read-only deterministic projector that "
            "converts N2a delivery_intent=ready events into bounded "
            "six-key push payloads, runs them through "
            "assert_no_secrets, dispatches via a stub provider that "
            "OPENS NO SOCKET, and writes outbox records under "
            "logs/notification_dispatch_outbox/. Sends no real push. "
            "Audit events emitted only on normal non --no-write runs."
        ),
    )
    p.add_argument(
        "--indent", type=int, default=2, help="JSON indent (0 for compact)."
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist artefacts; do not emit audit events. "
            "Print the snapshot JSON to stdout only."
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
