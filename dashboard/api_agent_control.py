"""Read-only Flask routes for the v3.15.15.18 mobile-first Agent
Control PWA.

This module exposes five GET-only endpoints under the
``/api/agent-control/`` prefix. It is the *only* surface the mobile
PWA shell needs to render its read-only cards.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* GET only — no POST / PUT / PATCH / DELETE / OPTIONS handlers
  registered.
* Never executes a CLI subprocess. Reads pre-computed JSON / module
  output only.
* Never invokes ``gh`` (or any other mutating tool).
* Never touches ``git``.
* Never reads ``config/config.yaml``, ``state/*.secret``, ``.env``,
  or any other path on the no-touch read-deny list.
* Missing / malformed / unreadable artifacts → ``{"status":
  "not_available", "reason": ...}``. Nothing is ever surfaced as
  ``ok`` by default; ``ok`` requires positive evidence.
* Every response payload is run through ``assert_no_secrets`` from
  ``reporting.agent_audit_summary`` before it leaves the server, so
  the surface remains free of accidental credential strings.
* The ``/notifications`` endpoint is a placeholder: it returns an
  empty list with ``mode: "placeholder"``. No browser push, no
  external service.

Wiring
------

The module follows the existing ``register_*_routes(app)`` pattern.
To activate the surface, ``dashboard/dashboard.py`` needs one line::

    from dashboard.api_agent_control import register_agent_control_routes
    register_agent_control_routes(app)

That edit is intentionally NOT shipped here — ``dashboard.py`` is on
the no-touch list and a separate operator-led PR wires it up.
Until that PR lands, the PWA frontend treats every endpoint as
``not_available`` and renders empty/placeholder states.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
LOGS_DIR: Path = REPO_ROOT / "logs"

# Cached locations of the JSON artifacts the cards consume. Each is
# produced by a separate reporting module — none of those imports
# happens here, so this surface stays light and side-effect free.
WORKLOOP_LATEST: Path = LOGS_DIR / "autonomous_workloop" / "latest.json"
PR_LIFECYCLE_LATEST: Path = LOGS_DIR / "github_pr_lifecycle" / "latest.json"
# v3.15.16.9b — loop closure visibility. Three additional artifacts
# read by ``_loop_closure_summary()`` to surface whether the
# v3.15.16.8 detection -> v3.15.16.9 templating -> operator-PR ->
# loop-closure cycle has completed. Read-only.
HUMAN_NEEDED_LATEST: Path = LOGS_DIR / "human_needed" / "latest.json"
GOVERNANCE_BOOTSTRAP_LATEST: Path = (
    LOGS_DIR / "governance_bootstrap" / "latest.json"
)
APPROVAL_INBOX_LATEST: Path = LOGS_DIR / "approval_inbox" / "latest.json"
# Consistency window: when all three counts are zero, the three
# generated_at_utc values must lie within this window of each
# other to qualify as ``resolved``. Wider spread -> ``stale``
# (the typed scheduler runs sequentially; a 10-min spread is the
# conservative upper bound on a single tick's wall-clock cost).
LOOP_CLOSURE_CONSISTENCY_WINDOW_SECONDS: int = 10 * 60

# v3.15.16.9c — canonical bootstrap event surfacing. The aggregate
# loop_closure block can hide whether the *specific* v3.15.16.5
# wiring gap is open / resolved when many unrelated human_needed
# events are present. ``_roadmap_priority_wiring_summary()`` filters
# the same three artifacts by an exact ``(reason, blocking_component)``
# pair and reports its own closed-vocabulary state, independent of
# the aggregate. The two literals below are the canonical filter.
# They are pinned by a source-text test so they cannot drift.
ROADMAP_PRIORITY_WIRING_COMPONENT: str = (
    "dashboard/dashboard.py:register_roadmap_priority_routes"
)
ROADMAP_PRIORITY_WIRING_REASON: str = "governance_bootstrap_required"

# Closed reason vocabulary surfaced when
# ``roadmap_priority_wiring.state == "not_available"``. The set is
# small on purpose: every entry maps to a deterministic upstream
# condition the operator can act on.
ROADMAP_PRIORITY_WIRING_NOT_AVAILABLE_REASONS: tuple[str, ...] = (
    "human_needed_missing",
    "human_needed_malformed",
    "governance_bootstrap_missing",
    "governance_bootstrap_malformed",
    "approval_inbox_missing",
    "approval_inbox_malformed",
    "event_id_missing",
    "governance_bootstrap_lags_human_needed",
)

# Frozen contracts the PWA surfaces verbatim (path + sha256 only).
FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json_artifact(path: Path) -> dict[str, Any]:
    """Read a JSON artifact and return one of:

    * ``{"status": "ok", "data": <parsed dict>}`` on success;
    * ``{"status": "not_available", "reason": "missing"}`` when the
      file does not exist;
    * ``{"status": "not_available", "reason": "malformed: <error>"}``
      when the file exists but is not valid JSON.

    Always returns a dict (never raises).
    """
    if not path.exists():
        return {"status": "not_available", "reason": "missing"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {
            "status": "not_available",
            "reason": f"unreadable: {type(e).__name__}",
        }
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "status": "not_available",
            "reason": f"malformed: {type(e).__name__}",
        }
    if not isinstance(data, dict):
        return {"status": "not_available", "reason": "malformed: not_an_object"}
    return {"status": "ok", "data": data}


def _file_sha256(path: Path) -> str:
    """Compute sha256 of ``path`` or return ``"missing"`` if it does
    not exist or is unreadable. Stdlib-only, never raises."""
    import hashlib

    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return "missing"
    return h.hexdigest()


def _frozen_hashes_payload() -> dict[str, Any]:
    """Return a stable, sortable payload mapping each frozen
    contract path to its current sha256 (or ``"missing"``)."""
    return {
        "status": "ok",
        "data": {
            rel: _file_sha256(REPO_ROOT / rel) for rel in FROZEN_CONTRACTS
        },
    }


def _safe_jsonify(payload: dict[str, Any]):
    """Run ``assert_no_secrets`` over the payload, then ``jsonify``.

    If the payload would leak a credential or a sensitive-path
    fragment, the assertion raises and the surrounding error handler
    in ``dashboard.dashboard`` returns a generic 500 — the surface
    refuses to leak rather than fall through.
    """
    assert_no_secrets(payload)
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Endpoint handlers
# ---------------------------------------------------------------------------


def _status_payload() -> dict[str, Any]:
    """Aggregate health: governance status + frozen-contract hashes
    + workloop runtime summary.

    The PWA Status card consumes this. No CLI subprocess; the
    governance status reporter is imported lazily and called as a
    pure function so the read remains synchronous and side-effect
    free. The workloop runtime block is a thin projection of
    ``logs/workloop_runtime/latest.json`` — see
    ``reporting.workloop_runtime`` (v3.15.15.22).
    """
    try:
        # Late import: keeps the module light when the surface is not
        # wired up.
        from reporting.governance_status import (
            collect_status,
            assert_no_secrets as _gov_assert_no_secrets,
        )

        snap = collect_status()
        _gov_assert_no_secrets(snap)
        gov = {"status": "ok", "data": snap}
    except Exception as e:  # noqa: BLE001 — defensive boundary
        gov = {
            "status": "not_available",
            "reason": f"governance_status_error: {type(e).__name__}",
        }
    return {
        "kind": "agent_control_status",
        "schema_version": 1,
        "governance_status": gov,
        "frozen_hashes": _frozen_hashes_payload(),
        "workloop_runtime": _workloop_runtime_summary(),
        "recurring_maintenance": _recurring_maintenance_summary(),
        "approval_policy": _approval_policy_summary(),
        "autonomy_metrics": _autonomy_metrics_summary(),
        "roadmap_protocol": _roadmap_protocol_summary(),
        "loop_closure": _loop_closure_summary(),
    }


def _roadmap_priority_wiring_summary(
    hn_env: dict[str, Any],
    gb_env: dict[str, Any],
    ai_env: dict[str, Any],
) -> dict[str, Any]:
    """v3.15.16.9c — derive the canonical bootstrap event surfacing.

    Consumes the *same* three artifact envelopes that the aggregate
    ``_loop_closure_summary()`` already reads and reports its own
    state, independent of the aggregate ``loop_state``. This lets the
    operator see whether the *specific* v3.15.16.5 wiring gap is open
    / resolved without being drowned out by 200+ unrelated
    ``human_needed`` events.

    Returned shape (closed vocabulary, never raises)::

        {
            "state": "open" | "resolved" | "not_available",
            "reason": str | None,
            "event_id": str | None,
            "blocking_component": str | None,
            "source_reason": str | None,
            "template_branch": str | None,
            "inbox_row_present": bool,
        }

    State semantics:

    * ``open`` — at least one ``human_needed.events[*]`` matches both
      canonical literals AND yields a non-empty ``event_id``. The
      lex-smallest matching event_id is reported. ``template_branch``
      is resolved by ``source_event_id == event_id`` AND
      ``source_reason == REASON`` (PRIMARY match). ``inbox_row_present``
      is ``True`` only when an ``approval_inbox.items[*]`` has
      ``source == f"human_needed:{event_id}"`` (exact equality).

    * ``resolved`` — all three artifacts valid (events / templates /
      items are lists) AND no ``human_needed`` event matches the
      canonical pair AND no ``governance_bootstrap`` template matches
      ``source_reason == REASON`` AND
      ``evidence.blocking_component == COMPONENT``. Unrelated events
      may persist; aggregate ``loop_state`` may still be ``open``.

    * ``not_available`` — any artifact is missing or malformed, or
      the artifacts are mid-refresh inconsistent. ``reason`` carries
      the closed-vocabulary value from
      ``ROADMAP_PRIORITY_WIRING_NOT_AVAILABLE_REASONS``.

    Hard guarantees:

    * Stdlib-only. No subprocess, no network, no git, no gh.
    * Reads artifact envelopes only — never re-reads the disk.
    * Never returns ``proposed_patch``, ``pr_body``, ``file_diff``,
      ``commit_message``, or any other large/sensitive template
      payload. Bounded scalars only.
    """

    def _na(reason: str) -> dict[str, Any]:
        return {
            "state": "not_available",
            "reason": reason,
            "event_id": None,
            "blocking_component": None,
            "source_reason": None,
            "template_branch": None,
            "inbox_row_present": False,
        }

    # 1. Validate each artifact's envelope and inner shape.
    if hn_env.get("status") != "ok":
        return _na("human_needed_missing")
    hn_data = hn_env.get("data") or {}
    if not isinstance(hn_data, dict):
        return _na("human_needed_malformed")
    hn_events = hn_data.get("events")
    if not isinstance(hn_events, list):
        return _na("human_needed_malformed")

    if gb_env.get("status") != "ok":
        return _na("governance_bootstrap_missing")
    gb_data = gb_env.get("data") or {}
    if not isinstance(gb_data, dict):
        return _na("governance_bootstrap_malformed")
    gb_templates = gb_data.get("templates")
    if not isinstance(gb_templates, list):
        return _na("governance_bootstrap_malformed")

    if ai_env.get("status") != "ok":
        return _na("approval_inbox_missing")
    ai_data = ai_env.get("data") or {}
    if not isinstance(ai_data, dict):
        return _na("approval_inbox_malformed")
    ai_items = ai_data.get("items")
    if not isinstance(ai_items, list):
        return _na("approval_inbox_malformed")

    # 2. Identify canonical references in each source.
    matching_hn_events = [
        e
        for e in hn_events
        if isinstance(e, dict)
        and e.get("reason") == ROADMAP_PRIORITY_WIRING_REASON
        and e.get("blocking_component") == ROADMAP_PRIORITY_WIRING_COMPONENT
    ]
    canonical_hn_event_ids = sorted(
        eid
        for eid in (str(e.get("event_id") or "") for e in matching_hn_events)
        if eid
    )
    matching_gb_templates = [
        t
        for t in gb_templates
        if isinstance(t, dict)
        and t.get("source_reason") == ROADMAP_PRIORITY_WIRING_REASON
        and isinstance(t.get("evidence"), dict)
        and t["evidence"].get("blocking_component")
        == ROADMAP_PRIORITY_WIRING_COMPONENT
    ]
    canonical_gb_event_ids = sorted(
        eid
        for eid in (
            str(t.get("source_event_id") or "") for t in matching_gb_templates
        )
        if eid
    )

    # 3. Decide.
    if matching_hn_events and not canonical_hn_event_ids:
        return _na("event_id_missing")

    if canonical_hn_event_ids:
        event_id = canonical_hn_event_ids[0]
        template_branch: str | None = None
        for t in gb_templates:
            if (
                isinstance(t, dict)
                and str(t.get("source_event_id") or "") == event_id
                and t.get("source_reason") == ROADMAP_PRIORITY_WIRING_REASON
            ):
                bn = t.get("branch_name")
                if isinstance(bn, str) and bn:
                    template_branch = bn
                    break
        inbox_source = f"human_needed:{event_id}"
        inbox_row_present = any(
            isinstance(it, dict) and it.get("source") == inbox_source
            for it in ai_items
        )
        return {
            "state": "open",
            "reason": None,
            "event_id": event_id,
            "blocking_component": ROADMAP_PRIORITY_WIRING_COMPONENT,
            "source_reason": ROADMAP_PRIORITY_WIRING_REASON,
            "template_branch": template_branch,
            "inbox_row_present": inbox_row_present,
        }

    if canonical_gb_event_ids:
        return _na("governance_bootstrap_lags_human_needed")

    return {
        "state": "resolved",
        "reason": None,
        "event_id": None,
        "blocking_component": None,
        "source_reason": None,
        "template_branch": None,
        "inbox_row_present": False,
    }


def _loop_closure_summary() -> dict[str, Any]:
    """v3.15.16.9b — surface the autonomous-loop closure state on
    the existing Status card.

    Reads three already-published artifacts:

    * ``logs/human_needed/latest.json`` (v3.15.16.8) — counts.events_total,
      top events[0].blocking_component, generated_at_utc.
    * ``logs/governance_bootstrap/latest.json`` (v3.15.16.9) —
      counts.templates_total, top templates[0].branch_name,
      generated_at_utc.
    * ``logs/approval_inbox/latest.json`` (v3.15.15.20+) — count of
      data.items where source startswith ``human_needed:``,
      generated_at_utc.

    Returns the bounded envelope::

        {status: "ok"|"not_available", reason?, data?: {
            loop_state: "open"|"resolved"|"stale",
            human_needed: {events_total, by_reason,
                           top_blocking_component, generated_at_utc},
            governance_bootstrap: {templates_total, top_branch_name,
                                   generated_at_utc},
            approval_inbox: {human_needed_derived_rows,
                             generated_at_utc},
            last_refreshed_utc: str
        }}

    Hard guarantees:

    * ``loop_state`` is the semantic state, separate from
      transport-level ``status``.
    * No ``proposed_patch``, no ``pr_body``, no full ``events`` /
      ``templates`` lists are returned. Only safe summary fields.
    * Defensive: any missing / malformed artifact -> ``not_available``.
    """
    hn_env = _read_json_artifact(HUMAN_NEEDED_LATEST)
    gb_env = _read_json_artifact(GOVERNANCE_BOOTSTRAP_LATEST)
    ai_env = _read_json_artifact(APPROVAL_INBOX_LATEST)

    # v3.15.16.9c — compute the canonical bootstrap event surfacing
    # against the same three artifact envelopes. Always emitted at
    # the envelope level so the operator sees the canonical proof
    # whether or not the aggregate loop_closure is ``ok``.
    rpw = _roadmap_priority_wiring_summary(hn_env, gb_env, ai_env)

    if hn_env.get("status") != "ok":
        return {
            "status": "not_available",
            "reason": f"human_needed: {hn_env.get('reason') or 'unknown'}",
            "roadmap_priority_wiring": rpw,
        }
    if gb_env.get("status") != "ok":
        return {
            "status": "not_available",
            "reason": f"governance_bootstrap: {gb_env.get('reason') or 'unknown'}",
            "roadmap_priority_wiring": rpw,
        }
    if ai_env.get("status") != "ok":
        return {
            "status": "not_available",
            "reason": f"approval_inbox: {ai_env.get('reason') or 'unknown'}",
            "roadmap_priority_wiring": rpw,
        }

    hn_data = hn_env.get("data") or {}
    gb_data = gb_env.get("data") or {}
    ai_data = ai_env.get("data") or {}

    hn_ts = hn_data.get("generated_at_utc")
    gb_ts = gb_data.get("generated_at_utc")
    ai_ts = ai_data.get("generated_at_utc")
    if not all(isinstance(t, str) and t for t in (hn_ts, gb_ts, ai_ts)):
        return {
            "status": "not_available",
            "reason": "missing generated_at_utc on one or more artifacts",
            "roadmap_priority_wiring": rpw,
        }

    # human_needed projection — bounded.
    hn_counts = hn_data.get("counts") or {}
    hn_events_total = int(hn_counts.get("events_total") or 0)
    hn_by_reason = (
        dict(hn_counts.get("by_reason") or {})
        if isinstance(hn_counts.get("by_reason"), dict)
        else {}
    )
    hn_events_list = (
        hn_data.get("events") if isinstance(hn_data.get("events"), list) else []
    )
    top_blocking_component: str | None = None
    if hn_events_list:
        first = hn_events_list[0]
        if isinstance(first, dict):
            bc = first.get("blocking_component")
            if isinstance(bc, str) and bc:
                top_blocking_component = bc

    # governance_bootstrap projection — bounded.
    gb_counts = gb_data.get("counts") or {}
    gb_templates_total = int(gb_counts.get("templates_total") or 0)
    gb_templates_list = (
        gb_data.get("templates")
        if isinstance(gb_data.get("templates"), list)
        else []
    )
    top_branch_name: str | None = None
    if gb_templates_list:
        first_t = gb_templates_list[0]
        if isinstance(first_t, dict):
            bn = first_t.get("branch_name")
            if isinstance(bn, str) and bn:
                top_branch_name = bn

    # approval_inbox derived-row count — counts items whose
    # ``source`` starts with the canonical v3.15.16.8 prefix.
    items = ai_data.get("items")
    if not isinstance(items, list):
        items = []
    ai_human_needed_derived_rows = sum(
        1
        for it in items
        if isinstance(it, dict)
        and isinstance(it.get("source"), str)
        and it["source"].startswith("human_needed:")
    )

    # Derive loop_state.
    counts_all_zero = (
        hn_events_total == 0
        and gb_templates_total == 0
        and ai_human_needed_derived_rows == 0
    )

    if not counts_all_zero:
        loop_state = "open"
    else:
        # Counts all zero — judge consistency by spread of
        # generated_at_utc values. ``stale`` if the spread is
        # wider than the consistency window; ``resolved`` if
        # within the window. Parsing is defensive: if any
        # timestamp is unparsable, fall back to ``stale``.
        parsed: list[float] = []
        for t in (hn_ts, gb_ts, ai_ts):
            try:
                norm = t[:-1] + "+00:00" if t.endswith("Z") else t
                parsed.append(_dt.datetime.fromisoformat(norm).timestamp())
            except (TypeError, ValueError):
                parsed = []
                break
        if not parsed or len(parsed) != 3:
            loop_state = "stale"
        else:
            spread = max(parsed) - min(parsed)
            if spread > LOOP_CLOSURE_CONSISTENCY_WINDOW_SECONDS:
                loop_state = "stale"
            else:
                loop_state = "resolved"

    # last_refreshed_utc is the lexicographic max of the three
    # ISO-Z timestamps. Lexicographic ordering is correct for
    # ISO-8601 UTC strings ending in ``Z``.
    last_refreshed_utc = max(hn_ts, gb_ts, ai_ts)

    return {
        "status": "ok",
        "data": {
            "loop_state": loop_state,
            "human_needed": {
                "events_total": hn_events_total,
                "by_reason": hn_by_reason,
                "top_blocking_component": top_blocking_component,
                "generated_at_utc": hn_ts,
            },
            "governance_bootstrap": {
                "templates_total": gb_templates_total,
                "top_branch_name": top_branch_name,
                "generated_at_utc": gb_ts,
            },
            "approval_inbox": {
                "human_needed_derived_rows": ai_human_needed_derived_rows,
                "generated_at_utc": ai_ts,
            },
            "last_refreshed_utc": last_refreshed_utc,
        },
        "roadmap_priority_wiring": rpw,
    }


def _roadmap_protocol_summary() -> dict[str, Any]:
    """Project the v3.15.15.28 roadmap-execution protocol's latest
    plan into a compact summary for the Status card. Returns
    ``not_available`` if no plan has been written yet (the protocol
    is opt-in; the operator runs ``--plan-item ... --dry-run`` and
    that produces ``logs/roadmap_execution_protocol/latest.json``).
    """
    try:
        from reporting.roadmap_execution_protocol import read_latest_snapshot

        snap = read_latest_snapshot()
        if snap is None:
            return {"status": "not_available", "reason": "missing"}
        return {
            "status": "ok",
            "data": {
                "module_version": snap.get("module_version"),
                "schema_version": snap.get("schema_version"),
                "generated_at_utc": snap.get("generated_at_utc"),
                "item_id": snap.get("item_id"),
                "title": snap.get("title"),
                "item_type": snap.get("item_type"),
                "risk_class": snap.get("risk_class"),
                "decision": snap.get("decision"),
                "status_field": snap.get("status"),
                "implementation_allowed": snap.get(
                    "implementation_allowed", False
                ),
                "executable": snap.get("executable", False),
                "safe_to_execute": snap.get("safe_to_execute", False),
                "blocked_reason": snap.get("blocked_reason"),
                "proposed_release_id": snap.get("proposed_release_id"),
                "proposed_branch": snap.get("proposed_branch"),
            },
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"roadmap_execution_protocol_error: {type(e).__name__}",
        }


def _autonomy_metrics_summary() -> dict[str, Any]:
    """Project the v3.15.15.25 autonomy metrics digest into a
    compact, read-only summary for the Status card. Returns
    ``not_available`` on a missing / malformed artifact — never
    raises.

    The summary surfaces top-level totals + final_recommendation +
    safety summary. The full artifact is at
    ``logs/autonomy_metrics/latest.json``.
    """
    try:
        from reporting.autonomy_metrics import read_latest_snapshot

        snap = read_latest_snapshot()
        if snap is None:
            return {"status": "not_available", "reason": "missing"}
        throughput = snap.get("throughput") or {}
        burden = snap.get("operator_burden") or {}
        reliability = snap.get("reliability") or {}
        safety = snap.get("safety") or {}
        return {
            "status": "ok",
            "data": {
                "module_version": snap.get("module_version"),
                "metrics_version": snap.get("metrics_version"),
                "generated_at_utc": snap.get("generated_at_utc"),
                "final_recommendation": snap.get("final_recommendation"),
                "safe_to_execute": snap.get("safe_to_execute", False),
                "throughput_summary": {
                    "proposals_total": throughput.get("proposals_total", 0),
                    "inbox_items_total": throughput.get("inbox_items_total", 0),
                    "pr_lifecycle_prs_seen": throughput.get(
                        "pr_lifecycle_prs_seen", 0
                    ),
                    "recurring_jobs_total": throughput.get(
                        "recurring_jobs_total", 0
                    ),
                    "runtime_sources_total": throughput.get(
                        "runtime_sources_total", 0
                    ),
                },
                "operator_burden_summary": {
                    "needs_human_total": burden.get("needs_human_total", 0),
                    "blocked_total": burden.get("blocked_total", 0),
                    "estimated_operator_actions_total": burden.get(
                        "estimated_operator_actions_total", 0
                    ),
                },
                "reliability_summary": {
                    "runtime_consecutive_failures": reliability.get(
                        "runtime_consecutive_failures", 0
                    ),
                    "missing_artifact_count": reliability.get(
                        "missing_artifact_count", 0
                    ),
                    "malformed_artifact_count": reliability.get(
                        "malformed_artifact_count", 0
                    ),
                },
                "safety_summary": {
                    "high_or_unknown_executable_count": safety.get(
                        "high_or_unknown_executable_count", 0
                    ),
                    "summary": safety.get("summary", "unknown"),
                },
            },
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"autonomy_metrics_error: {type(e).__name__}",
        }


def _approval_policy_summary() -> dict[str, Any]:
    """Project the v3.15.15.24 high-risk approval policy into a
    compact, read-only summary for the Status card. Returns
    ``not_available`` on any import / runtime error — never raises.

    The summary surfaces only static facts about the policy
    (module version, decision count, executable invariants); it does
    not call ``decide()`` so there is no per-row evaluation cost on
    the status surface.
    """
    try:
        from reporting.approval_policy import policy_summary

        s = policy_summary()
        return {
            "status": "ok",
            "data": {
                "module_version": s.get("module_version"),
                "schema_version": s.get("schema_version"),
                "decision_count": len(s.get("decisions") or []),
                "approval_category_count": len(
                    s.get("approval_categories") or []
                ),
                "high_or_unknown_is_executable": s.get(
                    "high_or_unknown_is_executable", False
                ),
                "execute_safe_requires_dependabot_low_or_medium": s.get(
                    "execute_safe_requires_dependabot_low_or_medium", True
                ),
                "execute_safe_requires_two_layer_opt_in": s.get(
                    "execute_safe_requires_two_layer_opt_in", True
                ),
            },
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"approval_policy_error: {type(e).__name__}",
        }


def _recurring_maintenance_summary() -> dict[str, Any]:
    """Project the latest recurring-maintenance digest into a compact
    summary suited for the Status card. Returns ``not_available`` on
    a missing or malformed artifact.

    The summary surfaces only the per-job last_status + counts +
    final_recommendation (no executor evidence detail). The full
    artifact is still readable at
    ``logs/recurring_maintenance/latest.json``.
    """
    try:
        from reporting.recurring_maintenance import read_latest_snapshot

        snap = read_latest_snapshot()
        if snap is None:
            return {"status": "not_available", "reason": "missing"}
        jobs = []
        for j in snap.get("jobs") or []:
            if not isinstance(j, dict):
                continue
            jobs.append(
                {
                    "job_type": j.get("job_type"),
                    "last_status": j.get("last_status"),
                    "enabled": j.get("enabled"),
                    "consecutive_failures": j.get("consecutive_failures"),
                    "next_run_after_utc": j.get("next_run_after_utc"),
                }
            )
        return {
            "status": "ok",
            "data": {
                "module_version": snap.get("module_version"),
                "generated_at_utc": snap.get("generated_at_utc"),
                "mode": snap.get("mode"),
                "safe_to_execute": snap.get("safe_to_execute", False),
                "counts": snap.get("counts") or {},
                "final_recommendation": snap.get("final_recommendation"),
                "jobs": jobs,
            },
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"recurring_maintenance_error: {type(e).__name__}",
        }


def _workloop_runtime_summary() -> dict[str, Any]:
    """Project the latest workloop-runtime artifact into a compact
    summary suited for the Status card. Returns ``not_available`` on
    a missing or malformed artifact.

    The summary deliberately strips the per-source ``summary`` field
    detail (it can contain long path strings) and surfaces only the
    counts + loop_health + final_recommendation. The full artifact
    is still readable at ``logs/workloop_runtime/latest.json``.
    """
    try:
        from reporting.workloop_runtime import read_latest_snapshot

        snap = read_latest_snapshot()
        if snap is None:
            return {
                "status": "not_available",
                "reason": "missing",
            }
        return {
            "status": "ok",
            "data": {
                "runtime_version": snap.get("runtime_version"),
                "generated_at_utc": snap.get("generated_at_utc"),
                "run_id": snap.get("run_id"),
                "mode": snap.get("mode"),
                "iteration": snap.get("iteration"),
                "max_iterations": snap.get("max_iterations"),
                "interval_seconds": snap.get("interval_seconds"),
                "next_run_after_utc": snap.get("next_run_after_utc"),
                "duration_ms": snap.get("duration_ms"),
                "safe_to_execute": snap.get("safe_to_execute", False),
                "loop_health": snap.get("loop_health") or {},
                "counts": snap.get("counts") or {},
                "final_recommendation": snap.get("final_recommendation"),
                "source_states": [
                    {
                        "source": s.get("source"),
                        "state": s.get("state"),
                    }
                    for s in (snap.get("sources") or [])
                    if isinstance(s, dict)
                ],
            },
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"workloop_runtime_error: {type(e).__name__}",
        }


def _activity_payload() -> dict[str, Any]:
    """Recent agent-audit timeline (last 50 events, redacted view).

    The PWA Activity card consumes this. The agent_audit_summary
    module already handles redaction; this layer just wraps it.
    """
    try:
        from reporting import agent_audit_summary as audit_summary
        import datetime as _dt

        today = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
        ledger = REPO_ROOT / "logs" / f"agent_audit.{today}.jsonl"
        snap = audit_summary.collect_timeline(ledger, limit=50)
        audit_summary.assert_no_secrets(snap)
        return {
            "kind": "agent_control_activity",
            "schema_version": 1,
            "status": "ok",
            "data": snap,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "kind": "agent_control_activity",
            "schema_version": 1,
            "status": "not_available",
            "reason": f"agent_audit_summary_error: {type(e).__name__}",
        }


def _workloop_payload() -> dict[str, Any]:
    """Latest autonomous workloop digest (if available)."""
    artifact = _read_json_artifact(WORKLOOP_LATEST)
    return {
        "kind": "agent_control_workloop",
        "schema_version": 1,
        **artifact,
        "artifact_path": "logs/autonomous_workloop/latest.json",
    }


def _pr_lifecycle_payload() -> dict[str, Any]:
    """Latest GitHub PR lifecycle digest (if available).

    On a clean Dependabot queue this returns
    ``data.prs == []`` and ``data.final_recommendation == "no_open_prs"``.
    """
    artifact = _read_json_artifact(PR_LIFECYCLE_LATEST)
    return {
        "kind": "agent_control_pr_lifecycle",
        "schema_version": 1,
        **artifact,
        "artifact_path": "logs/github_pr_lifecycle/latest.json",
    }


def _notifications_payload() -> dict[str, Any]:
    """Placeholder notification center.

    v3.15.15.18 does not ship browser push or any external
    notification service. The endpoint exists so the PWA can render
    the empty-state card; the actual notification source is gated on
    a later release (browser push for needs-human events lands in
    v3.15.15.23 per the runbook).
    """
    return {
        "kind": "agent_control_notifications",
        "schema_version": 1,
        "status": "ok",
        "mode": "placeholder",
        "data": [],
        "next_release_with_push": "v3.15.15.23",
    }


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


# Methods are explicitly listed as ["GET"] on every route. The unit
# tests assert that no other HTTP verb registers a handler.
_AGENT_CONTROL_ROUTES: tuple[tuple[str, Any], ...] = (
    ("/api/agent-control/status", _status_payload),
    ("/api/agent-control/activity", _activity_payload),
    ("/api/agent-control/workloop", _workloop_payload),
    ("/api/agent-control/pr-lifecycle", _pr_lifecycle_payload),
    ("/api/agent-control/notifications", _notifications_payload),
)


def register_agent_control_routes(app: Flask) -> None:
    """Mount the read-only agent-control routes on ``app``.

    Idempotent: re-registering on the same app is a no-op (Flask
    raises if the same endpoint name is added twice; we silence the
    duplicate by using unique endpoint names per route).
    """
    for path, handler in _AGENT_CONTROL_ROUTES:
        endpoint = "agent_control_" + path.rsplit("/", 1)[-1].replace("-", "_")

        # The closure captures ``handler`` by default-argument trick to
        # avoid late-binding the loop variable.
        def _view(_h=handler):  # type: ignore[no-untyped-def]
            return _safe_jsonify(_h())

        # Each route registers GET only. Flask defaults include HEAD
        # implicitly — we accept that since HEAD is read-only by
        # protocol.
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=_view,
            methods=["GET"],
        )
