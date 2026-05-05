"""Unit tests for ``dashboard.api_roadmap_priority`` (v3.15.16.5).

Verifies the same hard guarantees as the sibling agent-control
route modules:

* GET only (POST/PUT/PATCH/DELETE return 405).
* Missing artifact → ``not_available``.
* Malformed artifact → ``not_available``.
* Non-object artifact → ``not_available``.
* Valid artifact passes through with the bounded projection.
* ``safe_to_execute`` is always ``False`` in the response payload,
  regardless of what the underlying digest contains (defensive
  redaction at the boundary).
* ``needs_human`` is derived deterministically.
* The chosen_next_up payload is bounded to the documented allowlist
  of fields; unknown fields in the underlying digest are dropped.
* Secret-redaction guard refuses leaks.
* No subprocess / no ``gh`` / no ``git`` token in the module source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from dashboard import api_roadmap_priority as ac

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Flask:
    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac,
        "ROADMAP_PRIORITY_LATEST",
        tmp_path / "logs" / "roadmap_priority" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_roadmap_priority_routes(flask_app)
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


_PATH = "/api/agent-control/next-up"


# ---------------------------------------------------------------------------
# Verb / route invariants
# ---------------------------------------------------------------------------


def test_get_returns_200(client) -> None:
    resp = client.get(_PATH)
    assert resp.status_code == 200
    assert resp.is_json


@pytest.mark.parametrize("verb", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_verbs_are_rejected(client, verb: str) -> None:
    resp = client.open(_PATH, method=verb)
    assert resp.status_code == 405


def test_only_next_up_route_registered(app: Flask) -> None:
    rules = [
        r for r in app.url_map.iter_rules() if r.rule.startswith("/api/agent-control/")
    ]
    paths = sorted(r.rule for r in rules)
    assert paths == [_PATH]
    for r in rules:
        verbs = set(r.methods or ()) - {"HEAD", "OPTIONS"}
        assert verbs == {"GET"}


# ---------------------------------------------------------------------------
# not_available envelopes
# ---------------------------------------------------------------------------


def test_missing_artifact_yields_not_available(client) -> None:
    body = client.get(_PATH).get_json()
    assert body["kind"] == "agent_control_next_up"
    assert body["schema_version"] == 1
    assert body["status"] == "not_available"
    assert body["reason"] == "missing"
    assert body["artifact_path"] == "logs/roadmap_priority/latest.json"


def test_malformed_artifact_yields_not_available(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "not_available"
    assert body["reason"].startswith("malformed:")


def test_non_object_artifact_yields_not_available(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "not_available"
    assert "not_an_object" in body["reason"]


# ---------------------------------------------------------------------------
# Valid artifact projection
# ---------------------------------------------------------------------------


def _write_artifact(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def test_valid_ready_artifact_projects_chosen_next_up(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "report_kind": "roadmap_priority_digest",
            "module_version": "v3.15.16.2",
            "generated_at_utc": "2026-05-05T08:00:00Z",
            "final_recommendation": "ready_for_implementation",
            "safe_to_execute": False,
            "chosen_next_up": {
                "proposal_id": "p_aaaaaaaa",
                "title": "test",
                "summary": "summary",
                "proposal_type": "observability_addition",
                "risk_class": "LOW",
                "rationale": "lowest-rank eligible candidate",
                "protocol_plan_summary": {
                    "decision": "allowed_read_only",
                    "implementation_allowed": True,
                    "requires_human": False,
                    "risk_class": "LOW",
                    "item_type": "observability_addition",
                    "proposed_branch": "fix/test",
                    "proposed_release_id": "v3.15.16.x",
                    "required_tests": ["scripts/governance_lint.py"],
                    "expected_artifacts": ["docs/governance/x.md"],
                    "rollback_plan": ["git revert"],
                },
            },
            "candidates": [{"proposal_id": "p_aaaaaaaa", "rank": 1}],
            "filtered_out": [{"proposal_id": "p_zz", "filter_reason": "risk_high_excluded"}],
            "counts": {
                "proposals_total": 10,
                "eligible_total": 1,
                "filtered_out_total": 9,
                "filtered_out_by_reason": {"risk_high_excluded": 9},
            },
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["final_recommendation"] == "ready_for_implementation"
    assert data["safe_to_execute"] is False
    assert data["needs_human"] is False
    chosen = data["chosen_next_up"]
    assert chosen["proposal_id"] == "p_aaaaaaaa"
    assert chosen["title"] == "test"
    plan = chosen["protocol_plan_summary"]
    assert plan["decision"] == "allowed_read_only"
    assert plan["implementation_allowed"] is True
    assert plan["proposed_branch"] == "fix/test"
    # The full candidates / filtered_out arrays are NOT projected.
    assert "candidates" not in data
    assert "filtered_out" not in data
    assert data["counts"]["proposals_total"] == 10
    assert data["counts"]["eligible_total"] == 1


def test_nothing_ready_artifact_projects_null_chosen(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "report_kind": "roadmap_priority_digest",
            "module_version": "v3.15.16.2",
            "final_recommendation": "nothing_ready",
            "safe_to_execute": False,
            "chosen_next_up": None,
            "counts": {
                "proposals_total": 12,
                "eligible_total": 0,
                "filtered_out_total": 12,
                "filtered_out_by_reason": {"status_not_proposed": 12},
            },
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["status"] == "ok"
    assert body["data"]["chosen_next_up"] is None
    assert body["data"]["needs_human"] is False
    assert body["data"]["final_recommendation"] == "nothing_ready"


# ---------------------------------------------------------------------------
# safe_to_execute hard-coded false
# ---------------------------------------------------------------------------


def test_safe_to_execute_in_payload_is_always_false(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if a corrupted upstream digest claims ``safe_to_execute:
    true`` (which the prioritizer pin forbids — but defense in depth
    matters), the boundary projection must not propagate that
    value. We hard-code False on the way out."""
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "module_version": "v3.15.16.2",
            "final_recommendation": "ready_for_implementation",
            "safe_to_execute": True,  # corrupted upstream
            "chosen_next_up": {
                "proposal_id": "p_aaaaaaaa",
                "title": "x",
                "protocol_plan_summary": {
                    "decision": "allowed_read_only",
                    "implementation_allowed": True,
                    "requires_human": False,
                },
            },
            "counts": {},
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["data"]["safe_to_execute"] is False


