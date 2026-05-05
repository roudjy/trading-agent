"""Unit tests for ``dashboard.api_agent_control``.

Properties enforced:

* All five endpoints respond to GET only.
* No POST / PUT / PATCH / DELETE handler is registered.
* Missing artifacts → ``{"status": "not_available", "reason": "missing"}``.
* Malformed artifacts → ``{"status": "not_available", "reason": "malformed:..."}``.
* Secret redaction is applied via ``assert_no_secrets`` on every payload.
* The notification endpoint is a placeholder (empty list,
  ``mode == "placeholder"``).
* The frozen-hashes payload reports either a 64-char sha256 or
  the literal string ``"missing"``.
* The status payload aggregates governance + frozen hashes without
  invoking ``git`` or any subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_agent_control as ac

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Flask:
    """Build a Flask app with the routes registered and the artifact
    paths redirected into ``tmp_path``."""
    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac, "WORKLOOP_LATEST", tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    )
    monkeypatch.setattr(
        ac,
        "PR_LIFECYCLE_LATEST",
        tmp_path / "logs" / "github_pr_lifecycle" / "latest.json",
    )
    # v3.15.16.9b — redirect the three Loop closure source paths
    # too so the ``isolated`` test environment cannot read repo
    # artifacts.
    monkeypatch.setattr(
        ac,
        "HUMAN_NEEDED_LATEST",
        tmp_path / "logs" / "human_needed" / "latest.json",
    )
    monkeypatch.setattr(
        ac,
        "GOVERNANCE_BOOTSTRAP_LATEST",
        tmp_path / "logs" / "governance_bootstrap" / "latest.json",
    )
    monkeypatch.setattr(
        ac,
        "APPROVAL_INBOX_LATEST",
        tmp_path / "logs" / "approval_inbox" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_agent_control_routes(flask_app)
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


# ---------------------------------------------------------------------------
# Verb whitelist
# ---------------------------------------------------------------------------


_PATHS: tuple[str, ...] = (
    "/api/agent-control/status",
    "/api/agent-control/activity",
    "/api/agent-control/workloop",
    "/api/agent-control/pr-lifecycle",
    "/api/agent-control/notifications",
)


@pytest.mark.parametrize("path", _PATHS)
def test_get_returns_200(client, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"
    assert resp.is_json


@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("verb", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_verbs_are_rejected(client, path: str, verb: str) -> None:
    resp = client.open(path, method=verb)
    # Flask returns 405 Method Not Allowed for unregistered verbs.
    assert resp.status_code == 405, (
        f"{verb} {path} should be 405 (no mutation handler), got {resp.status_code}"
    )


def test_only_documented_routes_are_registered(app: Flask) -> None:
    """The agent-control surface is exactly the five routes; no extra
    endpoints sneak in via auto-discovery."""
    rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/api/agent-control/")]
    paths = sorted(r.rule for r in rules)
    assert paths == sorted(_PATHS)
    # Each rule registers GET + HEAD (HEAD is implicit) — never a
    # mutating verb.
    for r in rules:
        verbs = set(r.methods or ()) - {"HEAD", "OPTIONS"}
        assert verbs == {"GET"}, (
            f"route {r.rule} accepts unexpected verbs: {verbs}"
        )


# ---------------------------------------------------------------------------
# not_available semantics
# ---------------------------------------------------------------------------


def test_workloop_missing_artifact_yields_not_available(client) -> None:
    resp = client.get("/api/agent-control/workloop")
    body = resp.get_json()
    assert body["status"] == "not_available"
    assert body["reason"] == "missing"
    assert body["artifact_path"] == "logs/autonomous_workloop/latest.json"


def test_pr_lifecycle_missing_artifact_yields_not_available(client) -> None:
    resp = client.get("/api/agent-control/pr-lifecycle")
    body = resp.get_json()
    assert body["status"] == "not_available"
    assert body["reason"] == "missing"


def test_workloop_malformed_artifact_yields_not_available(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "logs" / "autonomous_workloop" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(ac, "WORKLOOP_LATEST", p)
    resp = client.get("/api/agent-control/workloop")
    body = resp.get_json()
    assert body["status"] == "not_available"
    assert body["reason"].startswith("malformed:")


def test_pr_lifecycle_non_object_artifact_yields_not_available(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(ac, "PR_LIFECYCLE_LATEST", p)
    resp = client.get("/api/agent-control/pr-lifecycle")
    body = resp.get_json()
    assert body["status"] == "not_available"
    assert "not_an_object" in body["reason"]


def test_pr_lifecycle_with_valid_artifact_passes_through(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "report_kind": "github_pr_lifecycle_digest",
        "module_version": "v3.15.15.17",
        "prs": [],
        "final_recommendation": "no_open_prs",
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ac, "PR_LIFECYCLE_LATEST", p)
    resp = client.get("/api/agent-control/pr-lifecycle")
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["data"]["final_recommendation"] == "no_open_prs"


# ---------------------------------------------------------------------------
# Notifications placeholder
# ---------------------------------------------------------------------------


def test_notifications_is_placeholder(client) -> None:
    resp = client.get("/api/agent-control/notifications")
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["mode"] == "placeholder"
    assert body["data"] == []
    # Forward-compat: surface advertises which release introduces push.
    assert body.get("next_release_with_push", "").startswith("v3.15.15.")


# ---------------------------------------------------------------------------
# Frozen hashes (paths only, never content)
# ---------------------------------------------------------------------------


def test_status_payload_includes_recurring_maintenance_block(client) -> None:
    """v3.15.15.23: status payload now also carries a
    recurring_maintenance summary."""
    body = client.get("/api/agent-control/status").get_json()
    assert "recurring_maintenance" in body
    rm_block = body["recurring_maintenance"]
    assert rm_block["status"] in ("ok", "not_available")
    if rm_block["status"] == "not_available":
        assert "reason" in rm_block


def test_status_payload_includes_approval_policy_block(client) -> None:
    """v3.15.15.24: status payload now also carries a read-only
    approval_policy summary. The block must not be silently OK on
    error — it either reports ``ok`` with a populated ``data`` dict
    or ``not_available`` with a reason."""
    body = client.get("/api/agent-control/status").get_json()
    assert "approval_policy" in body
    ap_block = body["approval_policy"]
    assert ap_block["status"] in ("ok", "not_available")
    if ap_block["status"] == "ok":
        data = ap_block["data"]
        assert data["high_or_unknown_is_executable"] is False
        assert data["execute_safe_requires_dependabot_low_or_medium"] is True
        assert data["execute_safe_requires_two_layer_opt_in"] is True
        assert isinstance(data["module_version"], str)
        assert isinstance(data["decision_count"], int)
        assert data["decision_count"] >= 14
    else:
        assert "reason" in ap_block


def test_status_payload_includes_autonomy_metrics_block(client) -> None:
    """v3.15.15.25: status payload now also carries a read-only
    autonomy_metrics summary. The block must not be silently OK on
    error — it either reports ``ok`` with a populated ``data`` dict
    or ``not_available`` with a reason."""
    body = client.get("/api/agent-control/status").get_json()
    assert "autonomy_metrics" in body
    am_block = body["autonomy_metrics"]
    assert am_block["status"] in ("ok", "not_available")
    if am_block["status"] == "ok":
        data = am_block["data"]
        assert data["safe_to_execute"] is False
        assert "final_recommendation" in data
        assert "throughput_summary" in data
        assert "operator_burden_summary" in data
        assert "reliability_summary" in data
        assert "safety_summary" in data
    else:
        assert "reason" in am_block


def test_status_payload_includes_roadmap_protocol_block(client) -> None:
    """v3.15.15.28: status payload now also carries a read-only
    roadmap_protocol summary. The block is ``not_available`` until
    the operator runs ``--plan-item ... --dry-run`` for the first
    time; ``ok`` once a plan exists. The protocol surface itself
    never executes."""
    body = client.get("/api/agent-control/status").get_json()
    assert "roadmap_protocol" in body
    rp_block = body["roadmap_protocol"]
    assert rp_block["status"] in ("ok", "not_available")
    if rp_block["status"] == "ok":
        data = rp_block["data"]
        assert data["safe_to_execute"] is False
        assert data["executable"] is False
        assert "decision" in data
        assert "item_type" in data
        assert "implementation_allowed" in data
    else:
        assert "reason" in rp_block


def test_status_payload_includes_workloop_runtime_block(client) -> None:
    """v3.15.15.22: status payload now carries a workloop_runtime
    summary. When the artifact is missing the block reports
    not_available — the surface never silently OKs."""
    body = client.get("/api/agent-control/status").get_json()
    assert "workloop_runtime" in body
    rt = body["workloop_runtime"]
    assert rt["status"] in ("ok", "not_available")
    if rt["status"] == "not_available":
        assert "reason" in rt


def test_status_payload_includes_frozen_hashes(client) -> None:
    resp = client.get("/api/agent-control/status")
    body = resp.get_json()
    fh = body.get("frozen_hashes", {})
    assert fh.get("status") == "ok"
    data = fh.get("data", {})
    assert set(data.keys()) == set(ac.FROZEN_CONTRACTS)
    for v in data.values():
        assert isinstance(v, str)
        # Either a 64-char sha256 or the literal "missing".
        assert v == "missing" or (len(v) == 64 and all(c in "0123456789abcdef" for c in v))


# ---------------------------------------------------------------------------
# Secret-redaction guard
# ---------------------------------------------------------------------------


def test_payload_with_credential_string_is_refused(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a future regression slips a credential-shaped VALUE into a
    surfaced artifact, ``assert_no_secrets`` should raise inside
    ``_safe_jsonify`` — the surface refuses to leak rather than
    soften the rule.

    v3.15.15.25.1: switched from the path-shaped string
    ``config/config.yaml`` (which is now a legitimate path
    reference) to an Anthropic-key-shaped credential value. Path
    references are no longer rejected; only credential VALUES are.
    """
    p = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "report_kind": "github_pr_lifecycle_digest",
        "evil_field": "sk-ant-AAAAAAAA1234",
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ac, "PR_LIFECYCLE_LATEST", p)
    # Flask's default error handler returns 500 for unhandled
    # exceptions; the assertion fires inside the view, so the response
    # status is the test's signal.
    resp = client.get("/api/agent-control/pr-lifecycle")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_no_subprocess_imports_in_module() -> None:
    """The route module must not import ``subprocess`` directly. All
    data comes from in-process module calls + JSON file reads."""
    src = Path(ac.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    # Reject any obvious mutating tool spawn.
    forbidden = (
        '"gh"',
        "'gh'",
        "/usr/bin/gh",
        '"git"',
        "'git'",
        "/usr/bin/git",
        "Popen",
    )
    for token in forbidden:
        assert token not in src, f"forbidden token in api_agent_control.py: {token!r}"


# ---------------------------------------------------------------------------
# v3.15.16.9b — loop closure subsection tests
# ---------------------------------------------------------------------------


def _write_artifact(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def _hn_payload(
    *,
    events_total: int = 0,
    blocking_component: "str | None" = None,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    events = []
    if events_total > 0 and blocking_component:
        events.append(
            {
                "event_id": "h_aaaaaaaaaa",
                "reason": "governance_bootstrap_required",
                "blocking_component": blocking_component,
                "priority": "HIGH",
            }
        )
    return {
        "schema_version": 1,
        "report_kind": "human_needed_digest",
        "module_version": "v3.15.16.8",
        "generated_at_utc": generated_at_utc,
        "counts": {
            "events_total": events_total,
            "by_reason": {"governance_bootstrap_required": events_total},
        },
        "events": events,
    }


def _gb_payload(
    *,
    templates_total: int = 0,
    branch_name: "str | None" = None,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    templates = []
    if templates_total > 0 and branch_name:
        templates.append(
            {
                "template_id": "gb_aaaaaaaaaa",
                "branch_name": branch_name,
                "source_event_id": "h_aaaaaaaaaa",
            }
        )
    return {
        "schema_version": 1,
        "report_kind": "governance_bootstrap_digest",
        "module_version": "v3.15.16.9",
        "generated_at_utc": generated_at_utc,
        "counts": {"templates_total": templates_total},
        "templates": templates,
    }


def _ai_payload(
    *,
    items=None,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    """Approval-inbox digest fixture. Items live at TOP LEVEL of the
    digest (per ``reporting.approval_inbox.collect_snapshot`` line
    1047 — ``items: items``); they are NOT nested under a ``data``
    key. Matching the canonical schema is critical: the loop-closure
    summary reads ``digest['items']`` directly."""
    return {
        "schema_version": 1,
        "report_kind": "approval_inbox_digest",
        "module_version": "v3.15.15.20",
        "generated_at_utc": generated_at_utc,
        "items": items if items is not None else [],
    }


def _set_loop_closure_artifacts(
    tmp_path: Path,
    *,
    hn,
    gb,
    ai,
) -> None:
    if hn is not None:
        _write_artifact(tmp_path / "logs" / "human_needed" / "latest.json", hn)
    if gb is not None:
        _write_artifact(
            tmp_path / "logs" / "governance_bootstrap" / "latest.json", gb
        )
    if ai is not None:
        _write_artifact(tmp_path / "logs" / "approval_inbox" / "latest.json", ai)


def test_loop_closure_not_available_when_human_needed_missing(
    client, tmp_path: Path
) -> None:
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "not_available"
    assert "human_needed" in lc["reason"]


def test_loop_closure_not_available_when_governance_bootstrap_missing(
    client, tmp_path: Path
) -> None:
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_payload(), gb=None, ai=_ai_payload()
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "not_available"
    assert "governance_bootstrap" in lc["reason"]


def test_loop_closure_not_available_when_approval_inbox_missing(
    client, tmp_path: Path
) -> None:
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_payload(), gb=_gb_payload(), ai=None
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "not_available"
    assert "approval_inbox" in lc["reason"]


def test_loop_closure_open_with_top_blocking_component(
    client, tmp_path: Path
) -> None:
    """The canonical v3.15.16.5 wiring-gap case: human_needed has 1
    event, governance_bootstrap has 1 template, approval_inbox has
    1 derived row."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_payload(
            events_total=1,
            blocking_component="dashboard/dashboard.py:register_roadmap_priority_routes",
        ),
        gb=_gb_payload(
            templates_total=1,
            branch_name="governance-bootstrap/h_aaaaaaaaaa",
        ),
        ai=_ai_payload(
            items=[
                {"item_id": "i_xxx", "source": "human_needed:h_aaaaaaaaaa"},
                {"item_id": "i_yyy", "source": "recurring_maintenance:something"},
            ]
        ),
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "ok"
    data = lc["data"]
    assert data["loop_state"] == "open"
    assert data["human_needed"]["events_total"] == 1
    assert (
        data["human_needed"]["top_blocking_component"]
        == "dashboard/dashboard.py:register_roadmap_priority_routes"
    )
    assert data["governance_bootstrap"]["templates_total"] == 1
    assert (
        data["governance_bootstrap"]["top_branch_name"]
        == "governance-bootstrap/h_aaaaaaaaaa"
    )
    # Counts only rows whose source startswith human_needed: (the
    # canonical v3.15.16.8 emission); other sources do not count.
    assert data["approval_inbox"]["human_needed_derived_rows"] == 1
    assert data["last_refreshed_utc"] == "2026-05-05T13:00:00Z"


def test_loop_closure_resolved_when_all_zero_and_timestamps_within_window(
    client, tmp_path: Path
) -> None:
    """All three counts zero AND timestamps within consistency
    window -> resolved."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_payload(generated_at_utc="2026-05-05T13:00:01Z"),
        gb=_gb_payload(generated_at_utc="2026-05-05T13:00:30Z"),
        ai=_ai_payload(generated_at_utc="2026-05-05T13:00:45Z"),
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "ok"
    data = lc["data"]
    assert data["loop_state"] == "resolved"
    assert data["human_needed"]["events_total"] == 0
    assert data["human_needed"]["top_blocking_component"] is None
    assert data["governance_bootstrap"]["templates_total"] == 0
    assert data["governance_bootstrap"]["top_branch_name"] is None
    assert data["approval_inbox"]["human_needed_derived_rows"] == 0
    # last_refreshed_utc is the lexicographic max of the three.
    assert data["last_refreshed_utc"] == "2026-05-05T13:00:45Z"


def test_loop_closure_stale_when_timestamps_spread_beyond_window(
    client, tmp_path: Path
) -> None:
    """All three counts zero BUT one timestamp >10 min older than
    the others -> stale (digests inconsistent)."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_payload(generated_at_utc="2026-05-05T13:00:00Z"),
        gb=_gb_payload(generated_at_utc="2026-05-05T12:30:00Z"),  # 30 min older
        ai=_ai_payload(generated_at_utc="2026-05-05T13:00:30Z"),
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "ok"
    assert lc["data"]["loop_state"] == "stale"


def test_loop_closure_inbox_count_uses_canonical_source_prefix(
    client, tmp_path: Path
) -> None:
    """The human_needed_derived_rows count must use the canonical
    v3.15.16.8 source-field prefix human_needed: — not any other
    field, not a substring search elsewhere."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_payload(),
        gb=_gb_payload(),
        ai=_ai_payload(
            items=[
                {"item_id": "a", "source": "human_needed:h_111"},
                {"item_id": "b", "source": "human_needed:h_222"},
                {"item_id": "c", "source": "recurring_maintenance:foo"},
                {"item_id": "d", "source": "proposal_queue:bar"},
                # Non-string source is ignored, not crashed:
                {"item_id": "e", "source": None},
            ]
        ),
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "ok"
    # Two of five items match the canonical prefix.
    assert lc["data"]["approval_inbox"]["human_needed_derived_rows"] == 2


def test_loop_closure_payload_contains_no_unsafe_fields(
    client, tmp_path: Path
) -> None:
    """The bounded payload must NOT carry proposed_patch, pr_body,
    or full events / templates lists. Pinned defensively."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn={
            **_hn_payload(
                events_total=1,
                blocking_component="dashboard/dashboard.py:register_x_routes",
            ),
            "events": [
                {
                    "event_id": "h_a",
                    "reason": "governance_bootstrap_required",
                    "blocking_component": "dashboard/dashboard.py:register_x_routes",
                    "proposed_patch": "secret-shaped patch text NOT for the wire",
                    "priority": "HIGH",
                }
            ],
        },
        gb={
            **_gb_payload(
                templates_total=1, branch_name="governance-bootstrap/h_a"
            ),
            "templates": [
                {
                    "template_id": "gb_a",
                    "branch_name": "governance-bootstrap/h_a",
                    "source_event_id": "h_a",
                    "pr_body": "MARKER_SHOULD_NOT_APPEAR_ON_WIRE",
                    "file_diff": "MARKER_SHOULD_NOT_APPEAR_ON_WIRE",
                }
            ],
        },
        ai=_ai_payload(),
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "ok"
    text = json.dumps(lc)
    forbidden = (
        "proposed_patch",
        "pr_body",
        "file_diff",
        "MARKER_SHOULD_NOT_APPEAR_ON_WIRE",
        "secret-shaped patch text",
    )
    for tok in forbidden:
        assert tok not in text, (
            f"loop_closure payload leaks forbidden field/value: {tok!r}"
        )
    # Defensive: confirm the bounded keys and ONLY the bounded keys.
    data = lc["data"]
    assert set(data.keys()) == {
        "loop_state",
        "human_needed",
        "governance_bootstrap",
        "approval_inbox",
        "last_refreshed_utc",
    }
    assert set(data["human_needed"].keys()) == {
        "events_total",
        "by_reason",
        "top_blocking_component",
        "generated_at_utc",
    }
    assert set(data["governance_bootstrap"].keys()) == {
        "templates_total",
        "top_branch_name",
        "generated_at_utc",
    }
    assert set(data["approval_inbox"].keys()) == {
        "human_needed_derived_rows",
        "generated_at_utc",
    }


def test_loop_closure_not_available_on_missing_generated_at_utc(
    client, tmp_path: Path
) -> None:
    """If any artifact lacks generated_at_utc, the surface returns
    not_available rather than rendering a meaningless timestamp."""
    bad_hn = _hn_payload()
    del bad_hn["generated_at_utc"]
    _set_loop_closure_artifacts(
        tmp_path, hn=bad_hn, gb=_gb_payload(), ai=_ai_payload()
    )
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "not_available"
    assert "generated_at_utc" in lc["reason"]


# ---------------------------------------------------------------------------
# v3.15.16.9c — canonical bootstrap event surfacing
# ---------------------------------------------------------------------------


_CANON_COMPONENT = "dashboard/dashboard.py:register_roadmap_priority_routes"
_CANON_REASON = "governance_bootstrap_required"


def _hn_canon(
    *,
    event_id: "str | None" = "h_044e7e64e",
    extra_events: "list | None" = None,
    matching_blocking_component: str = _CANON_COMPONENT,
    matching_reason: str = _CANON_REASON,
    include_match: bool = True,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    """human_needed digest with one matching canonical event plus
    optional extra (unrelated) events. Used by v3.15.16.9c tests."""
    events: list = []
    if include_match:
        ev: dict[str, Any] = {
            "reason": matching_reason,
            "blocking_component": matching_blocking_component,
            "priority": "HIGH",
        }
        if event_id is not None:
            ev["event_id"] = event_id
        events.append(ev)
    if extra_events:
        events.extend(extra_events)
    return {
        "schema_version": 1,
        "report_kind": "human_needed_digest",
        "module_version": "v3.15.16.8",
        "generated_at_utc": generated_at_utc,
        "counts": {
            "events_total": len(events),
            "by_reason": {_CANON_REASON: 1 if include_match else 0},
        },
        "events": events,
    }


def _gb_canon(
    *,
    event_id: str = "h_044e7e64e",
    branch_name: str = "governance-bootstrap/h_044e7e64e",
    extra_templates: "list | None" = None,
    include_match: bool = True,
    matching_blocking_component: str = _CANON_COMPONENT,
    matching_reason: str = _CANON_REASON,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    """governance_bootstrap digest with one matching canonical
    template (using the *full* canonical schema: source_event_id,
    source_reason, evidence.blocking_component) plus optional extras."""
    templates: list = []
    if include_match:
        templates.append(
            {
                "template_id": "gb_044e7e64e",
                "source_event_id": event_id,
                "source_reason": matching_reason,
                "branch_name": branch_name,
                "evidence": {
                    "blocking_component": matching_blocking_component,
                    "impact": "HIGH",
                    "priority": "HIGH",
                    "related_item": None,
                },
            }
        )
    if extra_templates:
        templates.extend(extra_templates)
    return {
        "schema_version": 1,
        "report_kind": "governance_bootstrap_digest",
        "module_version": "v3.15.16.9",
        "generated_at_utc": generated_at_utc,
        "counts": {"templates_total": len(templates)},
        "templates": templates,
    }


def _ai_canon(
    *,
    event_id: str = "h_044e7e64e",
    include_match: bool = True,
    extra_items: "list | None" = None,
    generated_at_utc: str = "2026-05-05T13:00:00Z",
) -> dict:
    items: list = []
    if include_match:
        items.append(
            {"item_id": "i_canon", "source": f"human_needed:{event_id}"}
        )
    if extra_items:
        items.extend(extra_items)
    return {
        "schema_version": 1,
        "report_kind": "approval_inbox_digest",
        "module_version": "v3.15.15.20",
        "generated_at_utc": generated_at_utc,
        "items": items,
    }


# --- open state ---


def test_rpw_open_when_event_matches_both_literals(client, tmp_path: Path) -> None:
    """Canonical pre-bootstrap state: matching event + matching
    template + matching inbox row → state=open with all literals."""
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_canon(), gb=_gb_canon(), ai=_ai_canon()
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "open"
    assert rpw["reason"] is None
    assert rpw["event_id"] == "h_044e7e64e"
    assert rpw["blocking_component"] == _CANON_COMPONENT
    assert rpw["source_reason"] == _CANON_REASON
    assert rpw["template_branch"] == "governance-bootstrap/h_044e7e64e"
    assert rpw["inbox_row_present"] is True


def test_rpw_open_template_branch_resolved_by_source_event_id_PRIMARY(
    client, tmp_path: Path
) -> None:
    """Template match is PRIMARY on (source_event_id, source_reason).
    A template whose source_event_id matches the chosen event_id
    populates template_branch, regardless of evidence shape."""
    # Two templates: one with the canonical pair (matches), one
    # with the canonical reason but a different event_id (does NOT
    # match). Helper must pick the PRIMARY (event_id) match.
    extra = [
        {
            "template_id": "gb_other",
            "source_event_id": "h_other",
            "source_reason": _CANON_REASON,
            "branch_name": "governance-bootstrap/h_other",
            "evidence": {"blocking_component": _CANON_COMPONENT},
        }
    ]
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(),
        gb=_gb_canon(extra_templates=extra),
        ai=_ai_canon(),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "open"
    assert rpw["template_branch"] == "governance-bootstrap/h_044e7e64e"


def test_rpw_open_inbox_row_present_via_exact_source_equality(
    client, tmp_path: Path
) -> None:
    """inbox_row_present is True ONLY when an item has
    source == "human_needed:<event_id>" exactly. Substring matches
    or near-misses must NOT count."""
    near_miss_items = [
        {
            "item_id": "i_substr",
            "source": "human_needed:h_044e7e64e_extra",
        },  # near-miss: superstring
        {
            "item_id": "i_other_prefix",
            "source": "recurring_maintenance:h_044e7e64e",
        },  # near-miss: different prefix
        {
            "item_id": "i_blocking_substr",
            "source": "manual:dashboard/dashboard.py:register_roadmap_priority_routes",
        },  # near-miss: blocking_component embedded but not the canonical source format
    ]
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(),
        gb=_gb_canon(),
        ai=_ai_canon(include_match=False, extra_items=near_miss_items),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "open"
    assert rpw["inbox_row_present"] is False


def test_rpw_open_picks_lex_smallest_event_id_deterministically(
    client, tmp_path: Path
) -> None:
    """When several human_needed events match the canonical pair,
    the lex-smallest event_id is chosen for the open report."""
    extra_events = [
        {
            "event_id": "h_zzzzzzzzzz",
            "reason": _CANON_REASON,
            "blocking_component": _CANON_COMPONENT,
            "priority": "HIGH",
        },
        {
            "event_id": "h_000000000a",  # smallest
            "reason": _CANON_REASON,
            "blocking_component": _CANON_COMPONENT,
            "priority": "HIGH",
        },
    ]
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(extra_events=extra_events),
        gb=_gb_canon(),
        ai=_ai_canon(),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "open"
    assert rpw["event_id"] == "h_000000000a"


# --- resolved state ---


def test_rpw_resolved_when_all_three_artifacts_clear_of_canonical(
    client, tmp_path: Path
) -> None:
    """Resolved requires the *full triple* cleared. With no matching
    event, no matching template, and no matching inbox row, state is
    resolved — even though counts are non-zero (unrelated work)."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(include_match=False),
        gb=_gb_canon(include_match=False),
        ai=_ai_canon(include_match=False),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "resolved"
    assert rpw["reason"] is None
    assert rpw["event_id"] is None
    assert rpw["blocking_component"] is None
    assert rpw["source_reason"] is None
    assert rpw["template_branch"] is None
    assert rpw["inbox_row_present"] is False


def test_rpw_resolved_ignores_unrelated_events_and_unrelated_inbox_rows(
    client, tmp_path: Path
) -> None:
    """The resolved decision is *non-aggregate*. Unrelated
    human_needed events, unrelated governance_bootstrap templates,
    and unrelated approval_inbox rows persist — yet the canonical
    triple is cleared, so state=resolved."""
    unrelated_events = [
        {
            "event_id": "h_unrelated1",
            "reason": _CANON_REASON,
            "blocking_component": "dashboard/dashboard.py:register_other_routes",
            "priority": "HIGH",
        },
        {
            "event_id": "h_unrelated2",
            "reason": "decision_unclear",
            "blocking_component": _CANON_COMPONENT,  # canonical comp + non-canonical reason
            "priority": "MEDIUM",
        },
    ]
    unrelated_templates = [
        {
            "template_id": "gb_other",
            "source_event_id": "h_unrelated1",
            "source_reason": _CANON_REASON,
            "branch_name": "governance-bootstrap/h_unrelated1",
            "evidence": {
                "blocking_component": "dashboard/dashboard.py:register_other_routes",
            },
        }
    ]
    unrelated_items = [
        {"item_id": "i_un1", "source": "human_needed:h_unrelated1"},
        {"item_id": "i_un2", "source": "recurring_maintenance:foo"},
    ]
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(include_match=False, extra_events=unrelated_events),
        gb=_gb_canon(include_match=False, extra_templates=unrelated_templates),
        ai=_ai_canon(include_match=False, extra_items=unrelated_items),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "resolved"
    # Aggregate loop_state may still be open because counts are non-zero —
    # the rpw subsection is independent of that signal.
    aggregate_loop_state = body["loop_closure"]["data"]["loop_state"]
    assert aggregate_loop_state == "open"


# --- not_available state ---


def test_rpw_not_available_human_needed_missing(
    client, tmp_path: Path
) -> None:
    """Artifact missing → not_available + closed reason."""
    _set_loop_closure_artifacts(
        tmp_path, hn=None, gb=_gb_canon(), ai=_ai_canon()
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "human_needed_missing"


def test_rpw_not_available_human_needed_malformed(
    client, tmp_path: Path
) -> None:
    """events not a list → human_needed_malformed."""
    bad = _hn_canon()
    bad["events"] = {"this": "is not a list"}
    _set_loop_closure_artifacts(tmp_path, hn=bad, gb=_gb_canon(), ai=_ai_canon())
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "human_needed_malformed"


def test_rpw_not_available_governance_bootstrap_missing(
    client, tmp_path: Path
) -> None:
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_canon(), gb=None, ai=_ai_canon()
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "governance_bootstrap_missing"


def test_rpw_not_available_governance_bootstrap_malformed(
    client, tmp_path: Path
) -> None:
    bad = _gb_canon()
    bad["templates"] = "not a list"
    _set_loop_closure_artifacts(tmp_path, hn=_hn_canon(), gb=bad, ai=_ai_canon())
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "governance_bootstrap_malformed"


def test_rpw_not_available_approval_inbox_missing(
    client, tmp_path: Path
) -> None:
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_canon(), gb=_gb_canon(), ai=None
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "approval_inbox_missing"


def test_rpw_not_available_approval_inbox_malformed(
    client, tmp_path: Path
) -> None:
    bad = _ai_canon()
    bad["items"] = 12345  # int, not a list
    _set_loop_closure_artifacts(tmp_path, hn=_hn_canon(), gb=_gb_canon(), ai=bad)
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "approval_inbox_malformed"


def test_rpw_not_available_event_id_missing(client, tmp_path: Path) -> None:
    """Matching event with empty event_id → event_id_missing.
    Matching is observed (so not 'resolved') but cannot be derived
    deterministically (so not 'open')."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(event_id=None),  # event present but missing event_id field
        gb=_gb_canon(),
        ai=_ai_canon(),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "event_id_missing"


def test_rpw_not_available_governance_bootstrap_lags_human_needed(
    client, tmp_path: Path
) -> None:
    """Mid-refresh inconsistency: gb has matching template but hn
    does not. Closed reason captures this exact case."""
    _set_loop_closure_artifacts(
        tmp_path,
        hn=_hn_canon(include_match=False),
        gb=_gb_canon(),  # still has the canonical template
        ai=_ai_canon(),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "governance_bootstrap_lags_human_needed"


# --- closed-vocabulary, schema and no-leak guards ---


def test_rpw_closed_reason_vocabulary_pinned() -> None:
    """The closed reason vocabulary is pinned; any addition is a
    deliberate API change requiring a new release."""
    expected = {
        "human_needed_missing",
        "human_needed_malformed",
        "governance_bootstrap_missing",
        "governance_bootstrap_malformed",
        "approval_inbox_missing",
        "approval_inbox_malformed",
        "event_id_missing",
        "governance_bootstrap_lags_human_needed",
    }
    assert set(ac.ROADMAP_PRIORITY_WIRING_NOT_AVAILABLE_REASONS) == expected


def test_rpw_canonical_literals_are_frozen() -> None:
    """Source-text invariant: the two canonical literals are pinned.
    A drift breaks the open→resolved proof for the operator."""
    src = (REPO_ROOT / "dashboard" / "api_agent_control.py").read_text(
        encoding="utf-8"
    )
    assert (
        'ROADMAP_PRIORITY_WIRING_COMPONENT: str = (\n'
        '    "dashboard/dashboard.py:register_roadmap_priority_routes"\n'
        ")"
    ) in src
    assert (
        'ROADMAP_PRIORITY_WIRING_REASON: str = "governance_bootstrap_required"'
        in src
    )


def test_rpw_governance_bootstrap_template_schema_pinned() -> None:
    """The fields the helper consumes (source_event_id, source_reason,
    branch_name, evidence.blocking_component) MUST exist in the
    governance_bootstrap module's template builder. If that schema
    drifts, this test fails before the live wire silently misclassifies."""
    src = (REPO_ROOT / "reporting" / "governance_bootstrap.py").read_text(
        encoding="utf-8"
    )
    # Top-level keys.
    assert '"source_event_id"' in src
    assert '"source_reason"' in src
    assert '"branch_name"' in src
    # Nested key.
    assert '"blocking_component"' in src


def test_rpw_payload_keys_are_bounded(client, tmp_path: Path) -> None:
    """The roadmap_priority_wiring payload exposes ONLY the seven
    bounded keys. No extra fields, no proposed_patch, no pr_body."""
    _set_loop_closure_artifacts(
        tmp_path, hn=_hn_canon(), gb=_gb_canon(), ai=_ai_canon()
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert set(rpw.keys()) == {
        "state",
        "reason",
        "event_id",
        "blocking_component",
        "source_reason",
        "template_branch",
        "inbox_row_present",
    }


def test_rpw_no_proposed_patch_or_pr_body_or_diff_leak(
    client, tmp_path: Path
) -> None:
    """Defensive: feed templates / events with leak-shaped fields and
    confirm none of them appear in the rendered payload."""
    leaky_events = [
        {
            "event_id": "h_044e7e64e",
            "reason": _CANON_REASON,
            "blocking_component": _CANON_COMPONENT,
            "proposed_patch": "MARKER_LEAK_PATCH",
            "priority": "HIGH",
        }
    ]
    leaky_templates = [
        {
            "template_id": "gb_044e7e64e",
            "source_event_id": "h_044e7e64e",
            "source_reason": _CANON_REASON,
            "branch_name": "governance-bootstrap/h_044e7e64e",
            "pr_body": "MARKER_LEAK_PR_BODY",
            "file_diff": "MARKER_LEAK_FILE_DIFF",
            "commit_message": "MARKER_LEAK_COMMIT",
            "evidence": {"blocking_component": _CANON_COMPONENT},
        }
    ]
    _set_loop_closure_artifacts(
        tmp_path,
        hn={
            "schema_version": 1,
            "module_version": "v3.15.16.8",
            "generated_at_utc": "2026-05-05T13:00:00Z",
            "counts": {"events_total": 1, "by_reason": {_CANON_REASON: 1}},
            "events": leaky_events,
        },
        gb={
            "schema_version": 1,
            "module_version": "v3.15.16.9",
            "generated_at_utc": "2026-05-05T13:00:00Z",
            "counts": {"templates_total": 1},
            "templates": leaky_templates,
        },
        ai=_ai_canon(),
    )
    body = client.get("/api/agent-control/status").get_json()
    rpw = body["loop_closure"]["roadmap_priority_wiring"]
    assert rpw["state"] == "open"
    text = json.dumps(rpw)
    for marker in (
        "MARKER_LEAK_PATCH",
        "MARKER_LEAK_PR_BODY",
        "MARKER_LEAK_FILE_DIFF",
        "MARKER_LEAK_COMMIT",
        "proposed_patch",
        "pr_body",
        "file_diff",
        "commit_message",
    ):
        assert marker not in text, (
            f"roadmap_priority_wiring leaks forbidden token: {marker!r}"
        )


def test_rpw_present_at_envelope_level_on_not_available_loop_closure(
    client, tmp_path: Path
) -> None:
    """When the aggregate loop_closure is itself not_available
    (e.g. an artifact is missing), the rpw subsection still rides
    at the envelope level so the operator can see the canonical
    reason."""
    _set_loop_closure_artifacts(tmp_path, hn=None, gb=None, ai=None)
    body = client.get("/api/agent-control/status").get_json()
    lc = body["loop_closure"]
    assert lc["status"] == "not_available"
    rpw = lc["roadmap_priority_wiring"]
    assert rpw["state"] == "not_available"
    assert rpw["reason"] == "human_needed_missing"
