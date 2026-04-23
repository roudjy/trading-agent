"""Unit tests for the v3.12 Flask read-only registry endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import dashboard as dashboard_mod


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client()


@pytest.fixture
def authed_client(client):
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "joery"
    return client


def _write_registry_v2(dir_: Path) -> None:
    payload = {
        "schema_version": "2.0",
        "status_model_version": "v3.12.0",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "run_id": "test_run",
        "git_revision": "abc",
        "summary": {"total": 0, "by_lifecycle_status": {}, "by_processing_state": {}},
        "entries": [],
    }
    (dir_ / "research" / "candidate_registry_latest.v2.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _write_status_history(dir_: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "status_model_version": "v3.12.0",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "history": {},
    }
    (dir_ / "research" / "candidate_status_history_latest.v1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_registry_v2_requires_auth(client):
    resp = client.get("/api/registry/v2")
    assert resp.status_code == 401


def test_status_history_requires_auth(client):
    resp = client.get("/api/registry/status-history")
    assert resp.status_code == 401


def test_registry_v2_returns_missing_state_when_absent(authed_client, tmp_path: Path):
    resp = authed_client.get("/api/registry/v2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
    assert data["entries"] == []


def test_status_history_returns_missing_state_when_absent(authed_client):
    resp = authed_client.get("/api/registry/status-history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
    assert data["history"] == {}


def test_registry_v2_serves_payload_when_present(authed_client, tmp_path: Path):
    _write_registry_v2(tmp_path)
    resp = authed_client.get("/api/registry/v2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "2.0"
    assert data["status_model_version"] == "v3.12.0"


def test_status_history_serves_payload_when_present(authed_client, tmp_path: Path):
    _write_status_history(tmp_path)
    resp = authed_client.get("/api/registry/status-history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "1.0"
    assert data["history"] == {}


def test_existing_candidates_endpoint_still_works(authed_client, tmp_path: Path):
    """Regression: the existing /api/candidates/latest endpoint is untouched."""
    resp = authed_client.get("/api/candidates/latest")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
