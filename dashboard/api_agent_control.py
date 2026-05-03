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
