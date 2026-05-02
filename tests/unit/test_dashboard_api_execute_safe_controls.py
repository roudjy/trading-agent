"""Unit tests for ``dashboard.api_execute_safe_controls``.

GET only. No POST. Catalog passthrough goes via in-process call;
no subprocess, no gh, no git tokens in the route module source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from dashboard import api_execute_safe_controls as ac

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_PATH = "/api/agent-control/execute-safe"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Flask:
    flask_app = Flask(__name__)
    ac.register_execute_safe_routes(flask_app)
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


def test_get_returns_200(client) -> None:
    resp = client.get(_PATH)
    assert resp.status_code == 200
    assert resp.is_json


@pytest.mark.parametrize("verb", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_verbs_are_rejected(client, verb: str) -> None:
    resp = client.open(_PATH, method=verb)
    assert resp.status_code == 405


def test_only_one_route_registered(app: Flask) -> None:
    rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/api/agent-control/")]
    paths = sorted(r.rule for r in rules)
    assert paths == [_PATH]
    for r in rules:
        verbs = set(r.methods or ()) - {"HEAD", "OPTIONS"}
        assert verbs == {"GET"}


def test_payload_carries_catalog_shape(client) -> None:
    body = client.get(_PATH).get_json()
    assert body["kind"] == "agent_control_execute_safe"
    assert body["status"] in ("ok", "not_available")
    if body["status"] == "ok":
        data = body["data"]
        assert data["report_kind"] == "execute_safe_controls_catalog"
        assert "actions" in data and isinstance(data["actions"], list)
        # All four whitelisted action types appear in the catalog.
        types = {a["action_type"] for a in data["actions"]}
        assert types == {
            "refresh_github_pr_lifecycle_dry_run",
            "refresh_proposal_queue_dry_run",
            "refresh_approval_inbox_dry_run",
            "run_dependabot_execute_safe_low_medium",
        }


def test_no_subprocess_or_gh_or_git_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for token in forbidden:
        assert token not in src, f"forbidden token: {token!r}"
