"""Unit tests for v3.15.1 /api/research/public-artifact-status endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dashboard import dashboard as dashboard_mod
from dashboard import research_artifacts
from research.public_artifact_status import (
    build_public_artifact_status,
    write_public_artifact_status,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    status_path = tmp_path / "public_artifact_status_latest.v1.json"
    monkeypatch.setattr(
        research_artifacts, "PUBLIC_ARTIFACT_STATUS_PATH", status_path
    )
    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client(), status_path


@pytest.fixture
def authed_client(client):
    test_client, status_path = client
    with test_client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "joery"
    return test_client, status_path


def _iso(year: int, month: int, day: int) -> str:
    return datetime(year, month, day, 12, 0, tzinfo=UTC).isoformat()


def test_requires_auth(client):
    test_client, _ = client
    resp = test_client.get("/api/research/public-artifact-status")
    assert resp.status_code == 401


def test_absent_state_is_explicit_unknown(authed_client):
    test_client, status_path = authed_client
    # status file does not exist
    assert not status_path.exists()

    resp = test_client.get("/api/research/public-artifact-status")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["state"] == "absent"
    # CRITICAL: missing file is not modeled as "fresh" or "stale";
    # it is explicit unknown so downstream consumers can differentiate
    # "confirmed fresh" from "no signal yet".
    assert data["public_artifacts_stale"] is None
    assert data["stale_reason"] is None
    assert data["stale_since_utc"] is None
    assert data["last_attempted_run"] is None
    assert data["last_public_artifact_write"] is None
    assert data["last_public_write_age_seconds"] is None


def test_valid_success_status_passes_through(authed_client):
    test_client, status_path = authed_client
    payload = build_public_artifact_status(
        outcome="success",
        run_id="run-ok-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    write_public_artifact_status(payload, path=status_path)

    resp = test_client.get("/api/research/public-artifact-status")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["state"] == "valid"
    assert data["schema_version"] == "1.0"
    assert data["public_artifact_status_version"] == "v0.1"
    assert data["public_artifacts_stale"] is False
    assert data["stale_reason"] is None
    assert data["last_public_artifact_write"]["run_id"] == "run-ok-1"
    assert data["last_public_write_age_seconds"] == 0


def test_valid_stale_status_exposes_reason_and_age(authed_client):
    test_client, status_path = authed_client

    prior_success = build_public_artifact_status(
        outcome="success",
        run_id="run-ok-1",
        attempted_at_utc=_iso(2026, 4, 23),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    degenerate = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=prior_success,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    write_public_artifact_status(degenerate, path=status_path)

    resp = test_client.get("/api/research/public-artifact-status")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["state"] == "valid"
    assert data["public_artifacts_stale"] is True
    assert data["stale_reason"] == "degenerate_run_no_public_write"
    assert data["stale_since_utc"] == _iso(2026, 4, 24)
    assert data["last_attempted_run"]["failure_stage"] == (
        "screening_no_survivors"
    )
    assert data["last_public_artifact_write"]["run_id"] == "run-ok-1"
    assert data["last_public_write_age_seconds"] == int(
        timedelta(days=1).total_seconds()
    )


def test_invalid_json_file_falls_back_to_absent_like_payload(authed_client):
    test_client, status_path = authed_client
    status_path.write_text("not json", encoding="utf-8")

    resp = test_client.get("/api/research/public-artifact-status")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["state"] in {"invalid_json", "empty", "absent"}
    assert data["public_artifacts_stale"] is None
