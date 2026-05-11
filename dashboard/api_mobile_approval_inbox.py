"""N3b — Mobile Approval Inbox API (read-only, UNWIRED).

GET-only Flask blueprint that exposes the existing N3a projector
artefact at ``logs/mobile_approval_inbox/latest.json`` to the PWA
inbox-detail surface.

Hard guarantees (pinned by tests)
---------------------------------

* GET only — no POST / PUT / PATCH / DELETE handler is registered.
* Never executes a CLI subprocess, never invokes ``gh`` / ``git``.
* Never imports a Web Push library, never reads / writes any
  approval-token, never reads the env VAPID private key (which by
  policy is referenced by name only in
  ``reporting.web_push_real_transport``).
* Never mutates the upstream N3a artefact, the inbox state, or the
  decision_state of any row.
* Never approves / rejects / merges / deploys anything — no decision
  verb appears in any code path.
* Every response payload is run through
  ``reporting.agent_audit_summary.assert_no_secrets`` before send.
* ``not_available`` envelope returned when the artefact is missing,
  unreadable, or malformed.
* ``not_found`` envelope returned for a detail lookup when the
  ``event_id`` is not present in the bounded rows.
* The blueprint is intentionally **NOT** wired into
  ``dashboard/dashboard.py`` in this PR — wiring is the operator's
  two-line diff (per ``execution_authority.md``).

Routes
------

::

    GET /api/agent-control/mobile-inbox/list
        → bounded rows + counts + safe envelope

    GET /api/agent-control/mobile-inbox/detail/<event_id>
        → exactly one row matching event_id, or not_found envelope

The blueprint reads ``reporting.mobile_approval_inbox.ARTIFACT_LATEST``
exactly once per request; no caching, no background work.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify

from reporting import mobile_approval_inbox as mai
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N3b"
SCHEMA_VERSION: Final[int] = 1

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed bounds + sanitisation
# ---------------------------------------------------------------------------

#: Maximum event_id length accepted by the detail route. The N3a
#: projector caps the inbox-row event_id well below this; the cap
#: also exists as defense-in-depth against pathological URL paths.
_MAX_EVENT_ID_LEN: Final[int] = 128

#: Permissive but bounded event_id charset. The N3a projector uses
#: ``[A-Za-z0-9_-]`` for all event_id values; allowing this exact
#: charset on the URL parameter blocks any path-traversal /
#: control-character smuggling.
_EVENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_\-]+$")


# ---------------------------------------------------------------------------
# Artefact reader (read-only, never raises)
# ---------------------------------------------------------------------------


def _read_artifact() -> tuple[str, dict[str, Any]]:
    """Return ``(status, payload)`` for the N3a artefact.

    ``status`` is ``"ok"`` if the artefact parses to a dict, else
    ``"not_available"``. ``payload`` is the parsed dict on success,
    else a small envelope-friendly dict explaining the absence.
    """
    path: Path = mai.ARTIFACT_LATEST
    if not path.is_file():
        return "not_available", {"reason": "missing"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "not_available", {
            "reason": f"unreadable: {type(exc).__name__}"
        }
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return "not_available", {
            "reason": f"malformed: {type(exc).__name__}"
        }
    if not isinstance(data, dict):
        return "not_available", {"reason": "malformed: not_an_object"}
    return "ok", data


def _safe_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the projector artefact to rows whose shape matches the
    closed N3a schema. Defense-in-depth — the projector already
    enforces this, but we re-validate at the API boundary."""
    raw = data.get("rows")
    if not isinstance(raw, list):
        return []
    expected = set(mai.INBOX_ROW_KEYS)
    out: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        if set(r.keys()) != expected:
            continue
        out.append(r)
    return out[: mai.MAX_INBOX_ROWS]


# ---------------------------------------------------------------------------
# View functions
# ---------------------------------------------------------------------------


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    assert_no_secrets(payload)
    return jsonify(payload)


def _list_envelope() -> dict[str, Any]:
    status, data = _read_artifact()
    if status != "ok":
        return {
            "kind": "agent_control_mobile_inbox_list",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "not_available",
            "reason": data.get("reason", "missing"),
            "rows": [],
            "counts": {"rows": 0},
            "artifact_path": mai.ARTIFACT_RELATIVE_PATH,
            "step5_implementation_allowed": step5_implementation_allowed,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        }
    rows = _safe_rows(data)
    return {
        "kind": "agent_control_mobile_inbox_list",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": "ok",
        "rows": rows,
        "counts": {"rows": len(rows)},
        "generated_at_utc": str(data.get("generated_at_utc") or ""),
        "artifact_path": mai.ARTIFACT_RELATIVE_PATH,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    }


def _detail_envelope(event_id: str) -> tuple[dict[str, Any], int]:
    """Return ``(envelope, http_status)`` for the detail lookup."""
    if not isinstance(event_id, str) or not event_id:
        return (
            {
                "kind": "agent_control_mobile_inbox_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_event_id",
                "reason": "empty",
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            400,
        )
    if len(event_id) > _MAX_EVENT_ID_LEN:
        return (
            {
                "kind": "agent_control_mobile_inbox_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_event_id",
                "reason": "too_long",
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            400,
        )
    if not _EVENT_ID_PATTERN.match(event_id):
        return (
            {
                "kind": "agent_control_mobile_inbox_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_event_id",
                "reason": "bad_charset",
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            400,
        )
    status, data = _read_artifact()
    if status != "ok":
        return (
            {
                "kind": "agent_control_mobile_inbox_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "artifact_path": mai.ARTIFACT_RELATIVE_PATH,
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            404,
        )
    for row in _safe_rows(data):
        if row.get("event_id") == event_id:
            return (
                {
                    "kind": "agent_control_mobile_inbox_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "ok",
                    "row": row,
                    "generated_at_utc": str(
                        data.get("generated_at_utc") or ""
                    ),
                    "artifact_path": mai.ARTIFACT_RELATIVE_PATH,
                    "step5_implementation_allowed": step5_implementation_allowed,
                    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
                },
                200,
            )
    return (
        {
            "kind": "agent_control_mobile_inbox_detail",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "not_found",
            "reason": "no_matching_event_id",
            "artifact_path": mai.ARTIFACT_RELATIVE_PATH,
            "step5_implementation_allowed": step5_implementation_allowed,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        },
        404,
    )


def _view_list() -> Response:
    return _safe_jsonify(_list_envelope())


def _view_detail(event_id: str) -> tuple[Response, int] | Response:
    envelope, code = _detail_envelope(event_id)
    resp = _safe_jsonify(envelope)
    if code == 200:
        return resp
    return resp, code


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_MOBILE_INBOX_ROUTES: tuple[tuple[str, str, Any, str], ...] = (
    (
        "/api/agent-control/mobile-inbox/list",
        "GET",
        _view_list,
        "agent_control_mobile_inbox_list",
    ),
    (
        "/api/agent-control/mobile-inbox/detail/<string:event_id>",
        "GET",
        _view_detail,
        "agent_control_mobile_inbox_detail",
    ),
)


def register_mobile_approval_inbox_routes(app: Flask) -> None:
    """Register the read-only mobile-approval-inbox routes.

    NOT wired into ``dashboard/dashboard.py`` in this PR. The
    one-line wiring change ``register_mobile_approval_inbox_routes(app)``
    is operator-only per ``execution_authority.md`` (``dashboard_wiring``
    = NEEDS_HUMAN).
    """
    for path, method, handler, endpoint in _MOBILE_INBOX_ROUTES:
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "register_mobile_approval_inbox_routes",
    "step5_implementation_allowed",
]
