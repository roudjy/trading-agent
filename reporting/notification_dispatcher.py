"""N2a — Artifact-only Notification Dispatcher.

Pure, deterministic, stdlib-only notification *dispatcher*. Reads
existing ADE artefacts (A8 work queue, A14 Step 5.0 plan, A16a intake
promotion, Step 5.0.1 roadmap intake) and produces notification-ready
event records under ``logs/notification_dispatcher/``.

This is the smallest safe N2a slice. **No real push is sent.** No
network call, no socket, no Web Push library, no subscription file,
no VAPID key, no dashboard or frontend code path. The dispatcher
*decides nothing*; it computes which event would be delivered and
writes the result.

N3 (mobile approval inbox), N4 (approval-token gate), and N5
(merge/deploy adapter) remain unimplemented. N2b (real Web Push
delivery) remains unimplemented and is gated on a separate explicit
operator go-signal.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.notification_event`` (read-only) +
  ``reporting.execution_authority`` (read-only) +
  ``reporting.development_intake_promotion`` (read-only) +
  ``reporting.development_roadmap_intake`` (read-only) +
  ``reporting.development_step5_loop`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no ``socket``,
  no ``urllib``, no ``requests``, no ``httpx``, no ``aiohttp``, no
  Web Push library.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  or ``trading``.
* No mutation of any upstream artefact.
* Atomic write only under
  ``logs/notification_dispatcher/...``.
* Closed ``delivery_intent`` vocabulary; the routing-table is N1's.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``. Step 5.1 / 5.2 stay
  BLOCKED. Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

CLI
---

::

    python -m reporting.notification_dispatcher
    python -m reporting.notification_dispatcher --no-write
    python -m reporting.notification_dispatcher --indent 0
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
from typing import Any, Final

from reporting import development_intake_promotion as dip
from reporting import development_roadmap_intake as dri
from reporting import development_step5_loop as dsl
from reporting import execution_authority as ea
from reporting import notification_event as ne
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N2a"
REPORT_KIND: Final[str] = "notification_dispatcher"

# ---------------------------------------------------------------------------
# Step 5 invariants (re-asserted on every artefact)
# ---------------------------------------------------------------------------

#: Mirrors the ``development_step5_loop`` constant so the artefact is
#: self-attesting.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Hard-pinned literal: Step 5 implementation remains BLOCKED.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed delivery-intent vocabulary. Adding a value requires a code
#: change pinned by an updated unit test.
DELIVERY_INTENTS: Final[tuple[str, ...]] = (
    "ready",
    "suppressed",
    "suppressed_cooldown",
    "duplicate_within_window",
    "rate_limited",
)

#: Closed source-module vocabulary the dispatcher recognises.
SOURCE_MODULES: Final[tuple[str, ...]] = (
    "development_intake_promotion",
    "development_step5_loop",
    "development_roadmap_intake",
)

#: Maximum events with ``delivery_intent="ready"`` per cycle. Excess
#: events are flagged ``rate_limited`` and roll into the next cycle's
#: ``events.jsonl`` for re-evaluation.
MAX_DISPATCH_PER_CYCLE: Final[int] = 16

#: Maximum events retained in the bounded ``events.jsonl`` history.
MAX_EVENTS_HISTORY: Final[int] = 500

#: Per-event-kind cooldown in seconds. Default-deny: any kind not
#: listed gets a generous 600s cooldown to avoid noise.
COOLDOWN_SECONDS_PER_EVENT_KIND: Final[dict[str, int]] = {
    "queue_item_proposed": 1800,
    "queue_item_blocked": 600,
    "queue_item_human_needed": 0,
    "delegation_emitted": 1800,
    "delegation_blocked": 600,
    "bugfix_candidate_proposed": 1800,
    "bugfix_candidate_blocked": 600,
    "intake_candidate_proposed": 1800,
    "intake_candidate_eligible": 600,
    "intake_candidate_blocked": 600,
    "step5_cycle_planned": 1800,
    "step5_cycle_halted": 0,
    "step5_cycle_needs_human": 0,
    "release_gate_pass": 1800,
    "release_gate_fail": 0,
    "release_gate_needs_human": 0,
    "operational_digest_emitted": 1800,
    "e2e_proof_pass": 1800,
    "e2e_proof_fail": 0,
    "pr_lifecycle_event": 600,
    "pr_merge_approval_required": 0,
    "pr_merge_approved": 600,
    "pr_merge_rejected": 600,
    "pr_merge_executed": 600,
    "deploy_approval_required": 0,
    "deploy_approved": 600,
    "deploy_rejected": 600,
    "deploy_executed": 600,
    "governance_violation_detected": 0,
    "secret_or_pii_redaction_event": 0,
    "audit_chain_anomaly": 0,
    "unknown_state": 600,
}

#: Severities that are treated as "delivery-suppressed" — the
#: dispatcher records the event but flags it so a future N2b push
#: surface never delivers it.
_SUPPRESSED_SEVERITIES: Final[frozenset[str]] = frozenset({"silent", "digest"})

#: 24-hour sliding-window for duplicate event_id dedupe.
DEDUPE_WINDOW_SECONDS: Final[int] = 24 * 60 * 60

#: Closed wrapper-level note vocabulary.
NOTE_NO_SOURCES: Final[str] = "no_upstream_sources_available"
NOTE_NO_EVENTS: Final[str] = "no_events_to_dispatch"
NOTE_EVENTS_PRESENT: Final[str] = "events_present"

#: Per-event schema, exact and ordered.
EVENT_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "event_id",
    "event_kind",
    "event_severity",
    "delivery_intent",
    "source_module",
    "source_artifact_path",
    "source_id",
    "title",
    "summary",
    "risk_class",
    "execution_authority_decision",
    "acceptance_criteria",
    "target_path",
    "evidence_hash",
    "created_at",
    "notes",
)

#: Bounded length for free-text scalars.
MAX_TITLE_LEN: Final[int] = 200
MAX_SUMMARY_LEN: Final[int] = 480
MAX_NOTES_LEN: Final[int] = 1000
MAX_AC_ITEMS: Final[int] = 16
MAX_AC_LINE_LEN: Final[int] = 200
MAX_TARGET_PATH_LEN: Final[int] = 300

# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "notification_dispatcher"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatcher/latest.json"
)
EVENTS_JSONL_PATH: Final[Path] = ARTIFACT_DIR / "events.jsonl"
EVENTS_JSONL_RELATIVE_PATH: Final[str] = (
    "logs/notification_dispatcher/events.jsonl"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/notification_dispatcher/"

# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "sends_real_push": False,
    "opens_mobile_inbox": False,
    "mints_approval_token": False,
    "invokes_network": False,
    "invokes_subprocess": False,
    "mutates_upstream_artifacts": False,
    "reads_subscription_files": False,
    "reads_vapid_keys": False,
    "writes_dashboard_or_frontend": False,
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


def _bounded_str_list(
    value: Any, max_items: int, max_line_len: int
) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value[:max_items]:
        if isinstance(v, str):
            out.append(_bounded_str(v, max_line_len))
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _parse_iso_utc(s: str | None) -> _dt.datetime | None:
    """Best-effort parse of an RFC3339 UTC string. Returns None on
    failure; never raises on malformed input."""
    if not isinstance(s, str) or not s:
        return None
    try:
        norm = s.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.UTC)
        return dt
    except ValueError:
        return None


def _seconds_between(later: str | None, earlier: str | None) -> float | None:
    a = _parse_iso_utc(later)
    b = _parse_iso_utc(earlier)
    if a is None or b is None:
        return None
    return (a - b).total_seconds()


def _evidence_hash(parts: dict[str, Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_id(event_kind: str, source_module: str, source_id: str, content_hash: str) -> str:
    raw = f"{event_kind}|{source_module}|{source_id}|{content_hash}".encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Source projectors — pure: dict in, list[dict] out
# ---------------------------------------------------------------------------


def _project_intake_promotion_rows(
    payload: dict[str, Any] | None,
    *,
    artifact_path: str,
    created_at: str,
) -> list[dict[str, Any]]:
    """Map A16a promotion-intent rows to event records."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        decision_state = row.get("decision_state")
        if decision_state == "eligible":
            event_kind = "intake_candidate_eligible"
        elif decision_state in ("blocked", "human_needed"):
            event_kind = "intake_candidate_blocked"
        elif decision_state == "already_promoted":
            event_kind = "intake_candidate_eligible"
        else:
            continue

        source_id = str(row.get("candidate_id") or "")
        if not source_id:
            continue

        risk_class = row.get("risk_level")
        reclassified = row.get("reclassified_execution_authority_decision")
        severity = ne.route_for(
            event_kind,
            risk_class=risk_class if isinstance(risk_class, str) else None,
            execution_authority_decision=(
                reclassified if isinstance(reclassified, str) else None
            ),
        )

        title = _bounded_str(row.get("title"), MAX_TITLE_LEN)
        summary_raw = (
            f"decision_state={decision_state}; "
            f"risk={risk_class}; "
            f"target={row.get('target_path') or ''}"
        )
        summary = _bounded_str(summary_raw, MAX_SUMMARY_LEN)
        ac = _bounded_str_list(
            row.get("acceptance_criteria"), MAX_AC_ITEMS, MAX_AC_LINE_LEN
        )
        target_path = _bounded_str(row.get("target_path"), MAX_TARGET_PATH_LEN)

        content_parts = {
            "decision_state": decision_state,
            "risk_class": risk_class,
            "reclassified_execution_authority_decision": reclassified,
            "target_path": target_path,
            "title": title,
            "evidence_hash_upstream": row.get("evidence_hash"),
        }
        evidence_hash = _evidence_hash(content_parts)
        eid = _event_id(
            event_kind,
            "development_intake_promotion",
            source_id,
            evidence_hash,
        )

        out.append(
            {
                "event_id": eid,
                "event_kind": event_kind,
                "event_severity": severity,
                "delivery_intent": "ready",  # gates will overwrite later
                "source_module": "development_intake_promotion",
                "source_artifact_path": artifact_path,
                "source_id": source_id,
                "title": title,
                "summary": summary,
                "risk_class": risk_class if isinstance(risk_class, str) else "",
                "execution_authority_decision": (
                    reclassified if isinstance(reclassified, str) else ""
                ),
                "acceptance_criteria": ac,
                "target_path": target_path,
                "evidence_hash": evidence_hash,
                "created_at": created_at,
                "notes": "",
            }
        )
    return out


