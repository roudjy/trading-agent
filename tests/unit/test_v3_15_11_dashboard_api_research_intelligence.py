"""v3.15.11 — dashboard API endpoint tests for the research intelligence layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard.api_research_intelligence import (
    register_research_intelligence_routes,
)
from research import (
    dead_zone_detection,
    information_gain,
    research_evidence_ledger,
    stop_condition_engine,
    viability_metrics,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    base = tmp_path / "research" / "campaigns" / "evidence"
    base.mkdir(parents=True, exist_ok=True)
    paths = {
        "evidence": base / "evidence_ledger_latest.v1.json",
        "ig": base / "information_gain_latest.v1.json",
        "stop": base / "stop_conditions_latest.v1.json",
        "dz": base / "dead_zones_latest.v1.json",
        "via": base / "viability_latest.v1.json",
    }
    monkeypatch.setattr(
        research_evidence_ledger, "EVIDENCE_LEDGER_PATH", paths["evidence"]
    )
    monkeypatch.setattr(
        information_gain, "INFORMATION_GAIN_PATH", paths["ig"]
    )
    monkeypatch.setattr(
        stop_condition_engine, "STOP_CONDITIONS_PATH", paths["stop"]
    )
    monkeypatch.setattr(dead_zone_detection, "DEAD_ZONES_PATH", paths["dz"])
    monkeypatch.setattr(viability_metrics, "VIABILITY_PATH", paths["via"])

    # Re-import the API module so it picks up patched paths.
    import importlib
    import dashboard.api_research_intelligence as api_mod
    api_mod = importlib.reload(api_mod)

    app = Flask(__name__)
    api_mod.register_research_intelligence_routes(app)
    app.config["TESTING"] = True
    test_client = app.test_client()
    test_client._patched_paths = paths  # type: ignore[attr-defined]
    return test_client


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def test_evidence_ledger_endpoint_returns_artifact(client: Any) -> None:
    paths = client._patched_paths
    payload = {
        "schema_version": "1.0",
        "hypothesis_evidence": [],
        "failure_mode_counts": [],
        "candidate_lineage": [],
        "summary": {"campaign_count": 1, "hypothesis_count": 0, "failure_mode_count": 0, "candidate_lineage_count": 0},
    }
    _write(paths["evidence"], payload)
    resp = client.get("/api/research/evidence-ledger")
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["campaign_count"] == 1


def test_evidence_ledger_endpoint_graceful_when_artifact_missing(
    client: Any,
) -> None:
    resp = client.get("/api/research/evidence-ledger")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["schema_version"] == "1.0"
    assert body["hypothesis_evidence"] == []


def test_information_gain_endpoint(client: Any) -> None:
    paths = client._patched_paths
    _write(
        paths["ig"],
        {
            "schema_version": "1.0",
            "information_gain": {
                "score": 0.8,
                "bucket": "high",
                "is_meaningful_campaign": True,
                "reasons": [],
            },
            "inputs": {},
        },
    )
    resp = client.get("/api/research/information-gain")
    assert resp.status_code == 200
    assert resp.get_json()["information_gain"]["bucket"] == "high"


def test_stop_conditions_endpoint_passes_advisory_state(client: Any) -> None:
    paths = client._patched_paths
    _write(
        paths["stop"],
        {
            "schema_version": "1.0",
            "enforcement_state": "advisory_only",
            "decisions": [
                {
                    "scope_type": "preset",
                    "scope_id": "p1",
                    "recommended_decision": "COOLDOWN",
                    "enforcement_state": "advisory_only",
                    "severity": "info",
                    "reason_codes": ["x"],
                    "evidence": {},
                    "cooldown_until_utc": None,
                }
            ],
        },
    )
    resp = client.get("/api/research/stop-conditions")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enforcement_state"] == "advisory_only"
    assert body["decisions"][0]["recommended_decision"] == "COOLDOWN"


def test_dead_zones_endpoint(client: Any) -> None:
    paths = client._patched_paths
    _write(paths["dz"], {"schema_version": "1.0", "zones": [{"zone_status": "dead"}]})
    resp = client.get("/api/research/dead-zones")
    assert resp.status_code == 200
    assert resp.get_json()["zones"][0]["zone_status"] == "dead"


def test_viability_endpoint(client: Any) -> None:
    paths = client._patched_paths
    _write(
        paths["via"],
        {
            "schema_version": "1.0",
            "metrics": {"campaign_count": 25, "candidate_count": 1},
            "verdict": {
                "status": "promising",
                "reason_codes": ["candidate_or_paper_ready_present"],
                "human_summary": "ok",
            },
        },
    )
    resp = client.get("/api/research/viability")
    assert resp.status_code == 200
    assert resp.get_json()["verdict"]["status"] == "promising"


def test_intelligence_summary_endpoint_combines_artifacts(client: Any) -> None:
    paths = client._patched_paths
    _write(
        paths["via"],
        {
            "schema_version": "1.0",
            "metrics": {"campaign_count": 25, "candidate_count": 0},
            "verdict": {
                "status": "weak",
                "reason_codes": ["learning_signal_without_candidate_yet"],
                "human_summary": "learning",
            },
        },
    )
    _write(
        paths["dz"],
        {
            "schema_version": "1.0",
            "zones": [{"zone_status": "dead"}, {"zone_status": "alive"}],
        },
    )
    _write(
        paths["stop"],
        {
            "schema_version": "1.0",
            "enforcement_state": "advisory_only",
            "decisions": [
                {
                    "scope_type": "preset",
                    "scope_id": "p1",
                    "recommended_decision": "COOLDOWN",
                    "enforcement_state": "advisory_only",
                    "severity": "info",
                    "reason_codes": [],
                    "evidence": {},
                    "cooldown_until_utc": None,
                }
            ],
        },
    )
    resp = client.get("/api/research/intelligence-summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enforcement_state"] == "advisory_only"
    assert body["viability"]["status"] == "weak"
    assert body["dead_zone_count"] == 1
    assert body["advisory_decision_count"] == 1


def test_intelligence_summary_endpoint_graceful_when_all_missing(
    client: Any,
) -> None:
    resp = client.get("/api/research/intelligence-summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enforcement_state"] == "advisory_only"
    assert body["viability"]["status"] == "insufficient_data"
    assert body["dead_zone_count"] == 0
    assert body["advisory_decision_count"] == 0
