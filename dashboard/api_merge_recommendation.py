"""N5a — Merge Recommendation API blueprint (read-only, UNWIRED).

GET-only Flask blueprint that exposes the existing A23
``development_merge_recommendation`` projector artefact at
``logs/development_merge_recommendation/latest.json`` to the
operator-facing surface.

This is the **adapter preparation** slice for the future merge
approval path. The blueprint surfaces recommendation rows for the
operator (and a future N5c UI) to consult; it does **not** perform
any merge / deploy / approve / reject action, and it does **not**
mint or verify approval tokens. Actual merge execution is N5b
territory and requires a separate operator high-risk plan.

Hard guarantees (pinned by tests)
---------------------------------

* GET only — no POST / PUT / PATCH / DELETE handler is registered.
* Two routes only:

    GET /api/agent-control/merge-recommendation/list
    GET /api/agent-control/merge-recommendation/detail/<recommendation_id>

* Reads only the A23 artefact via
  ``reporting.development_merge_recommendation.ARTIFACT_LATEST``.
  Never mutates the upstream artefact, never mutates any PR, never
  invokes ``gh`` / ``git``, never opens a network socket.
* Never imports a Web Push library, never reads any approval-token
  secret, never reads the env VAPID private key (those env vars
  are referenced by name only in their respective owning modules).
* Never executes a CLI subprocess.
* Every response payload is run through
  ``reporting.agent_audit_summary.assert_no_secrets`` before send.
* ``not_available`` envelope returned when the artefact is missing,
  unreadable, or malformed.
* ``not_found`` envelope returned for a detail lookup when the
  ``recommendation_id`` is not present in the bounded rows.
* The blueprint is intentionally **NOT** wired into
  ``dashboard/dashboard.py`` in this PR — wiring is the operator's
  two-line diff (per ``execution_authority.md``).
* No decision-verb call appears in any code path (the verb-with-
  paren patterns are explicitly forbidden by the unit-test scan).
  The closed A23 recommendation-action vocabulary uses
  ``recommend_human_*`` values that are explicitly NOT the verbs
  themselves.

Routes contract
---------------

The list endpoint returns a redacted envelope shaped like:

::

    {
        "kind": "agent_control_merge_recommendation_list",
        "schema_version": 1,
        "module_version": "v3.15.16.N5a",
        "status": "ok" | "not_available",
        "rows": [...closed-schema A23 rows...],
        "counts": {"rows": <int>},
        "generated_at_utc": "<isoformat or empty>",
        "artifact_path": "logs/development_merge_recommendation/latest.json",
        "step5_implementation_allowed": false,
        "step5_enabled_substage": "none"
    }

The detail endpoint returns the same envelope shape with either a
single ``row`` field or a ``status`` of ``not_found`` /
``invalid_recommendation_id`` / ``not_available``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify

from reporting import development_merge_recommendation as dmr
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5a"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Bounded recommendation_id surface
# ---------------------------------------------------------------------------

#: Maximum recommendation_id length accepted by the detail route.
#: The A23 projector caps the value well below this; the cap also
#: exists as defense-in-depth against pathological URL paths.
_MAX_RECOMMENDATION_ID_LEN: Final[int] = 128

#: Permissive but bounded recommendation_id charset.
_RECOMMENDATION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_\-]+$"
)


# ---------------------------------------------------------------------------
# Artefact reader (read-only, never raises)
# ---------------------------------------------------------------------------


def _read_artifact() -> tuple[str, dict[str, Any]]:
    """Return ``(status, payload)`` for the A23 artefact."""
    path: Path = dmr.ARTIFACT_LATEST
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
    closed A23 schema. Defense-in-depth — the projector already
    enforces this, but we re-validate at the API boundary."""
    raw = data.get("rows")
    if not isinstance(raw, list):
        return []
    expected = set(dmr.RECOMMENDATION_ROW_KEYS)
    out: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        if set(r.keys()) != expected:
            continue
        out.append(r)
    return out[: dmr.MAX_RECOMMENDATION_ROWS]


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
            "kind": "agent_control_merge_recommendation_list",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "not_available",
            "reason": data.get("reason", "missing"),
            "rows": [],
            "counts": {"rows": 0},
            "artifact_path": dmr.ARTIFACT_RELATIVE_PATH,
            "step5_implementation_allowed": step5_implementation_allowed,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        }
    rows = _safe_rows(data)
    return {
        "kind": "agent_control_merge_recommendation_list",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": "ok",
        "rows": rows,
        "counts": {"rows": len(rows)},
        "generated_at_utc": str(data.get("generated_at_utc") or ""),
        "artifact_path": dmr.ARTIFACT_RELATIVE_PATH,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    }


