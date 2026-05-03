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
    """If a future regression slips a credential-shaped string into a
    surfaced artifact, ``assert_no_secrets`` should raise inside
    ``_safe_jsonify`` — the surface refuses to leak rather than
    soften the rule."""
    p = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    # Include a sensitive-path fragment in a string field.
    payload = {
        "schema_version": 1,
        "report_kind": "github_pr_lifecycle_digest",
        "evil_field": "config/config.yaml",
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
