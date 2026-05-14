"""Agent Activity Center — read-only Flask blueprint (B2.0c, UNWIRED).

GET-only Flask blueprint that exposes the existing
``reporting.development_agent_activity_timeline`` aggregator
artefact at
``logs/development_agent_activity_timeline/latest.json`` through
six closed-shape endpoints under ``/api/agent-control/activity/*``.

This blueprint surfaces what the AAC aggregator already wrote.
It does **not** perform any mutation. It does **not** open, merge,
or deploy anything. It does **not** mint or verify approval
tokens. It does **not** invoke the GitHub CLI, the version-control
CLI, child processes, or any network library. It is auth-agnostic
and shipped UNWIRED; the two-line wiring diff in
``dashboard/dashboard.py`` is the operator's separate act per
``docs/governance/execution_authority.md`` (``dashboard_wiring`` =
NEEDS_HUMAN) and the no-touch hook on ``dashboard/dashboard.py``.

Hard guarantees (pinned by tests)
---------------------------------

* GET only — no POST / PUT / PATCH / DELETE handler is registered.
* Exactly six routes, all under ``/api/agent-control/activity/*``::

      GET /api/agent-control/activity/today
      GET /api/agent-control/activity/items
      GET /api/agent-control/activity/items/<string:item_id>
      GET /api/agent-control/activity/agents
      GET /api/agent-control/activity/artifacts
      GET /api/agent-control/activity/invariants

* Reads only the AAC aggregator artefact via
  ``reporting.development_agent_activity_timeline.ARTIFACT_LATEST``.
  Never mutates the upstream artefact. Never mutates any PR.
  Never reads ``os.environ``.
* Never imports a Web Push library, never imports an approval-token
  runtime, never imports a network library, never imports a CLI
  subprocess library.
* Every response payload is run through
  ``reporting.agent_audit_summary.assert_no_secrets`` before send.
* HTTP cache headers per
  ``docs/governance/agent_activity_center_api_contract.md`` §4::

      Cache-Control: private, max-age=10
      ETag: "<sha256-hex-prefix of generated_at_utc>"

  On a matching ``If-None-Match`` request, the endpoint returns
  ``304 Not Modified`` with empty body and the same ``ETag``.
* Closed error-code vocabulary per the API contract §8::

      invalid_enum         — query param outside closed vocab
      invalid_format       — query param violates regex
      not_in_last_snapshot — items/<id> path param not present
      aggregator_failed    — 500 case
      aggregator_missing   — 503 case

* The blueprint is intentionally **NOT** wired into
  ``dashboard/dashboard.py`` in the PR that introduces it.
* No decision-verb call appears in any code path. The companion
  unit-test source-text scan rejects approve/reject/merge/deploy/
  token-mint/token-verify call patterns at the syntactic level.
* Every envelope carries the closed Step 5 + Level 6 invariants
  verbatim::

      step5_implementation_allowed = False
      step5_enabled_substage       = "none"
      level6_enabled               = False

Routes contract
---------------

See ``docs/governance/agent_activity_center_api_contract.md`` for
the full per-endpoint response shape.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify, make_response, request

from reporting import development_agent_activity_timeline as aat
from reporting.agent_audit_summary import assert_no_secrets


# ---------------------------------------------------------------------------
# Module anchors
# ---------------------------------------------------------------------------

MODULE_VERSION: Final[str] = "v3.15.16.A15.B2.0c.api"
SCHEMA_VERSION: Final[int] = 1

ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_agent_activity_timeline/latest.json"
)


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Bounded item_id surface
# ---------------------------------------------------------------------------

#: Maximum item_id length accepted on the detail route. The
#: aggregator's id format is ``wi_<source>_<short>`` (≤ 64 chars in
#: practice); the cap exists as defense-in-depth.
_MAX_ITEM_ID_LEN: Final[int] = 128

#: Closed item_id charset. ASCII letters, digits, underscore,
#: hyphen, dot.
_ITEM_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_.\-]+$"
)


# ---------------------------------------------------------------------------
# Closed error-code vocabulary
# ---------------------------------------------------------------------------

_ERR_INVALID_ENUM: Final[str] = "invalid_enum"
_ERR_INVALID_FORMAT: Final[str] = "invalid_format"
_ERR_NOT_IN_LAST_SNAPSHOT: Final[str] = "not_in_last_snapshot"
_ERR_AGGREGATOR_FAILED: Final[str] = "aggregator_failed"
_ERR_AGGREGATOR_MISSING: Final[str] = "aggregator_missing"


# ---------------------------------------------------------------------------
# HTTP cache semantics
# ---------------------------------------------------------------------------

_CACHE_CONTROL: Final[str] = "private, max-age=10"


# ---------------------------------------------------------------------------
# Bounded sizes
# ---------------------------------------------------------------------------

#: Today headline-section cap per the API contract §3.1.
_TODAY_SECTION_CAP: Final[int] = 16

#: Items list cap (matches aggregator MAX_WORK_ITEMS).
_ITEMS_LIST_CAP: Final[int] = 256

#: Recent-events cap on the Today endpoint.
_RECENT_EVENTS_CAP: Final[int] = 16


# ---------------------------------------------------------------------------
# Discipline invariants every envelope carries
# ---------------------------------------------------------------------------

_DISCIPLINE_FIELDS: Final[dict[str, bool | str]] = {
    "step5_implementation_allowed": False,
    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    "level6_enabled": False,
}


def _with_discipline(envelope: dict[str, Any]) -> dict[str, Any]:
    """Attach the closed discipline-invariant fields to ``envelope``.
    Callers never overwrite these values."""
    out = dict(envelope)
    out.update(_DISCIPLINE_FIELDS)
    return out


# ---------------------------------------------------------------------------
# Aggregator artefact reader (read-only, never raises)
# ---------------------------------------------------------------------------


def _read_artifact() -> tuple[str, dict[str, Any]]:
    """Return ``(status, payload)`` for the AAC aggregator artefact.

    Status ∈ ``{"ok", "not_available"}``. The not_available path
    carries a ``reason`` string suitable for the error envelope.
    """
    path: Path = aat.ARTIFACT_LATEST
    if not path.is_file():
        return "not_available", {"reason": "missing"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "not_available", {
            "reason": f"unreadable: {type(exc).__name__}"
        }
    try:
        import json as _json

        data = _json.loads(text)
    except (TypeError, ValueError) as exc:
        return "not_available", {
            "reason": f"malformed: {type(exc).__name__}"
        }
    if not isinstance(data, dict):
        return "not_available", {"reason": "malformed: not_an_object"}
    return "ok", data


# ---------------------------------------------------------------------------
# Response builders — ETag + Cache-Control + 304 semantics
# ---------------------------------------------------------------------------


def _etag_for(generated_at_utc: str) -> str:
    """Build a quoted ETag from the upstream ``generated_at_utc``.
    Stable across runs: the sha256 prefix is deterministic."""
    digest = hashlib.sha256(
        (generated_at_utc or "").encode("utf-8")
    ).hexdigest()[:16]
    return f'"{digest}"'


def _respond_json(
    envelope: dict[str, Any], http_status: int = 200
) -> Response:
    """Run ``assert_no_secrets`` on the envelope then wrap in a
    ``Response`` with ``Cache-Control`` and ``ETag``. Honours an
    incoming ``If-None-Match`` header by returning a bare
    ``304 Not Modified`` with the same ETag.
    """
    assert_no_secrets(envelope)
    generated_at = str(envelope.get("generated_at_utc") or "")
    etag = _etag_for(generated_at)

    # Conditional request handling — 304 only on successful (200)
    # responses where the client's ETag matches.
    if http_status == 200:
        inm = request.headers.get("If-None-Match")
        if inm and inm == etag:
            resp = make_response("", 304)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = _CACHE_CONTROL
            return resp

    resp = make_response(jsonify(envelope), http_status)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = _CACHE_CONTROL
    return resp


# ---------------------------------------------------------------------------
# Error envelope helper
# ---------------------------------------------------------------------------


def _error_envelope(
    kind: str,
    code: str,
    *,
    param: str | None = None,
    value: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a closed-vocab error envelope per API contract §8."""
    env: dict[str, Any] = {
        "kind": kind,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": code,
        "error": code,
    }
    if param is not None:
        env["param"] = param
    if value is not None:
        env["value"] = value
    if detail is not None:
        env["detail"] = detail
    env["artifact_path"] = ARTIFACT_RELATIVE_PATH
    return _with_discipline(env)