def _project_step5_loop_row(
    payload: dict[str, Any] | None,
    *,
    artifact_path: str,
    created_at: str,
) -> list[dict[str, Any]]:
    """Map the latest Step 5.0 loop snapshot to a single event."""
    if not isinstance(payload, dict):
        return []
    plan = payload.get("current_plan")
    if not isinstance(plan, dict):
        return []
    outcome = plan.get("outcome")
    halt_reason = plan.get("halt_reason")
    decision = plan.get("execution_authority_decision")

    if outcome == "plan_emitted":
        event_kind = "step5_cycle_planned"
    elif outcome in ("halt_needs_human",):
        event_kind = "step5_cycle_needs_human"
    elif outcome in (
        "halt_permanently_denied",
        "halt_out_of_allowlist",
    ):
        event_kind = "step5_cycle_halted"
    elif outcome == "no_op_no_eligible_item":
        # Don't emit a notification for empty cycles — pure noise.
        return []
    else:
        return []

    cycle_id = str(plan.get("cycle_id") or "")
    if not cycle_id:
        return []

    severity = ne.route_for(
        event_kind,
        risk_class=None,
        execution_authority_decision=(
            decision if isinstance(decision, str) else None
        ),
    )

    title = _bounded_str(
        f"Step 5.0 {outcome}: {plan.get('source_kind') or ''}/{plan.get('source_id') or ''}",
        MAX_TITLE_LEN,
    )
    summary = _bounded_str(
        f"halt_reason={halt_reason}; decision={decision}",
        MAX_SUMMARY_LEN,
    )

    content_parts = {
        "outcome": outcome,
        "halt_reason": halt_reason,
        "execution_authority_decision": decision,
        "source_kind": plan.get("source_kind"),
        "source_id": plan.get("source_id"),
    }
    evidence_hash = _evidence_hash(content_parts)
    eid = _event_id(
        event_kind, "development_step5_loop", cycle_id, evidence_hash
    )

    return [
        {
            "event_id": eid,
            "event_kind": event_kind,
            "event_severity": severity,
            "delivery_intent": "ready",
            "source_module": "development_step5_loop",
            "source_artifact_path": artifact_path,
            "source_id": cycle_id,
            "title": title,
            "summary": summary,
            "risk_class": "",
            "execution_authority_decision": (
                decision if isinstance(decision, str) else ""
            ),
            "acceptance_criteria": [],
            "target_path": "",
            "evidence_hash": evidence_hash,
            "created_at": created_at,
            "notes": "",
        }
    ]