# ---------------------------------------------------------------------------
# needs_human derivation
# ---------------------------------------------------------------------------


def test_needs_human_true_when_protocol_requires_human(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "module_version": "v3.15.16.2",
            "final_recommendation": "ready_for_implementation",
            "chosen_next_up": {
                "proposal_id": "p_aaaaaaaa",
                "title": "x",
                "protocol_plan_summary": {
                    "decision": "allowed_read_only",
                    "implementation_allowed": True,
                    "requires_human": True,
                },
            },
            "counts": {},
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["data"]["needs_human"] is True


def test_needs_human_true_when_final_recommendation_unsafe(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "module_version": "v3.15.16.2",
            "final_recommendation": "unsafe",
            "chosen_next_up": None,
            "counts": {},
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    body = client.get(_PATH).get_json()
    assert body["data"]["needs_human"] is True


# ---------------------------------------------------------------------------
# Secrets-redaction guard
# ---------------------------------------------------------------------------


def test_unknown_top_level_fields_are_not_projected(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary copies a bounded allowlist of fields from the
    underlying digest. Unknown top-level fields — including
    accidentally-credential-shaped ones — are dropped at the
    boundary and never reach assert_no_secrets, which is the
    strongest possible posture (defence-in-depth: even if a future
    upstream digest grows a new field, it cannot leak through this
    surface without an explicit code change here)."""
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "module_version": "v3.15.16.2",
            "final_recommendation": "ready_for_implementation",
            "evil_field": "sk-ant-AAAAAAAA1234",
            "chosen_next_up": None,
            "counts": {},
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    resp = client.get(_PATH)
    assert resp.status_code == 200
    body = resp.get_json()
    # The credential-shaped value never appears in the response.
    assert "evil_field" not in body
    assert "evil_field" not in (body.get("data") or {})
    text = resp.get_data(as_text=True)
    assert "sk-ant-" not in text


def test_credential_in_projected_field_is_refused(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a credential-shaped value DOES land in a field the
    boundary projects (e.g. via a malicious proposal title),
    assert_no_secrets must trip and the request must fail loudly
    rather than leak."""
    p = tmp_path / "logs" / "roadmap_priority" / "latest.json"
    _write_artifact(
        p,
        {
            "schema_version": 1,
            "module_version": "v3.15.16.2",
            "final_recommendation": "ready_for_implementation",
            "chosen_next_up": {
                "proposal_id": "p_aaaaaaaa",
                # Title is in the bounded projection allowlist —
                # planting a credential here forces the value
                # through the assert_no_secrets boundary.
                "title": "sk-ant-AAAAAAAA1234",
                "protocol_plan_summary": {
                    "decision": "allowed_read_only",
                    "implementation_allowed": True,
                    "requires_human": False,
                },
            },
            "counts": {},
        },
    )
    monkeypatch.setattr(ac, "ROADMAP_PRIORITY_LATEST", p)
    resp = client.get(_PATH)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Module-source guarantees
# ---------------------------------------------------------------------------


def test_no_subprocess_imports_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(ac.__file__).read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for token in forbidden:
        assert token not in src, f"forbidden token: {token!r}"


def test_no_mutation_verb_in_module() -> None:
    """The module declares only methods=['GET']. No mutation verb
    string may appear anywhere in the source."""
    src = Path(ac.__file__).read_text(encoding="utf-8")
    forbidden = (
        '"POST"', "'POST'",
        '"PUT"', "'PUT'",
        '"PATCH"', "'PATCH'",
        '"DELETE"', "'DELETE'",
    )
    for token in forbidden:
        assert token not in src, f"forbidden mutation verb literal: {token!r}"