def _detail_envelope(
    recommendation_id: str,
) -> tuple[dict[str, Any], int]:
    """Return ``(envelope, http_status)`` for the detail lookup."""
    if not isinstance(recommendation_id, str) or not recommendation_id:
        return (
            {
                "kind": "agent_control_merge_recommendation_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_recommendation_id",
                "reason": "empty",
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            400,
        )
    if len(recommendation_id) > _MAX_RECOMMENDATION_ID_LEN:
        return (
            {
                "kind": "agent_control_merge_recommendation_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_recommendation_id",
                "reason": "too_long",
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            400,
        )
    if not _RECOMMENDATION_ID_PATTERN.match(recommendation_id):
        return (
            {
                "kind": "agent_control_merge_recommendation_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "invalid_recommendation_id",
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
                "kind": "agent_control_merge_recommendation_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "artifact_path": dmr.ARTIFACT_RELATIVE_PATH,
                "step5_implementation_allowed": step5_implementation_allowed,
                "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
            },
            404,
        )
    for row in _safe_rows(data):
        if row.get("recommendation_id") == recommendation_id:
            return (
                {
                    "kind": "agent_control_merge_recommendation_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "ok",
                    "row": row,
                    "generated_at_utc": str(
                        data.get("generated_at_utc") or ""
                    ),
                    "artifact_path": dmr.ARTIFACT_RELATIVE_PATH,
                    "step5_implementation_allowed": step5_implementation_allowed,
                    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
                },
                200,
            )
    return (
        {
            "kind": "agent_control_merge_recommendation_detail",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "not_found",
            "reason": "no_matching_recommendation_id",
            "artifact_path": dmr.ARTIFACT_RELATIVE_PATH,
            "step5_implementation_allowed": step5_implementation_allowed,
            "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        },
        404,
    )


def _view_list() -> Response:
    return _safe_jsonify(_list_envelope())


def _view_detail(
    recommendation_id: str,
) -> tuple[Response, int] | Response:
    envelope, code = _detail_envelope(recommendation_id)
    resp = _safe_jsonify(envelope)
    if code == 200:
        return resp
    return resp, code


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_MERGE_RECOMMENDATION_ROUTES: tuple[tuple[str, str, Any, str], ...] = (
    (
        "/api/agent-control/merge-recommendation/list",
        "GET",
        _view_list,
        "agent_control_merge_recommendation_list",
    ),
    (
        "/api/agent-control/merge-recommendation/detail/<string:recommendation_id>",
        "GET",
        _view_detail,
        "agent_control_merge_recommendation_detail",
    ),
)


def register_merge_recommendation_routes(app: Flask) -> None:
    """Register the read-only merge-recommendation routes.

    NOT wired into ``dashboard/dashboard.py`` in this PR. The
    one-line wiring change ``register_merge_recommendation_routes(app)``
    is operator-only per ``execution_authority.md``
    (``dashboard_wiring`` = NEEDS_HUMAN).
    """
    for path, method, handler, endpoint in _MERGE_RECOMMENDATION_ROUTES:
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
    "register_merge_recommendation_routes",
    "step5_implementation_allowed",
]