def _project_roadmap_intake_candidates(
    payload: dict[str, Any] | None,
    *,
    artifact_path: str,
    created_at: str,
) -> list[dict[str, Any]]:
    """Map Step 5.0.1 roadmap intake candidates (proposed-only) to
    intake_candidate_proposed events. Eligible/blocked candidates are
    handled by the A16a projector above; this projector emits the
    discovery-stage event so the operator can see new candidates as
    they show up."""
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []

    out: list[dict[str, Any]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        # Only emit "proposed" — eligible/blocked are owned by A16a.
        # If the upstream intake_status is "eligible", the A16a
        # projector emits the actionable event; this projector emits
        # the silent discovery event.
        intake_status = cand.get("intake_status")
        if intake_status not in ("proposed", "eligible"):
            continue

        event_kind = "intake_candidate_proposed"
        candidate_id = str(cand.get("candidate_id") or "")
        if not candidate_id:
            continue

        risk_class = cand.get("risk_level")
        decision = cand.get("execution_authority_decision")

        severity = ne.route_for(
            event_kind,
            risk_class=risk_class if isinstance(risk_class, str) else None,
            execution_authority_decision=(
                decision if isinstance(decision, str) else None
            ),
        )

        title = _bounded_str(cand.get("title"), MAX_TITLE_LEN)
        summary_raw = (
            f"intake_status={intake_status}; "
            f"risk={risk_class}; "
            f"target={cand.get('target_path') or ''}"
        )
        summary = _bounded_str(summary_raw, MAX_SUMMARY_LEN)
        ac = _bounded_str_list(
            cand.get("acceptance_criteria"), MAX_AC_ITEMS, MAX_AC_LINE_LEN
        )
        target_path = _bounded_str(
            cand.get("target_path"), MAX_TARGET_PATH_LEN
        )

        content_parts = {
            "intake_status": intake_status,
            "risk_class": risk_class,
            "execution_authority_decision": decision,
            "target_path": target_path,
            "title": title,
        }
        evidence_hash = _evidence_hash(content_parts)
        eid = _event_id(
            event_kind,
            "development_roadmap_intake",
            candidate_id,
            evidence_hash,
        )

        out.append(
            {
                "event_id": eid,
                "event_kind": event_kind,
                "event_severity": severity,
                "delivery_intent": "ready",
                "source_module": "development_roadmap_intake",
                "source_artifact_path": artifact_path,
                "source_id": candidate_id,
                "title": title,
                "summary": summary,
                "risk_class": risk_class if isinstance(risk_class, str) else "",
                "execution_authority_decision": (
                    decision if isinstance(decision, str) else ""
                ),
                "acceptance_criteria": ac,
                "target_path": target_path,
                "evidence_hash": evidence_hash,
                "created_at": created_at,
                "notes": "",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Delivery-intent gates
# ---------------------------------------------------------------------------


def _read_history(path: Path) -> list[dict[str, Any]]:
    """Read prior events from the bounded history JSONL. Best-effort;
    malformed lines skipped."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _apply_delivery_gates(
    events: list[dict[str, Any]],
    *,
    history: list[dict[str, Any]],
    now_utc: str,
) -> list[dict[str, Any]]:
    """Apply the closed delivery-intent rules in priority order:

    1. severity in {silent, digest} → ``suppressed``
    2. event_id seen in 24h sliding window → ``duplicate_within_window``
    3. event_kind within cooldown → ``suppressed_cooldown``
    4. excess over MAX_DISPATCH_PER_CYCLE → ``rate_limited``
    5. otherwise → ``ready``

    Returns events with mutated ``delivery_intent`` values; never
    drops an event from the output list (gating only re-labels).
    """
    seen_ids: dict[str, str] = {}  # event_id -> created_at
    last_seen_per_kind: dict[str, str] = {}
    for h in history:
        eid = h.get("event_id")
        ek = h.get("event_kind")
        ts = h.get("created_at")
        if isinstance(eid, str) and isinstance(ts, str):
            seen_ids[eid] = ts
        if isinstance(ek, str) and isinstance(ts, str):
            prev = last_seen_per_kind.get(ek)
            if prev is None or ts > prev:
                last_seen_per_kind[ek] = ts

    ready_count = 0
    out: list[dict[str, Any]] = []
    for ev in events:
        new_ev = dict(ev)
        sev = new_ev.get("event_severity")
        kind = new_ev.get("event_kind")
        eid = new_ev.get("event_id")

        # 1. Severity-default suppression.
        if sev in _SUPPRESSED_SEVERITIES:
            new_ev["delivery_intent"] = "suppressed"
            out.append(new_ev)
            continue

        # 2. event_id dedupe within sliding window.
        if isinstance(eid, str) and eid in seen_ids:
            seen_ts = seen_ids[eid]
            seconds = _seconds_between(now_utc, seen_ts)
            if seconds is None or seconds <= DEDUPE_WINDOW_SECONDS:
                new_ev["delivery_intent"] = "duplicate_within_window"
                out.append(new_ev)
                continue

        # 3. Cooldown per event_kind.
        if isinstance(kind, str):
            cooldown = COOLDOWN_SECONDS_PER_EVENT_KIND.get(kind, 600)
            if cooldown > 0:
                last_ts = last_seen_per_kind.get(kind)
                if last_ts is not None:
                    seconds = _seconds_between(now_utc, last_ts)
                    if seconds is not None and seconds < cooldown:
                        new_ev["delivery_intent"] = "suppressed_cooldown"
                        out.append(new_ev)
                        continue

        # 4. Rate limit.
        if ready_count >= MAX_DISPATCH_PER_CYCLE:
            new_ev["delivery_intent"] = "rate_limited"
            out.append(new_ev)
            continue

        # 5. Default — ready.
        new_ev["delivery_intent"] = "ready"
        ready_count += 1
        out.append(new_ev)

    return out


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "ready": 0,
        "suppressed": 0,
        "suppressed_cooldown": 0,
        "duplicate_within_window": 0,
        "rate_limited": 0,
        "by_event_kind": {k: 0 for k in ne.EVENT_KINDS},
        "by_event_severity": {s: 0 for s in ne.EVENT_SEVERITIES},
        "by_delivery_intent": {d: 0 for d in DELIVERY_INTENTS},
        "by_source_module": {m: 0 for m in SOURCE_MODULES},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }


def _aggregate_counts(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(events)
    for ev in events:
        di = ev.get("delivery_intent")
        if di in counts:
            counts[di] += 1
        if di in counts["by_delivery_intent"]:
            counts["by_delivery_intent"][di] += 1
        kind = ev.get("event_kind")
        if isinstance(kind, str) and kind in counts["by_event_kind"]:
            counts["by_event_kind"][kind] += 1
        sev = ev.get("event_severity")
        if isinstance(sev, str) and sev in counts["by_event_severity"]:
            counts["by_event_severity"][sev] += 1
        sm = ev.get("source_module")
        if isinstance(sm, str) and sm in counts["by_source_module"]:
            counts["by_source_module"][sm] += 1
        d = ev.get("execution_authority_decision")
        if d in counts["by_execution_authority_decision"]:
            counts["by_execution_authority_decision"][d] += 1
    return counts


def collect_snapshot(
    *,
    intake_promotion_path: Path | None = None,
    step5_loop_path: Path | None = None,
    roadmap_intake_path: Path | None = None,
    events_history_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic notification-dispatcher snapshot.

    All path arguments are read-only. ``events_history_path`` is read
    for sliding-window dedupe and cooldown computation; not mutated
    here.
    """
    ip = (
        intake_promotion_path
        if intake_promotion_path is not None
        else dip.ARTIFACT_LATEST
    )
    sp = (
        step5_loop_path
        if step5_loop_path is not None
        else dsl.ARTIFACT_LATEST
    )
    rp = (
        roadmap_intake_path
        if roadmap_intake_path is not None
        else dri.ARTIFACT_LATEST
    )
    eh = (
        events_history_path
        if events_history_path is not None
        else EVENTS_JSONL_PATH
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    intake_payload = _read_json(ip)
    step5_payload = _read_json(sp)
    roadmap_payload = _read_json(rp)

    sources_read: list[dict[str, Any]] = [
        {
            "source_module": "development_intake_promotion",
            "path": str(ip),
            "available": intake_payload is not None,
        },
        {
            "source_module": "development_step5_loop",
            "path": str(sp),
            "available": step5_payload is not None,
        },
        {
            "source_module": "development_roadmap_intake",
            "path": str(rp),
            "available": roadmap_payload is not None,
        },
    ]

    events: list[dict[str, Any]] = []
    events.extend(
        _project_intake_promotion_rows(
            intake_payload,
            artifact_path=str(ip),
            created_at=ts,
        )
    )
    events.extend(
        _project_step5_loop_row(
            step5_payload, artifact_path=str(sp), created_at=ts
        )
    )
    events.extend(
        _project_roadmap_intake_candidates(
            roadmap_payload, artifact_path=str(rp), created_at=ts
        )
    )

    # Stable ordering: source_module, event_kind, event_id.
    events.sort(
        key=lambda e: (
            e.get("source_module", ""),
            e.get("event_kind", ""),
            e.get("event_id", ""),
        )
    )

    history = _read_history(eh)
    events = _apply_delivery_gates(events, history=history, now_utc=ts)

    counts = _aggregate_counts(events)

    if all(s["available"] is False for s in sources_read):
        note = NOTE_NO_SOURCES
    elif not events:
        note = NOTE_NO_EVENTS
    else:
        note = NOTE_EVENTS_PRESENT

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "sources_read": sources_read,
        "events_history_path": str(eh),
        "note": note,
        "validation_warnings": [],
        "vocabularies": {
            "delivery_intents": list(DELIVERY_INTENTS),
            "source_modules": list(SOURCE_MODULES),
            "notification_event_kinds": list(ne.EVENT_KINDS),
            "notification_event_severities": list(ne.EVENT_SEVERITIES),
            "max_dispatch_per_cycle": MAX_DISPATCH_PER_CYCLE,
            "max_events_history": MAX_EVENTS_HISTORY,
            "dedupe_window_seconds": DEDUPE_WINDOW_SECONDS,
        },
        "cooldown_seconds_per_event_kind": dict(
            COOLDOWN_SECONDS_PER_EVENT_KIND
        ),
        "counts": counts,
        "events": events,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "intake_promotion_module_version": dip.MODULE_VERSION,
        "step5_module_version": dsl.MODULE_VERSION,
        "roadmap_intake_module_version": dri.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }

    # Defense-in-depth: every emitted snapshot is run through the
    # closed credential-pattern guard. The dispatcher emits no
    # secret-shaped strings by construction, but the guard is the
    # safety net per the canonical rule.
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write + bounded events.jsonl append
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatcher._atomic_write_json refuses "
            f"non-dispatcher-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatcher.",
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


def _append_events_history(
    path: Path, events: list[dict[str, Any]]
) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "notification_dispatcher._append_events_history refuses "
            f"non-dispatcher-logs path: {path}"
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
    for ev in events:
        compact = {
            "event_id": ev["event_id"],
            "event_kind": ev["event_kind"],
            "event_severity": ev["event_severity"],
            "delivery_intent": ev["delivery_intent"],
            "source_module": ev["source_module"],
            "source_id": ev["source_id"],
            "created_at": ev["created_at"],
        }
        existing.append(json.dumps(compact, sort_keys=True, ensure_ascii=False))
    if len(existing) > MAX_EVENTS_HISTORY:
        existing = existing[-MAX_EVENTS_HISTORY:]
    text = "\n".join(existing) + ("\n" if existing else "")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".notification_dispatcher.events.",
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


def write_outputs(snapshot: dict[str, Any]) -> tuple[Path, Path]:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    _append_events_history(EVENTS_JSONL_PATH, snapshot.get("events") or [])
    return (ARTIFACT_LATEST, EVENTS_JSONL_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.notification_dispatcher",
        description=(
            "N2a Artifact-only Notification Dispatcher. Read-only "
            "deterministic projector that converts ADE upstream "
            "artefacts into notification-ready event records under "
            "logs/notification_dispatcher/. Sends no real push. "
            "Decides nothing; emits no notifications externally. "
            "Step 5 implementation remains BLOCKED."
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
            "logs/notification_dispatcher/latest.json or events.jsonl "
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
