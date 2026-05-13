"""N5b Phase 1 — Merge Preflight API blueprint (read-only, UNWIRED).

GET-only Flask blueprint that exposes the existing
``reporting.development_merge_preflight`` projector artefact at
``logs/development_merge_preflight/latest.json`` to the
operator-facing surface.

This blueprint surfaces the closed-schema dry-run preflight rows
that the N5b Phase 1 projector writes — joining the A22 PR-lifecycle
observer and the A23 / N5a merge recommendation into a per-PR
verdict the operator can read. It does **not** perform any merge /
deploy / approve / reject action, it does **not** mint or verify
approval tokens, it does **not** invoke ``gh`` / ``git`` /
subprocess / network. Actual live merge execution is N5b Phase
2/3/4 territory and remains permanently denied without a separate
explicit operator-go per
``docs/governance/n5b_merge_execution_plan.md`` §10.

The blueprint is auth-agnostic and shipped unwired. Its live auth
posture will be verified separately when the operator applies the
dashboard.py wiring. This PR does not expose the routes.

Hard guarantees (pinned by tests)
---------------------------------

* GET only — no POST / PUT / PATCH / DELETE handler is registered.
* Two routes only:

    GET /api/agent-control/merge-preflight/list
    GET /api/agent-control/merge-preflight/detail/<preflight_id>

* Reads only the N5b Phase 1 artefact via
  ``reporting.development_merge_preflight.ARTIFACT_LATEST``.
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
  ``preflight_id`` is not present in the bounded rows.
* ``invalid_preflight_id`` envelope returned for malformed or
  oversized ``preflight_id`` path parameters.
* The blueprint is intentionally **NOT** wired into
  ``dashboard/dashboard.py`` in the PR that introduces it — wiring
  is the operator's two-line diff (per ``execution_authority.md``).
* No decision-verb call appears in any code path (the verb-with-
  paren patterns are explicitly forbidden by the unit-test scan).
* Every list and detail envelope carries the closed
  ``step5_implementation_allowed=False``,
  ``step5_enabled_substage="none"``, ``level6_enabled=False``,
  ``dry_run_only=True``, ``live_merge_implemented=False``,
  ``deploy_coupled=False`` invariants verbatim — the projector's
  own ``discipline_invariants`` dict is mirrored at the API
  boundary so the consumer always sees them.

Routes contract
---------------

The list endpoint returns a redacted envelope shaped like:

::

    {
        "kind": "agent_control_merge_preflight_list",
        "schema_version": 1,
        "module_version": "v3.15.16.N5b.phase1.api",
        "status": "ok" | "not_available",
        "rows": [...closed-schema N5b rows...],
        "counts": {
            "rows": <int>,
            "by_dry_run_verdict": {<verdict>: <int>, ...},
        },
        "generated_at_utc": "<isoformat or empty>",
        "artifact_path": "logs/development_merge_preflight/latest.json",
        "step5_implementation_allowed": false,
        "step5_enabled_substage": "none",
        "level6_enabled": false,
        "dry_run_only": true,
        "live_merge_implemented": false,
        "deploy_coupled": false
    }

The detail endpoint returns the same envelope shape with either a
single ``row`` field or a ``status`` of ``not_found`` /
``invalid_preflight_id`` / ``not_available``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify

from reporting import development_merge_preflight as dmp
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase1.api"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Bounded preflight_id surface
# ---------------------------------------------------------------------------

#: Maximum preflight_id length accepted by the detail route. The
#: projector's id format is ``pf_<pr_number>_<sha_prefix_12>`` — far
#: shorter than this cap. The cap also exists as defense-in-depth
#: against pathological URL paths.
_MAX_PREFLIGHT_ID_LEN: Final[int] = 128

#: Permissive but bounded preflight_id charset. The projector's id
#: only contains ASCII letters, digits, and underscores; this regex
#: refuses any path segment that contains URL-encoded bytes,
#: separators, or token-shaped characters (``.``, ``=``, ``/``).
_PREFLIGHT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_\-]+$"
)


# ---------------------------------------------------------------------------
# Discipline invariants every envelope carries
# ---------------------------------------------------------------------------

_DISCIPLINE_FIELDS: Final[dict[str, bool | str]] = {
    "step5_implementation_allowed": False,
    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    "level6_enabled": False,
    "dry_run_only": True,
    "live_merge_implemented": False,
    "deploy_coupled": False,
}


def _with_discipline(envelope: dict[str, Any]) -> dict[str, Any]:
    """Attach the closed discipline-invariant fields to ``envelope``.
    Callers never overwrite these values."""
    out = dict(envelope)
    out.update(_DISCIPLINE_FIELDS)
    return out


# ---------------------------------------------------------------------------
# Artefact reader (read-only, never raises)
# ---------------------------------------------------------------------------


def _read_artifact() -> tuple[str, dict[str, Any]]:
    """Return ``(status, payload)`` for the N5b Phase 1 artefact."""
    path: Path = dmp.ARTIFACT_LATEST
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
    closed N5b Phase 1 candidate schema. Defense-in-depth — the
    projector already enforces this, but we re-validate at the API
    boundary."""
    raw = data.get("candidates")
    if not isinstance(raw, list):
        return []
    expected = set(dmp.CANDIDATE_ROW_KEYS)
    out: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        if set(r.keys()) != expected:
            continue
        out.append(r)
    return out[: dmp.MAX_CANDIDATE_ROWS]


