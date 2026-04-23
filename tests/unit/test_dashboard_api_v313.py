"""Unit tests for the v3.13 /api/registry/regime endpoint."""

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


def _write_regime_intelligence(dir_: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "classifier_version": "v0.1",
        "regime_layer_version": "v0.1",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "run_id": "test_run",
        "git_revision": "abc",
        "summary": {
            "candidates_total": 0,
            "candidates_with_sufficient_evidence": 0,
            "regime_axes": ["trend", "vol", "width"],
            "gate_rule_ids": ["trend_only", "trend_low_vol", "trend_expansion"],
        },
        "entries": [],
    }
    (dir_ / "research" / "regime_intelligence_latest.v1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_regime_endpoint_requires_auth(client):
    resp = client.get("/api/registry/regime")
    assert resp.status_code == 401


def test_regime_endpoint_returns_stable_missing_state(authed_client):
    resp = authed_client.get("/api/registry/regime")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
    assert data["schema_version"] == "1.0"
    assert data["classifier_version"] is None
    assert data["generated_at_utc"] is None
    assert data["entries"] == []


def test_regime_endpoint_serves_payload_when_present(authed_client, tmp_path: Path):
    _write_regime_intelligence(tmp_path)
    resp = authed_client.get("/api/registry/regime")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "1.0"
    assert data["classifier_version"] == "v0.1"
    assert data["summary"]["gate_rule_ids"] == [
        "trend_only",
        "trend_low_vol",
        "trend_expansion",
    ]
