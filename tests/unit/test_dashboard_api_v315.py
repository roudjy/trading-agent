"""Unit tests for the v3.15 /api/registry/paper* endpoints."""

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


def _write(dir_: Path, name: str, payload: dict) -> None:
    (dir_ / "research" / name).write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _ledger_payload() -> dict:
    return {
        "schema_version": "1.0",
        "paper_ledger_version": "v0.1",
        "paper_venues_version": "v0.1",
        "generated_at_utc": "2026-04-24T10:00:00+00:00",
        "run_id": "r",
        "git_revision": "g",
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "event_types": ["signal", "order", "fill", "reject", "skip", "position"],
        "evidence_statuses": ["reconstructed", "projected_minimal", "projected_insufficient"],
        "overall_event_counts": {
            "signal": 4, "order": 3, "fill": 3,
            "reject": 1, "skip": 0, "position": 3,
        },
        "per_candidate": [],
    }


def _divergence_payload() -> dict:
    return {
        "schema_version": "1.0",
        "paper_divergence_version": "v0.1",
        "paper_venues_version": "v0.1",
        "generated_at_utc": "2026-04-24T10:00:00+00:00",
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "alignment_policy": {},
        "severity_thresholds_bps": {"medium": 25.0, "high": 75.0},
        "severity_counts": {"low": 2, "medium": 1, "high": 0},
        "per_candidate": [{"candidate_id": "x"}],
        "per_sleeve_equal_weight": [],
        "portfolio_equal_weight": {},
    }


def _readiness_payload() -> dict:
    return {
        "schema_version": "1.0",
        "paper_readiness_version": "v0.1",
        "generated_at_utc": "2026-04-24T10:00:00+00:00",
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "thresholds": {"min_paper_oos_days": 60},
        "blocking_reasons_taxonomy": [],
        "warning_reasons_taxonomy": [],
        "readiness_statuses": [
            "ready_for_paper_promotion", "blocked", "insufficient_evidence",
        ],
        "counts": {
            "ready_for_paper_promotion": 1,
            "blocked": 1,
            "insufficient_evidence": 0,
        },
        "entries": [{"candidate_id": "c1"}],
    }


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


def test_paper_summary_requires_auth(client):
    assert client.get("/api/registry/paper").status_code == 401


def test_paper_ledger_requires_auth(client):
    assert client.get("/api/registry/paper/ledger").status_code == 401


def test_paper_divergence_requires_auth(client):
    assert client.get("/api/registry/paper/divergence").status_code == 401


def test_paper_readiness_requires_auth(client):
    assert client.get("/api/registry/paper/readiness").status_code == 401


# ---------------------------------------------------------------------------
# Missing-state schemas
# ---------------------------------------------------------------------------


def test_detail_endpoints_missing_state_schemas(authed_client):
    for path, key in (
        ("/api/registry/paper/ledger", "per_candidate"),
        ("/api/registry/paper/divergence", "per_candidate"),
        ("/api/registry/paper/readiness", "entries"),
    ):
        resp = authed_client.get(path)
        assert resp.status_code == 200, path
        data = resp.get_json()
        assert data["artifact_state"] == "missing", path
        assert data["schema_version"] == "1.0", path
        assert data["live_eligible"] is False, path
        assert data[key] == [], path


def test_summary_missing_state(authed_client):
    resp = authed_client.get("/api/registry/paper")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "missing"
    assert data["live_eligible"] is False
    assert data["artifact_states"] == {
        "ledger": "missing",
        "divergence": "missing",
        "readiness": "missing",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_detail_endpoints_pass_through_payloads(authed_client, tmp_path: Path):
    _write(tmp_path, "paper_ledger_latest.v1.json", _ledger_payload())
    _write(tmp_path, "paper_divergence_latest.v1.json", _divergence_payload())
    _write(tmp_path, "paper_readiness_latest.v1.json", _readiness_payload())

    ledger = authed_client.get("/api/registry/paper/ledger").get_json()
    assert ledger["paper_ledger_version"] == "v0.1"
    assert ledger["overall_event_counts"]["signal"] == 4

    div = authed_client.get("/api/registry/paper/divergence").get_json()
    assert div["paper_divergence_version"] == "v0.1"
    assert div["severity_counts"]["medium"] == 1

    rdy = authed_client.get("/api/registry/paper/readiness").get_json()
    assert rdy["paper_readiness_version"] == "v0.1"
    assert rdy["counts"]["blocked"] == 1


def test_summary_aggregates_counts_from_detail_artifacts(authed_client, tmp_path: Path):
    _write(tmp_path, "paper_ledger_latest.v1.json", _ledger_payload())
    _write(tmp_path, "paper_divergence_latest.v1.json", _divergence_payload())
    _write(tmp_path, "paper_readiness_latest.v1.json", _readiness_payload())

    resp = authed_client.get("/api/registry/paper")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_state"] == "present"
    assert data["live_eligible"] is False
    assert data["readiness_counts"] == {
        "ready_for_paper_promotion": 1,
        "blocked": 1,
        "insufficient_evidence": 0,
    }
    assert data["divergence_severity_distribution"] == {
        "low": 2, "medium": 1, "high": 0,
    }
    assert data["ledger_event_counts"]["signal"] == 4
    assert data["ledger_event_counts"]["fill"] == 3
    assert data["generated_at_utc"] == "2026-04-24T10:00:00+00:00"
