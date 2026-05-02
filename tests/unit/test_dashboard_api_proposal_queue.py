"""Unit tests for ``dashboard.api_proposal_queue``.

Verifies the same hard guarantees as ``api_agent_control``:

* GET only (POST/PUT/PATCH/DELETE return 405).
* Missing artifact → ``not_available``.
* Malformed artifact → ``not_available``.
* Non-object artifact → ``not_available``.
* Valid artifact passes through.
* Secret-redaction guard refuses leaks.
* No subprocess / no ``gh`` / no ``git`` token in the module source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from dashboard import api_proposal_queue as ac

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Flask:
    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac,
        "PROPOSAL_QUEUE_LATEST",
        tmp_path / "logs" / "proposal_queue" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_proposal_queue_routes(flask_app)
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


_PATH = "/api/agent-control/proposals"


def test_get_returns_200(client) -> None:
    resp = client.get(_PATH)
    assert resp.status_code == 200
    assert resp.is_json


@pytest.mark.parametrize("verb", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_verbs_are_rejected(client, verb: str) -> None:
    resp = client.open(_PATH, method=verb)
    assert resp.status_code == 405


def test_only_proposals_route_registered(app: Flask) -> None:
    rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/api/agent-control/")]
    paths = sorted(r.rule for r in rules)
    assert paths == [_PATH]
    for r in rules:
        verbs = set(r.methods or ()) - {"HEAD", "OPTIONS"}
        assert verbs == {"GET"}


def test_missing_artifact_yields_not_available(client) -> None:
    body = client.get(_PATH).get_json()
    assert body["status"] == "not_available"
    assert body["reason"] == "missing"
    assert body["artifact_path"] == "logs/proposal_queue/latest.json"


def test_malformed_artifact_yields_not_available(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "proposal_queue" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(ac, "PROPOSAL_QUEUE_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "not_available"
    assert body["reason"].startswith("malformed:")


def test_non_object_artifact_yields_not_available(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "proposal_queue" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(ac, "PROPOSAL_QUEUE_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "not_available"
    assert "not_an_object" in body["reason"]


def test_valid_artifact_passes_through(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "proposal_queue" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "report_kind": "proposal_queue_digest",
        "module_version": "v3.15.15.19",
        "proposals": [],
        "final_recommendation": "no_proposals",
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ac, "PROPOSAL_QUEUE_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "ok"
    assert body["data"]["final_recommendation"] == "no_proposals"


def test_credential_string_in_artifact_is_refused(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "proposal_queue" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "report_kind": "proposal_queue_digest",
        "evil_field": "config/config.yaml",
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ac, "PROPOSAL_QUEUE_LATEST", p)
    resp = client.get(_PATH)
    assert resp.status_code == 500


def test_no_subprocess_imports_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for token in forbidden:
        assert token not in src, f"forbidden token: {token!r}"
