"""v3.12 additive enrichment in report_agent (schema_version unchanged)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import report_agent


def _write_research_latest(dir_: Path) -> Path:
    payload = {
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "count": 1,
        "summary": {"success": 1, "failed": 0, "goedgekeurd": 1},
        "results": [
            {
                "timestamp_utc": "2026-04-23T12:00:00+00:00",
                "strategy_name": "sma_crossover",
                "family": "trend",
                "hypothesis": "",
                "asset": "NVDA",
                "interval": "4h",
                "params_json": json.dumps({"fast": 20, "slow": 100}, sort_keys=True),
                "success": True,
                "error": "",
                "win_rate": 0.55,
                "sharpe": 1.1,
                "deflated_sharpe": 0.8,
                "max_drawdown": 0.22,
                "trades_per_maand": 5.5,
                "consistentie": 0.5,
                "totaal_trades": 55,
                "goedgekeurd": True,
                "criteria_checks_json": "{}",
                "reden": "",
            }
        ],
    }
    path = dir_ / "research_latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_run_meta(dir_: Path) -> Path:
    payload = {
        "schema_version": "1.1",
        "run_id": "test_run",
        "preset_name": "trend_equities_4h_baseline",
        "candidate_summary": {"raw": 1, "screened": 1, "validated": 1, "rejected": 0, "promoted": 1},
        "top_rejection_reasons": [],
    }
    path = dir_ / "run_meta_latest.v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_v1_registry(dir_: Path) -> Path:
    payload = {
        "version": "v1",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "git_revision": "abc123",
        "promotion_config": {},
        "candidates": [
            {
                "strategy_id": "sma_crossover|NVDA|4h|{\"fast\": 20, \"slow\": 100}",
                "strategy_name": "sma_crossover",
                "asset": "NVDA",
                "interval": "4h",
                "selected_params": {"fast": 20, "slow": 100},
                "status": "candidate",
                "reasoning": {"passed": [], "failed": [], "escalated": []},
            }
        ],
        "summary": {"total": 1, "candidate": 1},
    }
    path = dir_ / "candidate_registry_latest.v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_v2_registry(dir_: Path) -> Path:
    payload = {
        "schema_version": "2.0",
        "status_model_version": "v3.12.0",
        "generated_at_utc": "2026-04-23T12:00:00+00:00",
        "run_id": "test_run",
        "git_revision": "abc123",
        "summary": {
            "total": 1,
            "by_lifecycle_status": {"candidate": 1},
            "by_processing_state": {"validation": 1},
        },
        "entries": [
            {
                "candidate_id": "sma_crossover|NVDA|4h|{\"fast\": 20, \"slow\": 100}",
                "experiment_family": "trend|equities",
                "preset_origin": "trend_equities_4h_baseline",
                "strategy_name": "sma_crossover",
                "parameter_set": {"fast": 20, "slow": 100},
                "asset": "NVDA",
                "interval": "4h",
                "asset_universe": ["NVDA"],
                "processing_state": "validation",
                "lifecycle_status": "candidate",
                "legacy_verdict": "candidate",
                "mapping_reason": "legacy_candidate_preserved",
                "observed_reason_codes": [],
                "taxonomy_rejection_codes": [],
                "taxonomy_derivations": [],
                "scores": {
                    "composite_score": 0.6,
                    "composite_status": "provisional",
                    "authoritative": False,
                    "scoring_formula_version": "v0.1-experimental",
                    "components": {},
                    "derivation_metadata": {},
                },
                "paper_readiness_flags": None,
                "paper_readiness_assessment_status": "reserved_for_future_phase",
                "deployment_eligibility": "reserved_for_future_phase",
                "lineage_metadata": {
                    "run_id": "test_run",
                    "git_revision": "abc123",
                    "config_hash": None,
                    "data_snapshot_id": None,
                    "random_seed": None,
                    "adapter_versions": {},
                    "feature_versions": {},
                    "evaluation_version": None,
                    "execution_engine_used": "research_only",
                },
                "source_artifact_references": {},
            }
        ],
    }
    path = dir_ / "candidate_registry_latest.v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def sidecar_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all sidecar paths to tmp_path and write fixtures."""
    monkeypatch.chdir(tmp_path)
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    _write_research_latest(research_dir)
    _write_run_meta(research_dir)
    _write_v1_registry(research_dir)
    _write_v2_registry(research_dir)
    return research_dir


def test_schema_version_remains_v1_1(sidecar_dir: Path) -> None:
    payload = report_agent.build_report_payload()
    assert payload["schema_version"] == "1.1"


def test_per_candidate_entries_gain_lifecycle_status(sidecar_dir: Path) -> None:
    payload = report_agent.build_report_payload()
    (entry,) = payload["per_candidate_diagnostics"]
    assert entry.get("lifecycle_status") == "candidate"
    assert entry.get("legacy_verdict") == "candidate"


def test_per_candidate_entries_gain_taxonomy_and_scores(sidecar_dir: Path) -> None:
    payload = report_agent.build_report_payload()
    (entry,) = payload["per_candidate_diagnostics"]
    assert entry.get("taxonomy_rejection_codes") == []
    assert entry.get("observed_reason_codes") == []
    scores = entry.get("scores")
    assert scores["composite_status"] == "provisional"
    assert scores["authoritative"] is False


def test_lifecycle_breakdown_populated_in_payload(sidecar_dir: Path) -> None:
    payload = report_agent.build_report_payload()
    assert payload.get("lifecycle_breakdown") == {"candidate": 1}


def test_markdown_includes_lifecycle_breakdown_section(sidecar_dir: Path) -> None:
    payload = report_agent.build_report_payload()
    md = report_agent.render_markdown(payload)
    assert "Candidate Lifecycle Breakdown (v3.12)" in md
    assert "candidate: 1" in md


def test_payload_still_renders_when_v2_sidecar_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    _write_research_latest(research_dir)
    _write_run_meta(research_dir)
    _write_v1_registry(research_dir)
    # intentionally: NO v2 sidecar

    payload = report_agent.build_report_payload()
    assert payload["schema_version"] == "1.1"
    # v3.12 fields are absent; existing keys are preserved
    (entry,) = payload["per_candidate_diagnostics"]
    assert "lifecycle_status" not in entry
    assert payload.get("lifecycle_breakdown") is None


def test_existing_per_candidate_keys_are_preserved(sidecar_dir: Path) -> None:
    """v3.11 keys that Reports.tsx reads must remain present."""
    payload = report_agent.build_report_payload()
    (entry,) = payload["per_candidate_diagnostics"]
    for key in ("strategy_id", "strategy_name", "asset", "interval", "verdict", "metrics"):
        assert key in entry, f"v3.11 key {key!r} missing"
