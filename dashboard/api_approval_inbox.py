"""Read-only Flask route for the v3.15.15.20 approval inbox.

Single GET endpoint: ``/api/agent-control/approval-inbox``. Reads the
gitignored digest at ``logs/approval_inbox/latest.json`` and returns a
``not_available`` envelope when the artifact is missing or malformed.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* GET only. No POST / PUT / PATCH / DELETE handler is registered.
* Never executes a CLI subprocess, never invokes ``gh`` or ``git``.
* Missing / malformed / unreadable artifacts → ``{"status":
  "not_available", "reason": ...}``.
* The response payload is run through ``assert_no_secrets`` from
  ``reporting.agent_audit_summary`` before it leaves the server.

Wiring
------

Same pattern as ``dashboard.api_agent_control`` and
``dashboard.api_proposal_queue``. To activate the route,
``dashboard/dashboard.py`` needs one line::

    from dashboard.api_approval_inbox import register_approval_inbox_routes
    register_approval_inbox_routes(app)

That edit is intentionally NOT shipped here — ``dashboard.py`` is on
the no-touch list. Until that operator-led PR lands, the PWA treats
the endpoint as ``not_available``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
LOGS_DIR: Path = REPO_ROOT / "logs"
APPROVAL_INBOX_LATEST: Path = LOGS_DIR / "approval_inbox" / "latest.json"


def _read_json_artifact(path: Path) -> dict[str, Any]:
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


def _approval_inbox_payload() -> dict[str, Any]:
    artifact = _read_json_artifact(APPROVAL_INBOX_LATEST)
    return {
        "kind": "agent_control_approval_inbox",
        "schema_version": 1,
        **artifact,
        "artifact_path": "logs/approval_inbox/latest.json",
    }


def _safe_jsonify(payload: dict[str, Any]):
    assert_no_secrets(payload)
    return jsonify(payload)


_APPROVAL_INBOX_ROUTES: tuple[tuple[str, Any], ...] = (
    ("/api/agent-control/approval-inbox", _approval_inbox_payload),
)


def register_approval_inbox_routes(app: Flask) -> None:
    for path, handler in _APPROVAL_INBOX_ROUTES:
        endpoint = "agent_control_approval_inbox"

        def _view(_h=handler):  # type: ignore[no-untyped-def]
            return _safe_jsonify(_h())

        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=_view,
            methods=["GET"],
        )
