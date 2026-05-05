"""Read-only Flask route for the v3.15.16.5 PWA Next-Up card.

Single GET endpoint: ``/api/agent-control/next-up``. Reads the
gitignored digest at ``logs/roadmap_priority/latest.json``
(produced by ``reporting.roadmap_priority`` and refreshed on every
merge by the v3.15.16.3 deploy hook) and returns a
``not_available`` envelope when the artifact is missing or
malformed.

The endpoint never copies the full ``candidates[]`` /
``filtered_out[]`` arrays — it copies counts only, plus the
``chosen_next_up`` record. The full lists stay in the underlying
artifact for operators who need them; the PWA card stays small
and mobile-readable.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* GET only. No POST / PUT / PATCH / DELETE handler is registered.
* Never executes a CLI subprocess, never invokes ``gh`` or ``git``.
* Never reads ``config/config.yaml``, ``state/*.secret``, ``.env``,
  or any other path on the no-touch read-deny list.
* Missing / malformed / unreadable / non-object artifacts →
  ``{"status": "not_available", "reason": ...}``. ``ok`` requires
  positive evidence.
* The response payload is run through ``assert_no_secrets`` from
  ``reporting.agent_audit_summary`` before it leaves the server,
  so any credential-shaped string in the underlying digest causes
  the request to fail loudly rather than leak.
* The digest's ``safe_to_execute`` field is hard-coded ``false``
  by ``reporting.roadmap_priority``; the boundary projection here
  surfaces it verbatim.

Wiring
------

Same pattern as ``dashboard.api_proposal_queue`` and
``dashboard.api_approval_inbox``. To activate the route,
``dashboard/dashboard.py`` needs two lines::

    from dashboard.api_roadmap_priority import register_roadmap_priority_routes
    register_roadmap_priority_routes(app)

The operator authorized that wiring for v3.15.16.5, but
``dashboard/dashboard.py`` is on the no-touch list and the
``deny_no_touch`` hook blocks the write at the file level
regardless of in-chat approval. The wiring therefore lands as a
separate one-shot operator-authored governance-bootstrap PR after
this module merges — the same shape that v3.15.15.21 used to wire
``register_agent_control_routes`` / ``register_proposal_queue_routes``
/ ``register_approval_inbox_routes``. Until that bootstrap lands,
``/api/agent-control/next-up`` returns 404; the PWA frontend
collapses that to a ``not_available`` envelope and the Next-Up
card renders its empty state. Nothing crashes, nothing leaks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
LOGS_DIR: Path = REPO_ROOT / "logs"
ROADMAP_PRIORITY_LATEST: Path = (
    LOGS_DIR / "roadmap_priority" / "latest.json"
)


def _read_json_artifact(path: Path) -> dict[str, Any]:
    """Read a JSON artifact and return one of:

    * ``{"status": "ok", "data": <parsed dict>}`` on success;
    * ``{"status": "not_available", "reason": "missing"}`` when the
      file does not exist;
    * ``{"status": "not_available", "reason": "malformed: <error>"}``
      when the file exists but is not valid JSON;
    * ``{"status": "not_available", "reason": "unreadable: <error>"}``
      on filesystem error;
    * ``{"status": "not_available", "reason": "malformed: not_an_object"}``
      when the parsed payload is not a dict.

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


def _project_chosen_next_up(chosen: Any) -> dict[str, Any] | None:
    """Project ``chosen_next_up`` to the bounded subset the PWA
    card renders. Anything not in this allowlist is dropped at the
    boundary so future digest fields cannot leak through to the
    operator surface without a deliberate code change here."""
    if not isinstance(chosen, dict):
        return None
    plan_in = chosen.get("protocol_plan_summary")
    plan_out: dict[str, Any] = {}
    if isinstance(plan_in, dict):
        for k in (
            "decision",
            "implementation_allowed",
            "requires_human",
            "risk_class",
            "item_type",
            "proposed_branch",
            "proposed_release_id",
        ):
            if k in plan_in:
                plan_out[k] = plan_in[k]
        # Lists: keep, but cap at a small number to keep payload tiny.
        rt_in = plan_in.get("required_tests")
        if isinstance(rt_in, list):
            plan_out["required_tests"] = [str(x) for x in rt_in[:8]]
        ea_in = plan_in.get("expected_artifacts")
        if isinstance(ea_in, list):
            plan_out["expected_artifacts"] = [str(x) for x in ea_in[:8]]
    return {
        "proposal_id": chosen.get("proposal_id"),
        "title": chosen.get("title"),
        "summary": chosen.get("summary"),
        "proposal_type": chosen.get("proposal_type"),
        "risk_class": chosen.get("risk_class"),
        "rationale": chosen.get("rationale"),
        "protocol_plan_summary": plan_out,
    }


