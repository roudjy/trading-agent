"""Unit tests for B2.0c — ``dashboard.api_agent_control_activity``
(UNWIRED).

Pins:

* exactly six GET routes; no other HTTP method registered;
* every endpoint returns ``not_available`` envelope when the
  aggregator artefact is missing / unreadable / malformed;
* ``today`` endpoint sections capped to 16 with
  ``total_matching`` / ``truncated`` fields;
* ``items`` list endpoint with closed-vocab filters
  (``stage`` / ``owner_role`` / ``human_needed`` / ``updated_since``)
  returns 400 ``invalid_enum`` / ``invalid_format`` on bad values;
* ``items/<id>`` detail endpoint returns 200 with single match,
  404 ``not_in_last_snapshot`` when id absent, 400
  ``invalid_format`` on bad-charset / too-long / empty;
* ``items/<id>`` returns 503 ``aggregator_missing`` when artefact
  absent;
* ``agents`` endpoint emits one row per closed agent role with
  derived counts and last_action;
* ``artifacts`` / ``invariants`` endpoints surface their slices;
* HTTP cache semantics: ``Cache-Control: private, max-age=10`` +
  ``ETag`` header + 304 on matching ``If-None-Match``;
* every envelope carries closed Step 5 + Level 6 invariants
  verbatim;
* AST + source-text scans: no subprocess / GitHub CLI /
  version-control CLI / network library / approval-token /
  decision-verb call patterns / no mutating HTTP method
  registration;
* dashboard.py wiring is enforced as a both-or-neither
  skip-or-enforce pin;
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_agent_control_activity as aaca
from reporting import development_agent_activity_timeline as aat


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    target = (
        tmp_path
        / "logs"
        / "development_agent_activity_timeline"
        / "latest.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(aat, "ARTIFACT_LATEST", target)
    return target


def _make_app() -> Flask:
    app = Flask(__name__)
    aaca.register_agent_control_activity_routes(app)
    return app


def _valid_work_item(
    *,
    item_id: str = "wi_a18c_aaa",
    title: str = "A18c row · cand_aaa",
    source_kind: str = "generated_lane",
    source_path: str = (
        "logs/development_generated_lane_a18c/latest.json"
    ),
    current_stage: str = "needs_human",
    owner_role: str = "release_gate_agent",
    risk: str = "medium",
    human_needed: bool = True,
    latest_verdict: str = "admission_decision=needs_human",
    next_action: str = "Operator review",
    updated_at: str = "2026-05-14T07:00:00Z",
    summary: str = "synthetic work item",
    event_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "source_kind": source_kind,
        "source_path": source_path,
        "current_stage": current_stage,
        "owner_role": owner_role,
        "risk": risk,
        "human_needed": human_needed,
        "latest_verdict": latest_verdict,
        "next_action": next_action,
        "updated_at": updated_at,
        "summary": summary,
        "event_ids": event_ids or [],
    }


def _valid_agent_event(
    *,
    event_id: str = "ev_aaa",
    item_id: str = "wi_a18c_aaa",
    timestamp: str = "2026-05-14T07:00:00Z",
    agent_role: str = "release_gate_agent",
    module: str = "generated_lane_a18c",
    event_type: str = "verdict",
    summary: str = "needs_human",
    decision: str = "require_human",
    reason: str = "policy",
    artifact_path: str = (
        "logs/development_generated_lane_a18c/latest.json"
    ),
    severity: str = "human",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "item_id": item_id,
        "timestamp": timestamp,
        "agent_role": agent_role,
        "module": module,
        "event_type": event_type,
        "summary": summary,
        "decision": decision,
        "reason": reason,
        "artifact_path": artifact_path,
        "severity": severity,
    }


def _valid_human_action(
    *,
    action_id: str = "ha_aaa",
    item_id: str = "wi_a18c_aaa",
    severity: str = "medium",
    title: str = "Operator review",
    why_required: str = "needs_human",
    required_phrase: str | None = None,
    safe_to_ignore: bool = False,
    copy_only: bool = True,
    source_artifact_path: str = (
        "logs/development_generated_lane_a18c/latest.json"
    ),
    suggested_role: str = "release_gate_agent",
    created_at: str = "2026-05-14T07:00:00Z",
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "item_id": item_id,
        "severity": severity,
        "title": title,
        "why_required": why_required,
        "required_phrase": required_phrase,
        "safe_to_ignore": safe_to_ignore,
        "copy_only": copy_only,
        "source_artifact_path": source_artifact_path,
        "suggested_role": suggested_role,
        "created_at": created_at,
    }


def _valid_artifact_health(
    *,
    path: str = "logs/development_work_queue/latest.json",
    group: str = "queue",
    fresh: bool = True,
    parse_ok: bool = True,
    row_count: int = 0,
    last_modified: str = "2026-05-14T07:00:00Z",
    module_version: str = "wq.v4.2",
    has_summary: bool = True,
) -> dict[str, Any]:
    return {
        "path": path,
        "group": group,
        "fresh": fresh,
        "parse_ok": parse_ok,
        "row_count": row_count,
        "last_modified": last_modified,
        "module_version": module_version,
        "has_summary": has_summary,
    }


def _valid_invariant(
    *,
    key: str = "level_6",
    label: str = "Level 6",
    value: Any = "permanently_disabled",
    tone: str = "danger_off",
    detail: str = "Level 6 stays permanently disabled.",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "tone": tone,
        "detail": detail,
    }


def _write_artifact(
    artifact_path: Path,
    *,
    work_items: list[dict[str, Any]] | None = None,
    agent_events: list[dict[str, Any]] | None = None,
    human_actions: list[dict[str, Any]] | None = None,
    artifact_health: list[dict[str, Any]] | None = None,
    invariant_status: list[dict[str, Any]] | None = None,
    generated_at_utc: str = "2026-05-14T08:00:00Z",
) -> None:
    payload = {
        "schema_version": 1,
        "module_version": "aat.v0.1",
        "report_kind": "agent_activity_timeline",
        "generated_at_utc": generated_at_utc,
        "freshness": {
            "generated_at_utc": generated_at_utc,
            "oldest_artifact_age_seconds": 0,
            "any_stale": False,
            "any_malformed": False,
            "background_refreshing": False,
            "ttl_seconds_by_path": {},
        },
        "counts": {
            "discovered": 0,
            "queued": 0,
            "delegated": 0,
            "planned": 0,
            "dry_run_ready": 0,
            "pr_proposed": 0,
            "pr_opened": 0,
            "ci_feedback": 0,
            "needs_human": 0,
            "merge_candidate": 0,
            "blocked": 0,
            "total_open": 0,
        },
        "work_items": work_items or [],
        "agent_events": agent_events or [],
        "human_actions": human_actions or [],
        "artifact_health": artifact_health or [],
        "invariant_status": invariant_status or [_valid_invariant()],
        "vocabularies": {
            "stage": list(aat.STAGES),
            "severity": list(aat.SEVERITIES),
            "decision": list(aat.DECISIONS),
            "risk": list(aat.RISKS),
            "freshness": list(aat.FRESHNESS_STATES),
            "artifact_health": list(aat.ARTIFACT_HEALTH_STATES),
            "human_action": list(aat.HUMAN_ACTION_TYPES),
            "invariant_state": list(aat.INVARIANT_STATES),
        },
    }
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_version_anchor() -> None:
    assert aaca.MODULE_VERSION == "v3.15.16.A15.B2.0c.api"


def test_schema_version_is_1() -> None:
    assert aaca.SCHEMA_VERSION == 1


def test_step5_invariants_intact_by_import() -> None:
    assert aaca.step5_implementation_allowed is False
    assert aaca.STEP5_ENABLED_SUBSTAGE == "none"


def test_artifact_relative_path_is_canonical() -> None:
    assert (
        aaca.ARTIFACT_RELATIVE_PATH
        == "logs/development_agent_activity_timeline/latest.json"
    )


def test_registrar_is_exported() -> None:
    assert "register_agent_control_activity_routes" in aaca.__all__


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_blueprint_registers_exactly_six_get_routes() -> None:
    app = _make_app()
    rules = [
        r for r in app.url_map.iter_rules()
        if r.rule.startswith("/api/agent-control/activity/")
    ]
    assert len(rules) == 6
    paths = sorted(r.rule for r in rules)
    assert paths == sorted(
        [
            "/api/agent-control/activity/today",
            "/api/agent-control/activity/items",
            "/api/agent-control/activity/items/<string:item_id>",
            "/api/agent-control/activity/agents",
            "/api/agent-control/activity/artifacts",
            "/api/agent-control/activity/invariants",
        ]
    )


def test_blueprint_registers_only_get_method() -> None:
    """Closed-verb pin: every route under the activity prefix has
    methods exactly {GET, HEAD, OPTIONS} (Flask auto-adds the last
    two)."""
    app = _make_app()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/agent-control/activity/"):
            continue
        methods = set(rule.methods or set())
        for forbidden in ("POST", "PUT", "PATCH", "DELETE"):
            assert forbidden not in methods, (
                f"forbidden method on {rule.rule}: {methods}"
            )
        assert "GET" in methods


def test_blueprint_rejects_mutating_methods_at_request_time() -> None:
    """Every endpoint returns 405 on POST/PUT/PATCH/DELETE."""
    client = _make_app().test_client()
    for path in (
        "/api/agent-control/activity/today",
        "/api/agent-control/activity/items",
        "/api/agent-control/activity/agents",
        "/api/agent-control/activity/artifacts",
        "/api/agent-control/activity/invariants",
    ):
        for verb in ("post", "put", "patch", "delete"):
            res = getattr(client, verb)(path)
            assert res.status_code in (
                405,
                404,
            ), f"{verb} {path} returned {res.status_code}"


def test_blueprint_registers_no_routes_outside_activity_prefix() -> None:
    """The blueprint owns ``/api/agent-control/activity/*`` exclusively."""
    app = _make_app()
    rules = [
        r
        for r in app.url_map.iter_rules()
        if r.endpoint
        and r.endpoint.startswith("agent_control_activity_")
    ]
    for r in rules:
        assert r.rule.startswith("/api/agent-control/activity/"), (
            f"unexpected route prefix: {r.rule}"
        )


# ---------------------------------------------------------------------------
# BOTH-or-NEITHER wiring pin
# ---------------------------------------------------------------------------


def test_blueprint_not_yet_wired_into_dashboard_dashboard() -> None:
    """Operator step pending: dashboard.py must contain BOTH the
    import and the register call for api_agent_control_activity, or
    NEITHER. The two-line wiring diff is operator-applied per the
    no-touch hook on ``dashboard/dashboard.py``."""
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_agent_control_activity "
        "import register_agent_control_activity_routes" in text
        or "from dashboard.api_agent_control_activity import (" in text
    )
    register_present = (
        "register_agent_control_activity_routes(app)" in text
    )
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_agent_control_activity, or NEITHER."
    )


# ---------------------------------------------------------------------------
# `today` endpoint
# ---------------------------------------------------------------------------


def test_today_missing_artifact_returns_not_available() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/today"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "not_available"
    assert body["needs_human"] == []
    assert body["counts"] == {}
    assert body["step5_implementation_allowed"] is False


def test_today_ok_returns_capped_sections(_isolate_artifact: Path) -> None:
    work_items = [
        _valid_work_item(
            item_id=f"wi_h_{i}",
            current_stage="needs_human",
            human_needed=True,
        )
        for i in range(20)
    ]
    _write_artifact(_isolate_artifact, work_items=work_items)
    res = _make_app().test_client().get(
        "/api/agent-control/activity/today"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert len(body["needs_human"]) == 16
    assert (
        body["section_totals"]["needs_human"]["total_matching"] == 20
    )
    assert (
        body["section_totals"]["needs_human"]["truncated"] is True
    )


def test_today_includes_merge_candidate_and_ci_feedback_sections(
    _isolate_artifact: Path,
) -> None:
    work_items = [
        _valid_work_item(
            item_id="wi_merge",
            current_stage="merge_candidate",
            human_needed=False,
        ),
        _valid_work_item(
            item_id="wi_ci",
            current_stage="ci_feedback",
            human_needed=False,
        ),
        _valid_work_item(
            item_id="wi_blocked",
            current_stage="done_blocked",
            human_needed=False,
        ),
    ]
    _write_artifact(_isolate_artifact, work_items=work_items)
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
        .get_json()
    )
    assert len(body["merge_candidate"]) == 1
    assert len(body["ci_feedback"]) == 1
    assert len(body["blocked"]) == 1


def test_today_recent_events_capped(_isolate_artifact: Path) -> None:
    events = [
        _valid_agent_event(
            event_id=f"ev_{i:03d}",
            timestamp=f"2026-05-14T07:00:{i:02d}Z",
        )
        for i in range(40)
    ]
    _write_artifact(_isolate_artifact, agent_events=events)
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
        .get_json()
    )
    assert len(body["recent_events"]) == 16


def test_today_carries_invariant_status(_isolate_artifact: Path) -> None:
    _write_artifact(
        _isolate_artifact,
        invariant_status=[
            _valid_invariant(),
            _valid_invariant(
                key="step5_implementation_allowed",
                label="Step 5 impl. allowed",
                value=False,
                tone="off",
                detail="off",
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
        .get_json()
    )
    keys = {row["key"] for row in body["invariant_status"]}
    assert "level_6" in keys
    assert "step5_implementation_allowed" in keys


def test_today_malformed_artifact_returns_not_available(
    _isolate_artifact: Path,
) -> None:
    _isolate_artifact.write_text("{not json", encoding="utf-8")
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
        .get_json()
    )
    assert body["status"] == "not_available"
    assert "malformed" in body.get("reason", "")


# ---------------------------------------------------------------------------
# `items` list endpoint
# ---------------------------------------------------------------------------


def test_items_list_ok_returns_work_items(_isolate_artifact: Path) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[_valid_work_item()],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items")
        .get_json()
    )
    assert body["status"] == "ok"
    assert body["total_matching"] == 1
    assert body["truncated"] is False
    assert len(body["work_items"]) == 1


def test_items_list_filter_stage_accepts_closed_vocab(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[
            _valid_work_item(
                item_id="wi_p", current_stage="planned", human_needed=False
            ),
            _valid_work_item(
                item_id="wi_h",
                current_stage="needs_human",
                human_needed=True,
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items?stage=planned")
        .get_json()
    )
    assert body["total_matching"] == 1
    assert body["work_items"][0]["current_stage"] == "planned"


def test_items_list_filter_stage_rejects_unknown_value() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/items?stage=bogus_stage"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["error"] == "invalid_enum"
    assert body["param"] == "stage"


def test_items_list_filter_owner_role_accepts_closed_vocab(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[
            _valid_work_item(
                item_id="wi_a",
                owner_role="release_gate_agent",
            ),
            _valid_work_item(
                item_id="wi_b",
                owner_role="planner",
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get(
            "/api/agent-control/activity/items?owner_role=planner"
        )
        .get_json()
    )
    assert body["total_matching"] == 1


def test_items_list_filter_owner_role_rejects_unknown_value() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/items?owner_role=trickster"
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_enum"


def test_items_list_filter_human_needed_true(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[
            _valid_work_item(item_id="wi_h", human_needed=True),
            _valid_work_item(item_id="wi_n", human_needed=False),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get(
            "/api/agent-control/activity/items?human_needed=true"
        )
        .get_json()
    )
    assert body["total_matching"] == 1
    assert body["work_items"][0]["human_needed"] is True


def test_items_list_filter_human_needed_rejects_garbage() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/items?human_needed=yes_please"
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_enum"


def test_items_list_filter_updated_since_rejects_malformed_ts() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/items?updated_since=yesterday"
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_format"


# ---------------------------------------------------------------------------
# `items/<id>` detail endpoint
# ---------------------------------------------------------------------------


def test_items_detail_ok(_isolate_artifact: Path) -> None:
    target = _valid_work_item(item_id="wi_target_001")
    event = _valid_agent_event(item_id="wi_target_001", event_id="ev_x")
    ha = _valid_human_action(item_id="wi_target_001")
    _write_artifact(
        _isolate_artifact,
        work_items=[target],
        agent_events=[event],
        human_actions=[ha],
    )
    res = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items/wi_target_001")
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["work_item"]["item_id"] == "wi_target_001"
    assert len(body["agent_events"]) == 1
    assert len(body["human_actions"]) == 1
    assert (
        "logs/development_generated_lane_a18c/latest.json"
        in body["artefacts_referenced"]
    )


def test_items_detail_not_in_last_snapshot_returns_404(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, work_items=[])
    res = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items/wi_nonexistent")
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["error"] == "not_in_last_snapshot"


def test_items_detail_bad_charset_returns_400() -> None:
    res = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items/has%20space")
    )
    assert res.status_code in (400, 404)
    if res.status_code == 400:
        body = res.get_json()
        assert body["error"] == "invalid_format"


def test_items_detail_too_long_returns_400() -> None:
    long_id = "a" * 200
    res = (
        _make_app()
        .test_client()
        .get(f"/api/agent-control/activity/items/{long_id}")
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["error"] == "invalid_format"
    assert body["detail"] == "too_long"


def test_items_detail_aggregator_missing_returns_503() -> None:
    res = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items/wi_anything")
    )
    assert res.status_code == 503
    body = res.get_json()
    assert body["error"] == "aggregator_missing"


# ---------------------------------------------------------------------------
# `agents` endpoint
# ---------------------------------------------------------------------------


def test_agents_missing_returns_not_available() -> None:
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/agents")
        .get_json()
    )
    assert body["status"] == "not_available"
    assert body["rows"] == []


def test_agents_ok_emits_one_row_per_closed_role(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[
            _valid_work_item(
                item_id="wi_a",
                owner_role="release_gate_agent",
                current_stage="needs_human",
                human_needed=True,
            ),
            _valid_work_item(
                item_id="wi_b",
                owner_role="planner",
                current_stage="planned",
                human_needed=False,
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/agents")
        .get_json()
    )
    assert body["status"] == "ok"
    assert len(body["rows"]) == len(aat.AGENT_ROLES)
    by_role = {r["role"]: r for r in body["rows"]}
    assert by_role["release_gate_agent"]["needs_human"] == 1
    assert by_role["planner"]["planned"] == 1


def test_agents_last_action_carries_latest_event(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        work_items=[
            _valid_work_item(
                item_id="wi_a",
                owner_role="release_gate_agent",
            ),
        ],
        agent_events=[
            _valid_agent_event(event_id="ev_old", timestamp="2026-05-14T06:00:00Z"),
            _valid_agent_event(event_id="ev_new", timestamp="2026-05-14T07:00:00Z"),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/agents")
        .get_json()
    )
    by_role = {r["role"]: r for r in body["rows"]}
    last = by_role["release_gate_agent"]["last_action"]
    assert last is not None
    assert last["event_id"] == "ev_new"


# ---------------------------------------------------------------------------
# `artifacts` endpoint
# ---------------------------------------------------------------------------


def test_artifacts_missing_returns_not_available() -> None:
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/artifacts")
        .get_json()
    )
    assert body["status"] == "not_available"


def test_artifacts_ok_passes_through_artifact_health(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        artifact_health=[
            _valid_artifact_health(),
            _valid_artifact_health(
                path="generated_seed.jsonl",
                group="seed",
                fresh=False,
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/artifacts")
        .get_json()
    )
    assert body["status"] == "ok"
    assert len(body["artifact_health"]) == 2


# ---------------------------------------------------------------------------
# `invariants` endpoint
# ---------------------------------------------------------------------------


def test_invariants_missing_returns_not_available() -> None:
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/invariants")
        .get_json()
    )
    assert body["status"] == "not_available"


def test_invariants_ok_passes_through_invariant_status(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact,
        invariant_status=[
            _valid_invariant(),
            _valid_invariant(
                key="step5_implementation_allowed",
                label="Step 5 impl. allowed",
                value=False,
                tone="off",
                detail="off",
            ),
        ],
    )
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/invariants")
        .get_json()
    )
    assert body["status"] == "ok"
    keys = {r["key"] for r in body["invariant_status"]}
    assert "level_6" in keys
    assert "step5_implementation_allowed" in keys


# ---------------------------------------------------------------------------
# HTTP cache semantics
# ---------------------------------------------------------------------------


def test_response_carries_cache_control_header(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact)
    res = _make_app().test_client().get(
        "/api/agent-control/activity/today"
    )
    assert res.headers.get("Cache-Control") == "private, max-age=10"


def test_response_carries_etag_header(_isolate_artifact: Path) -> None:
    _write_artifact(_isolate_artifact)
    res = _make_app().test_client().get(
        "/api/agent-control/activity/today"
    )
    etag = res.headers.get("ETag")
    assert etag is not None
    assert etag.startswith('"') and etag.endswith('"')


def test_if_none_match_returns_304(_isolate_artifact: Path) -> None:
    _write_artifact(_isolate_artifact)
    client = _make_app().test_client()
    first = client.get("/api/agent-control/activity/today")
    etag = first.headers["ETag"]
    second = client.get(
        "/api/agent-control/activity/today",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.headers.get("ETag") == etag
    assert second.data == b""


def test_etag_changes_when_generated_at_utc_changes(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(
        _isolate_artifact, generated_at_utc="2026-05-14T08:00:00Z"
    )
    first = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
    )
    _write_artifact(
        _isolate_artifact, generated_at_utc="2026-05-14T09:00:00Z"
    )
    second = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
    )
    assert first.headers["ETag"] != second.headers["ETag"]


# ---------------------------------------------------------------------------
# Discipline-invariant mirroring
# ---------------------------------------------------------------------------


def test_every_endpoint_mirrors_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, work_items=[_valid_work_item()])
    client = _make_app().test_client()
    paths = [
        "/api/agent-control/activity/today",
        "/api/agent-control/activity/items",
        "/api/agent-control/activity/items/wi_a18c_aaa",
        "/api/agent-control/activity/agents",
        "/api/agent-control/activity/artifacts",
        "/api/agent-control/activity/invariants",
    ]
    for path in paths:
        body = client.get(path).get_json()
        assert body["step5_implementation_allowed"] is False, path
        assert body["step5_enabled_substage"] == "none", path
        assert body["level6_enabled"] is False, path


def test_today_envelope_carries_invariants_even_when_artifact_missing() -> None:
    body = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/today")
        .get_json()
    )
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"
    assert body["level6_enabled"] is False


def test_error_envelope_carries_invariants() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/activity/items?stage=bogus"
    )
    body = res.get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"
    assert body["level6_enabled"] is False


def test_detail_404_envelope_carries_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, work_items=[])
    res = (
        _make_app()
        .test_client()
        .get("/api/agent-control/activity/items/wi_nonexistent")
    )
    body = res.get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"
    assert body["level6_enabled"] is False


# ---------------------------------------------------------------------------
# AST scans
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_TOPS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
)

_FORBIDDEN_FROM_PREFIXES = (
    "research",
    "automation",
    "broker",
    "agent.risk",
    "agent.execution",
    "reporting.intelligent_routing",
)


def _module_ast() -> ast.AST:
    return ast.parse(Path(aaca.__file__).read_text(encoding="utf-8"))


def test_blueprint_module_has_no_subprocess_or_network_imports() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                assert top not in _FORBIDDEN_IMPORT_TOPS, (
                    f"forbidden import: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in _FORBIDDEN_IMPORT_TOPS, (
                f"forbidden import: from {node.module!r}"
            )


def test_blueprint_module_has_no_qre_or_dashboard_dashboard_imports() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "dashboard.dashboard"
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module != "dashboard.dashboard"
            for prefix in _FORBIDDEN_FROM_PREFIXES:
                assert not (
                    node.module == prefix
                    or node.module.startswith(prefix + ".")
                ), f"forbidden import: from {node.module!r}"


def test_blueprint_module_has_no_os_environ_read() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            raise AssertionError(
                "blueprint references os.environ — forbidden"
            )
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                raise AssertionError(
                    "blueprint calls os.getenv — forbidden"
                )


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def test_blueprint_source_has_no_mutating_methods_literal() -> None:
    src = Path(aaca.__file__).read_text(encoding="utf-8")
    for forbidden in (
        'methods=["POST"',
        "methods=['POST'",
        'methods=["PUT"',
        "methods=['PUT'",
        'methods=["PATCH"',
        "methods=['PATCH'",
        'methods=["DELETE"',
        "methods=['DELETE'",
    ):
        assert forbidden not in src, (
            f"blueprint source contains forbidden methods literal: "
            f"{forbidden!r}"
        )


def test_blueprint_source_has_no_decision_verb_call_patterns() -> None:
    src = Path(aaca.__file__).read_text(encoding="utf-8")
    forbidden_patterns = (
        "approve(",
        "reject(",
        "merge_pr(",
        "deploy(",
        "mint_token(",
        "verify_token(",
        "subprocess.run(",
        "subprocess.Popen(",
        "os.system(",
        "os.popen(",
    )
    for needle in forbidden_patterns:
        assert needle not in src, (
            f"blueprint source contains forbidden call pattern: "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# assert_no_secrets boundary
# ---------------------------------------------------------------------------


def test_assert_no_secrets_called_on_every_envelope(
    _isolate_artifact: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_artifact(_isolate_artifact, work_items=[_valid_work_item()])
    calls: list[Any] = []

    def _spy(payload):
        calls.append(payload)

    monkeypatch.setattr(aaca, "assert_no_secrets", _spy)
    client = _make_app().test_client()
    for path in (
        "/api/agent-control/activity/today",
        "/api/agent-control/activity/items",
        "/api/agent-control/activity/items/wi_a18c_aaa",
        "/api/agent-control/activity/agents",
        "/api/agent-control/activity/artifacts",
        "/api/agent-control/activity/invariants",
    ):
        client.get(path)
    assert len(calls) >= 6