def _by_dry_run_verdict(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Bounded counts dict over the closed
    ``DRY_RUN_VERDICTS`` vocabulary."""
    counts: dict[str, int] = {v: 0 for v in dmp.DRY_RUN_VERDICTS}
    for row in rows:
        verdict = row.get("dry_run_verdict")
        if isinstance(verdict, str) and verdict in counts:
            counts[verdict] += 1
    return counts


# ---------------------------------------------------------------------------
# View functions
# ---------------------------------------------------------------------------


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    assert_no_secrets(payload)
    return jsonify(payload)


def _list_envelope() -> dict[str, Any]:
    status, data = _read_artifact()
    if status != "ok":
        return _with_discipline(
            {
                "kind": "agent_control_merge_preflight_list",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "rows": [],
                "counts": {
                    "rows": 0,
                    "by_dry_run_verdict": {
                        v: 0 for v in dmp.DRY_RUN_VERDICTS
                    },
                },
                "artifact_path": dmp.ARTIFACT_RELATIVE_PATH,
            }
        )
    rows = _safe_rows(data)
    return _with_discipline(
        {
            "kind": "agent_control_merge_preflight_list",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "rows": rows,
            "counts": {
                "rows": len(rows),
                "by_dry_run_verdict": _by_dry_run_verdict(rows),
            },
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": dmp.ARTIFACT_RELATIVE_PATH,
        }
    )


def _detail_envelope(
    preflight_id: str,
) -> tuple[dict[str, Any], int]:
    """Return ``(envelope, http_status)`` for the detail lookup."""
    if not isinstance(preflight_id, str) or not preflight_id:
        return (
            _with_discipline(
                {
                    "kind": "agent_control_merge_preflight_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "invalid_preflight_id",
                    "reason": "empty",
                }
            ),
            400,
        )
    if len(preflight_id) > _MAX_PREFLIGHT_ID_LEN:
        return (
            _with_discipline(
                {
                    "kind": "agent_control_merge_preflight_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "invalid_preflight_id",
                    "reason": "too_long",
                }
            ),
            400,
        )
    if not _PREFLIGHT_ID_PATTERN.match(preflight_id):
        return (
            _with_discipline(
                {
                    "kind": "agent_control_merge_preflight_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "invalid_preflight_id",
                    "reason": "bad_charset",
                }
            ),
            400,
        )
    status, data = _read_artifact()
    if status != "ok":
        return (
            _with_discipline(
                {
                    "kind": "agent_control_merge_preflight_detail",
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "status": "not_available",
                    "reason": data.get("reason", "missing"),
                    "artifact_path": dmp.ARTIFACT_RELATIVE_PATH,
                }
            ),
            404,
        )
    for row in _safe_rows(data):
        if row.get("preflight_id") == preflight_id:
            return (
                _with_discipline(
                    {
                        "kind": "agent_control_merge_preflight_detail",
                        "schema_version": SCHEMA_VERSION,
                        "module_version": MODULE_VERSION,
                        "status": "ok",
                        "row": row,
                        "generated_at_utc": str(
                            data.get("generated_at_utc") or ""
                        ),
                        "artifact_path": dmp.ARTIFACT_RELATIVE_PATH,
                    }
                ),
                200,
            )
    return (
        _with_discipline(
            {
                "kind": "agent_control_merge_preflight_detail",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_found",
                "reason": "no_matching_preflight_id",
                "artifact_path": dmp.ARTIFACT_RELATIVE_PATH,
            }
        ),
        404,
    )


def _view_list() -> Response:
    return _safe_jsonify(_list_envelope())


def _view_detail(
    preflight_id: str,
) -> tuple[Response, int] | Response:
    envelope, code = _detail_envelope(preflight_id)
    resp = _safe_jsonify(envelope)
    if code == 200:
        return resp
    return resp, code


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_MERGE_PREFLIGHT_ROUTES: tuple[tuple[str, str, Any, str], ...] = (
    (
        "/api/agent-control/merge-preflight/list",
        "GET",
        _view_list,
        "agent_control_merge_preflight_list",
    ),
    (
        "/api/agent-control/merge-preflight/detail/<string:preflight_id>",
        "GET",
        _view_detail,
        "agent_control_merge_preflight_detail",
    ),
)


def register_merge_preflight_routes(app: Flask) -> None:
    """Register the read-only N5b Phase 1 merge-preflight routes.

    NOT wired into ``dashboard/dashboard.py`` in the PR that
    introduces this blueprint. The two-line wiring change

    ::

        from dashboard.api_merge_preflight import register_merge_preflight_routes
        register_merge_preflight_routes(app)

    is operator-only per ``docs/governance/execution_authority.md``
    (``dashboard_wiring`` = NEEDS_HUMAN) and the no-touch hook at
    ``.claude/hooks/deny_no_touch.py`` (which protects
    ``dashboard/dashboard.py``).
    """
    for path, method, handler, endpoint in _MERGE_PREFLIGHT_ROUTES:
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
    "register_merge_preflight_routes",
    "step5_implementation_allowed",
]