def _project_counts(counts: Any) -> dict[str, Any]:
    """Project counts to a stable, small-shape dict. Defensive
    against the upstream digest evolving."""
    if not isinstance(counts, dict):
        return {
            "proposals_total": 0,
            "eligible_total": 0,
            "filtered_out_total": 0,
            "filtered_out_by_reason": {},
        }
    out: dict[str, Any] = {}
    for k in ("proposals_total", "eligible_total", "filtered_out_total"):
        v = counts.get(k)
        out[k] = int(v) if isinstance(v, int) else 0
    by_reason = counts.get("filtered_out_by_reason")
    if isinstance(by_reason, dict):
        out["filtered_out_by_reason"] = {
            str(k): int(v) for k, v in by_reason.items() if isinstance(v, int)
        }
    else:
        out["filtered_out_by_reason"] = {}
    return out


def _derive_needs_human(
    final_recommendation: str | None, chosen: dict[str, Any] | None
) -> bool:
    """Deterministic ``needs_human`` projection.

    True when:
      * the digest is unavailable / unsafe, OR
      * the chosen next-up's protocol plan reports requires_human=True
        (defensive — the prioritizer filters such candidates out, but
        a future protocol classifier might emit a value the
        prioritizer did not anticipate).

    Otherwise False.
    """
    if final_recommendation in ("not_available", "unsafe"):
        return True
    if isinstance(chosen, dict):
        plan = chosen.get("protocol_plan_summary")
        if isinstance(plan, dict) and bool(plan.get("requires_human")):
            return True
    return False


def _next_up_payload() -> dict[str, Any]:
    """Build the bounded ``/api/agent-control/next-up`` envelope."""
    artifact = _read_json_artifact(ROADMAP_PRIORITY_LATEST)
    if artifact.get("status") != "ok":
        return {
            "kind": "agent_control_next_up",
            "schema_version": 1,
            "status": "not_available",
            "reason": artifact.get("reason", "unknown"),
            "artifact_path": "logs/roadmap_priority/latest.json",
        }
    raw = artifact.get("data") or {}
    chosen_projected = _project_chosen_next_up(raw.get("chosen_next_up"))
    final_recommendation = raw.get("final_recommendation")
    if not isinstance(final_recommendation, str):
        final_recommendation = "unknown"
    return {
        "kind": "agent_control_next_up",
        "schema_version": 1,
        "status": "ok",
        "data": {
            "module_version": raw.get("module_version"),
            "generated_at_utc": raw.get("generated_at_utc"),
            "final_recommendation": final_recommendation,
            "safe_to_execute": False,
            "chosen_next_up": chosen_projected,
            "counts": _project_counts(raw.get("counts")),
            "needs_human": _derive_needs_human(
                final_recommendation, chosen_projected
            ),
        },
        "artifact_path": "logs/roadmap_priority/latest.json",
    }


def _safe_jsonify(payload: dict[str, Any]):
    assert_no_secrets(payload)
    return jsonify(payload)


_ROADMAP_PRIORITY_ROUTES: tuple[tuple[str, Any], ...] = (
    ("/api/agent-control/next-up", _next_up_payload),
)


def register_roadmap_priority_routes(app: Flask) -> None:
    """Mount the read-only roadmap-priority route on ``app``.

    Uses unique endpoint names so re-registering on the same app
    doesn't collide with other agent-control modules."""
    for path, handler in _ROADMAP_PRIORITY_ROUTES:
        endpoint = "agent_control_next_up"

        def _view(_h=handler):  # type: ignore[no-untyped-def]
            return _safe_jsonify(_h())

        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=_view,
            methods=["GET"],
        )


__all__ = ["register_roadmap_priority_routes"]
