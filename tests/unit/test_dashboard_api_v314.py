"""Unit tests for the v3.14 /api/registry/portfolio endpoint.

Mirrors the v3.13 regime-endpoint tests exactly: auth-gated, stable
missing-state schema, pass-through happy path.
"""

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


def _write_portfolio_diagnostics(dir_: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "diagnostics_layer_version": "v0.1",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "run_id": "test_run",
        "git_revision": "abc",
        "authoritative": False,
        "diagnostic_only": True,
        "thresholds": {"min_overlap_days": 90},
        "correlation": {"candidate": {"labels": [], "matrix": []}},
        "equal_weight_portfolio": {"candidate_count": 0, "overlap_days": 0},
        "drawdown_attribution": [],
        "concentration_warnings": [{"dimension": "asset", "hhi": 0.5}],
        "intra_sleeve_correlation_warnings": [],
        "turnover_contribution": [],
        "regime_conditioned": [],
    }
    (dir_ / "research" / "portfolio_diagnostics_latest.v1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_portfolio_endpoint_requires_auth(client):
    resp = client.get("/api/registry/portfolio")
    assert resp.status_code == 401


def test_portfolio_endpoint_returns_stable_missing_state(authed_client):
    resp = authed_client.get("/api/registry/portfolio")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
    assert data["schema_version"] == "1.0"
    assert data["diagnostics_layer_version"] is None
    assert data["generated_at_utc"] is None
    assert data["authoritative"] is False
    assert data["diagnostic_only"] is True
    assert data["concentration_warnings"] == []


def test_portfolio_endpoint_serves_payload_when_present(authed_client, tmp_path: Path):
    _write_portfolio_diagnostics(tmp_path)
    resp = authed_client.get("/api/registry/portfolio")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "1.0"
    assert data["diagnostics_layer_version"] == "v0.1"
    assert data["concentration_warnings"][0]["dimension"] == "asset"