# ---------------------------------------------------------------------------
# Query-param validation helpers
# ---------------------------------------------------------------------------


def _validate_enum_param(
    param: str, value: str, vocab: tuple[str, ...]
) -> tuple[bool, str | None]:
    """Return ``(ok, error_reason)``. ``ok=True`` means the value
    is in the closed vocab."""
    if value in vocab:
        return True, None
    return False, "not_in_closed_vocab"


_ISO_UTC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso_utc(value: str) -> bool:
    return bool(_ISO_UTC_PATTERN.match(value))


# ---------------------------------------------------------------------------
# Filtering and projection helpers
# ---------------------------------------------------------------------------


def _safe_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Return ``data[key]`` if it is a list of dicts; else []."""
    raw = data.get(key)
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def _filter_items(
    rows: list[dict[str, Any]],
    *,
    stage: str | None,
    owner_role: str | None,
    human_needed: bool | None,
    updated_since: str | None,
) -> list[dict[str, Any]]:
    """Apply all four closed-vocab filters."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if stage is not None and r.get("current_stage") != stage:
            continue
        if owner_role is not None and r.get("owner_role") != owner_role:
            continue
        if human_needed is not None:
            if bool(r.get("human_needed")) != human_needed:
                continue
        if updated_since is not None:
            ru = str(r.get("updated_at") or "")
            if ru < updated_since:
                continue
        out.append(r)
    return out


