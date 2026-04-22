"""Unit tests for the v3.10 Flask control-surface additions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import dashboard as dashboard_mod


@pytest.fixture
def client():
    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client()


@pytest.fixture
def authed_client(client):
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "joery"
    return client


def test_health_is_unauth_and_reports_version(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["version"] == Path("VERSION").read_text(encoding="utf-8").strip()
    assert "scheduler_next_fire_utc" in data


def test_presets_requires_auth(client):
    resp = client.get("/api/presets")
    assert resp.status_code == 401


def test_presets_authed_returns_four_presets(authed_client):
    resp = authed_client.get("/api/presets")
    assert resp.status_code == 200
    data = resp.get_json()
    names = [card["name"] for card in data["presets"]]
    assert names == [
        "trend_equities_4h_baseline",
        "pairs_equities_daily_baseline",
        "trend_regime_filtered_equities_4h",
        "crypto_diagnostic_1h",
    ]


def test_preset_card_shape_for_ui(authed_client):
    resp = authed_client.get("/api/presets")
    cards = {c["name"]: c for c in resp.get_json()["presets"]}
    pairs = cards["pairs_equities_daily_baseline"]
    assert pairs["enabled"] is False
    assert pairs["status"] == "planned"
    assert pairs["backlog_reason"] is not None
    crypto = cards["crypto_diagnostic_1h"]
    assert crypto["diagnostic_only"] is True
    assert crypto["excluded_from_daily_scheduler"] is True
    assert crypto["excluded_from_candidate_promotion"] is True


def test_session_login_rejects_wrong_credentials(client):
    resp = client.post("/api/session/login",
                       json={"username": "joery", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json() == {"ok": False, "error": "invalid credentials"}


def test_session_logout_clears_session(authed_client):
    resp = authed_client.post("/api/session/logout")
    assert resp.status_code == 200
    # After logout, an authed-only endpoint rejects.
    resp2 = authed_client.get("/api/presets")
    assert resp2.status_code == 401


def test_report_latest_requires_auth(client):
    resp = client.get("/api/report/latest")
    assert resp.status_code == 401


def test_report_latest_returns_none_when_absent(authed_client, tmp_path, monkeypatch):
    # Point the module's Path checks at a temp dir that has nothing.
    monkeypatch.chdir(tmp_path)
    resp = authed_client.get("/api/report/latest")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"markdown": None, "payload": None}


def test_report_history_returns_empty_list_when_dir_absent(authed_client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resp = authed_client.get("/api/report/history")
    assert resp.status_code == 200
    assert resp.get_json() == {"reports": []}


def test_candidates_latest_returns_missing_state_when_no_artifact(authed_client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resp = authed_client.get("/api/candidates/latest")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"candidates": [], "artifact_state": "missing"}


def test_preset_run_for_disabled_preset_rejects_at_launch(authed_client, monkeypatch):
    # Stub launch_research_run to avoid actually spawning a subprocess.
    captured = {}

    def fake_launch(*, preset=None, now=None):
        captured["preset"] = preset
        return {"accepted": True, "launch_state": "started", "preset": preset}, 202

    monkeypatch.setattr(dashboard_mod.research_runner, "launch_research_run", fake_launch)
    resp = authed_client.post("/api/presets/pairs_equities_daily_baseline/run")
    assert resp.status_code == 202
    assert captured["preset"] == "pairs_equities_daily_baseline"


def test_preset_run_endpoint_forwards_name(authed_client, monkeypatch):
    captured = {}

    def fake_launch(*, preset=None, now=None):
        captured["preset"] = preset
        return {"accepted": True, "launch_state": "started", "preset": preset}, 202

    monkeypatch.setattr(dashboard_mod.research_runner, "launch_research_run", fake_launch)
    resp = authed_client.post("/api/presets/trend_equities_4h_baseline/run")
    assert resp.status_code == 202
    assert captured["preset"] == "trend_equities_4h_baseline"
