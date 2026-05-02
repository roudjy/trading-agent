"""Read-only Flask route for the v3.15.15.21 execute-safe controls.

Single GET endpoint: ``/api/agent-control/execute-safe``. Returns the
current action catalog (eligibility verdicts only — never executes).

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* GET only. **No POST handler is registered in this release.**
  Actual execution remains CLI-only because this surface lacks
  per-operator auth / CSRF / typed confirmation flow. v3.15.15.22+
  may add a POST endpoint after the auth surface lands.
* Never mutates state.
* Reads only via the in-process
  ``reporting.execute_safe_controls.collect_catalog`` call.
* Every response payload is run through ``assert_no_secrets``.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify

from reporting.agent_audit_summary import assert_no_secrets


def _execute_safe_payload() -> dict[str, Any]:
    """Build the catalog snapshot in-process. Best-effort: any
    exception is mapped to a not_available envelope so the surface
    never falls through with an unhandled error."""
    try:
        from reporting.execute_safe_controls import collect_catalog

        snap = collect_catalog()
        return {
            "kind": "agent_control_execute_safe",
            "schema_version": 1,
            "status": "ok",
            "data": snap,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "kind": "agent_control_execute_safe",
            "schema_version": 1,
            "status": "not_available",
            "reason": f"execute_safe_controls_error: {type(e).__name__}",
        }


def _safe_jsonify(payload: dict[str, Any]):
    assert_no_secrets(payload)
    return jsonify(payload)


_EXECUTE_SAFE_ROUTES: tuple[tuple[str, Any], ...] = (
    ("/api/agent-control/execute-safe", _execute_safe_payload),
)


def register_execute_safe_routes(app: Flask) -> None:
    for path, handler in _EXECUTE_SAFE_ROUTES:
        endpoint = "agent_control_execute_safe"

        def _view(_h=handler):  # type: ignore[no-untyped-def]
            return _safe_jsonify(_h())

        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=_view,
            methods=["GET"],
        )