def _derive_agent_matrix(
    work_items: list[dict[str, Any]],
    agent_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute the per-role activity matrix per design doc §5.5."""
    by_role: dict[str, dict[str, Any]] = {}
    for role in aat.AGENT_ROLES:
        by_role[role] = {
            "role": role,
            "new": 0,
            "planned": 0,
            "blocked": 0,
            "needs_human": 0,
            "pr_ready": 0,
            "last_action": None,
            "total": 0,
        }
    for w in work_items:
        role = w.get("owner_role")
        if not isinstance(role, str) or role not in by_role:
            continue
        row = by_role[role]
        row["total"] += 1
        stage = w.get("current_stage")
        if stage in ("discovered", "queued"):
            row["new"] += 1
        if stage == "planned":
            row["planned"] += 1
        if stage == "done_blocked":
            row["blocked"] += 1
        if w.get("human_needed"):
            row["needs_human"] += 1
        if stage in ("dry_run_ready", "pr_proposed", "merge_candidate"):
            row["pr_ready"] += 1
    # Last action per role from agent_events[]; events arrive sorted
    # ascending by (timestamp, event_id) — the last one matches.
    for ev in agent_events:
        role = ev.get("agent_role")
        if not isinstance(role, str) or role not in by_role:
            continue
        by_role[role]["last_action"] = ev
    return [by_role[role] for role in aat.AGENT_ROLES]


def _today_section(
    rows: list[dict[str, Any]],
    predicate,
    cap: int = _TODAY_SECTION_CAP,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Apply ``predicate`` and cap. Returns ``(slice, total, truncated)``."""
    matching = [r for r in rows if predicate(r)]
    total = len(matching)
    truncated = total > cap
    return matching[:cap], total, truncated


# ---------------------------------------------------------------------------
# View functions
# ---------------------------------------------------------------------------


def _view_today() -> Response:
    status, data = _read_artifact()
    if status != "ok":
        env = _with_discipline(
            {
                "kind": "agent_control_activity_today",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "counts": {},
                "needs_human": [],
                "merge_candidate": [],
                "ci_feedback": [],
                "blocked": [],
                "recent_events": [],
                "freshness": {},
                "invariant_status": [],
                "generated_at_utc": "",
                "artifact_path": ARTIFACT_RELATIVE_PATH,
            }
        )
        return _respond_json(env, 200)

    work_items = _safe_list(data, "work_items")
    agent_events = _safe_list(data, "agent_events")
    invariants = _safe_list(data, "invariant_status")
    freshness = data.get("freshness") if isinstance(
        data.get("freshness"), dict
    ) else {}
    counts = data.get("counts") if isinstance(
        data.get("counts"), dict
    ) else {}

    needs_human, nh_total, nh_trunc = _today_section(
        work_items, lambda r: bool(r.get("human_needed"))
    )
    merge_cand, mc_total, mc_trunc = _today_section(
        work_items, lambda r: r.get("current_stage") == "merge_candidate"
    )
    ci_fb, ci_total, ci_trunc = _today_section(
        work_items, lambda r: r.get("current_stage") == "ci_feedback"
    )
    blocked, bl_total, bl_trunc = _today_section(
        work_items, lambda r: r.get("current_stage") == "done_blocked"
    )
    recent_events = agent_events[-_RECENT_EVENTS_CAP:][::-1]

    env = _with_discipline(
        {
            "kind": "agent_control_activity_today",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "counts": counts,
            "needs_human": needs_human,
            "merge_candidate": merge_cand,
            "ci_feedback": ci_fb,
            "blocked": blocked,
            "recent_events": recent_events,
            "freshness": freshness,
            "invariant_status": invariants,
            "section_totals": {
                "needs_human": {
                    "total_matching": nh_total,
                    "truncated": nh_trunc,
                },
                "merge_candidate": {
                    "total_matching": mc_total,
                    "truncated": mc_trunc,
                },
                "ci_feedback": {
                    "total_matching": ci_total,
                    "truncated": ci_trunc,
                },
                "blocked": {
                    "total_matching": bl_total,
                    "truncated": bl_trunc,
                },
            },
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


def _view_items_list() -> Response | tuple[Response, int]:
    # Parse query params (all optional).
    stage = request.args.get("stage")
    owner_role = request.args.get("owner_role")
    human_needed_raw = request.args.get("human_needed")
    updated_since = request.args.get("updated_since")

    if stage is not None:
        ok, _r = _validate_enum_param("stage", stage, aat.STAGES)
        if not ok:
            return (
                _respond_json(
                    _error_envelope(
                        "agent_control_activity_items_list",
                        _ERR_INVALID_ENUM,
                        param="stage",
                        value=stage,
                    ),
                    400,
                ),
                400,
            )
    if owner_role is not None:
        ok, _r = _validate_enum_param(
            "owner_role", owner_role, aat.AGENT_ROLES
        )
        if not ok:
            return (
                _respond_json(
                    _error_envelope(
                        "agent_control_activity_items_list",
                        _ERR_INVALID_ENUM,
                        param="owner_role",
                        value=owner_role,
                    ),
                    400,
                ),
                400,
            )
    human_needed: bool | None = None
    if human_needed_raw is not None:
        if human_needed_raw == "true":
            human_needed = True
        elif human_needed_raw == "false":
            human_needed = False
        else:
            return (
                _respond_json(
                    _error_envelope(
                        "agent_control_activity_items_list",
                        _ERR_INVALID_ENUM,
                        param="human_needed",
                        value=human_needed_raw,
                    ),
                    400,
                ),
                400,
            )
    if updated_since is not None and not _validate_iso_utc(updated_since):
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_list",
                    _ERR_INVALID_FORMAT,
                    param="updated_since",
                    value=updated_since,
                ),
                400,
            ),
            400,
        )

    status, data = _read_artifact()
    if status != "ok":
        env = _with_discipline(
            {
                "kind": "agent_control_activity_items_list",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "work_items": [],
                "freshness": {},
                "generated_at_utc": "",
                "artifact_path": ARTIFACT_RELATIVE_PATH,
            }
        )
        return _respond_json(env, 200)

    work_items = _safe_list(data, "work_items")
    filtered = _filter_items(
        work_items,
        stage=stage,
        owner_role=owner_role,
        human_needed=human_needed,
        updated_since=updated_since,
    )
    total = len(filtered)
    truncated = total > _ITEMS_LIST_CAP
    capped = filtered[:_ITEMS_LIST_CAP]
    freshness = data.get("freshness") if isinstance(
        data.get("freshness"), dict
    ) else {}

    env = _with_discipline(
        {
            "kind": "agent_control_activity_items_list",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "work_items": capped,
            "total_matching": total,
            "truncated": truncated,
            "freshness": freshness,
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


def _view_items_detail(
    item_id: str,
) -> Response | tuple[Response, int]:
    if not isinstance(item_id, str) or not item_id:
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_detail",
                    _ERR_INVALID_FORMAT,
                    param="item_id",
                    detail="empty",
                ),
                400,
            ),
            400,
        )
    if len(item_id) > _MAX_ITEM_ID_LEN:
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_detail",
                    _ERR_INVALID_FORMAT,
                    param="item_id",
                    detail="too_long",
                ),
                400,
            ),
            400,
        )
    if not _ITEM_ID_PATTERN.match(item_id):
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_detail",
                    _ERR_INVALID_FORMAT,
                    param="item_id",
                    detail="bad_charset",
                ),
                400,
            ),
            400,
        )

    status, data = _read_artifact()
    if status != "ok":
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_detail",
                    _ERR_AGGREGATOR_MISSING,
                    detail=data.get("reason", "missing"),
                ),
                503,
            ),
            503,
        )

    work_items = _safe_list(data, "work_items")
    target: dict[str, Any] | None = None
    for w in work_items:
        if w.get("item_id") == item_id:
            target = w
            break

    if target is None:
        return (
            _respond_json(
                _error_envelope(
                    "agent_control_activity_items_detail",
                    _ERR_NOT_IN_LAST_SNAPSHOT,
                    param="item_id",
                    value=item_id,
                ),
                404,
            ),
            404,
        )

    related_event_ids = set(target.get("event_ids") or [])
    agent_events = [
        e
        for e in _safe_list(data, "agent_events")
        if e.get("item_id") == item_id
        or (
            isinstance(e.get("event_id"), str)
            and e["event_id"] in related_event_ids
        )
    ]
    human_actions = [
        a
        for a in _safe_list(data, "human_actions")
        if a.get("item_id") == item_id
    ]
    artefacts_referenced: list[str] = []
    seen_paths: set[str] = set()
    src = target.get("source_path")
    if isinstance(src, str) and src not in seen_paths:
        artefacts_referenced.append(src)
        seen_paths.add(src)
    for e in agent_events:
        ap = e.get("artifact_path")
        if isinstance(ap, str) and ap not in seen_paths:
            artefacts_referenced.append(ap)
            seen_paths.add(ap)
    for a in human_actions:
        ap = a.get("source_artifact_path")
        if isinstance(ap, str) and ap not in seen_paths:
            artefacts_referenced.append(ap)
            seen_paths.add(ap)

    env = _with_discipline(
        {
            "kind": "agent_control_activity_items_detail",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "work_item": target,
            "agent_events": agent_events,
            "human_actions": human_actions,
            "artefacts_referenced": artefacts_referenced,
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


def _view_agents() -> Response:
    status, data = _read_artifact()
    if status != "ok":
        env = _with_discipline(
            {
                "kind": "agent_control_activity_agents",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "rows": [],
                "generated_at_utc": "",
                "artifact_path": ARTIFACT_RELATIVE_PATH,
            }
        )
        return _respond_json(env, 200)
    work_items = _safe_list(data, "work_items")
    agent_events = _safe_list(data, "agent_events")
    rows = _derive_agent_matrix(work_items, agent_events)
    env = _with_discipline(
        {
            "kind": "agent_control_activity_agents",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "rows": rows,
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


def _view_artifacts() -> Response:
    status, data = _read_artifact()
    if status != "ok":
        env = _with_discipline(
            {
                "kind": "agent_control_activity_artifacts",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "artifact_health": [],
                "generated_at_utc": "",
                "artifact_path": ARTIFACT_RELATIVE_PATH,
            }
        )
        return _respond_json(env, 200)
    env = _with_discipline(
        {
            "kind": "agent_control_activity_artifacts",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "artifact_health": _safe_list(data, "artifact_health"),
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


def _view_invariants() -> Response:
    status, data = _read_artifact()
    if status != "ok":
        env = _with_discipline(
            {
                "kind": "agent_control_activity_invariants",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "status": "not_available",
                "reason": data.get("reason", "missing"),
                "invariant_status": [],
                "generated_at_utc": "",
                "artifact_path": ARTIFACT_RELATIVE_PATH,
            }
        )
        return _respond_json(env, 200)
    env = _with_discipline(
        {
            "kind": "agent_control_activity_invariants",
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "status": "ok",
            "invariant_status": _safe_list(data, "invariant_status"),
            "generated_at_utc": str(data.get("generated_at_utc") or ""),
            "artifact_path": ARTIFACT_RELATIVE_PATH,
        }
    )
    return _respond_json(env, 200)


# ---------------------------------------------------------------------------
# Route table + registrar
# ---------------------------------------------------------------------------


_AGENT_CONTROL_ACTIVITY_ROUTES: tuple[
    tuple[str, str, Any, str], ...
] = (
    (
        "/api/agent-control/activity/today",
        "GET",
        _view_today,
        "agent_control_activity_today",
    ),
    (
        "/api/agent-control/activity/items",
        "GET",
        _view_items_list,
        "agent_control_activity_items_list",
    ),
    (
        "/api/agent-control/activity/items/<string:item_id>",
        "GET",
        _view_items_detail,
        "agent_control_activity_items_detail",
    ),
    (
        "/api/agent-control/activity/agents",
        "GET",
        _view_agents,
        "agent_control_activity_agents",
    ),
    (
        "/api/agent-control/activity/artifacts",
        "GET",
        _view_artifacts,
        "agent_control_activity_artifacts",
    ),
    (
        "/api/agent-control/activity/invariants",
        "GET",
        _view_invariants,
        "agent_control_activity_invariants",
    ),
)


def register_agent_control_activity_routes(app: Flask) -> None:
    """Register the read-only Agent Activity Center routes.

    NOT wired into ``dashboard/dashboard.py`` in the PR that
    introduces this blueprint. The two-line wiring change

    ::

        from dashboard.api_agent_control_activity import (
            register_agent_control_activity_routes,
        )
        register_agent_control_activity_routes(app)

    is operator-only per
    ``docs/governance/execution_authority.md``
    (``dashboard_wiring`` = NEEDS_HUMAN) and the no-touch hook at
    ``.claude/hooks/deny_no_touch.py`` (which protects
    ``dashboard/dashboard.py``).
    """
    for path, method, handler, endpoint in _AGENT_CONTROL_ACTIVITY_ROUTES:
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
    "register_agent_control_activity_routes",
    "step5_implementation_allowed",
]
