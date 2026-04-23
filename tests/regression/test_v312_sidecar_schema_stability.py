"""Schema-stability regression for v3.12 sidecars.

Pins the top-level and entry-level key sets of the three new v3.12
artifacts so no subsequent commit can silently drop or rename a
field. Byte-level fixtures are deliberately avoided (they would
force churn every time an unrelated run writes a new timestamp);
schema-level pinning is the right granularity for drift prevention.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.candidate_sidecars import (
    SidecarBuildContext,
    build_and_write_all,
)


RUN_ID = "20260423T120000000000Z"
GIT = "abc123"
NOW = "2026-04-23T12:00:00+00:00"


def _v1_candidate(status: str = "candidate") -> dict:
    return {
        "strategy_id": "sma_crossover|NVDA|4h|{\"fast\": 20, \"slow\": 100}",
        "strategy_name": "sma_crossover",
        "asset": "NVDA",
        "interval": "4h",
        "selected_params": {"fast": 20, "slow": 100},
        "status": status,
        "reasoning": {"passed": [], "failed": [], "escalated": []},
    }


def _ctx() -> SidecarBuildContext:
    return SidecarBuildContext(
        run_id=RUN_ID,
        generated_at_utc=NOW,
        git_revision=GIT,
        research_latest={
            "generated_at_utc": NOW,
            "count": 1,
            "summary": {"success": 1, "failed": 0, "goedgekeurd": 0},
            "results": [
                {
                    "timestamp_utc": NOW,
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
        },
        candidate_registry_v1={
            "version": "v1",
            "generated_at_utc": NOW,
            "git_revision": GIT,
            "promotion_config": {},
            "candidates": [_v1_candidate()],
            "summary": {"total": 1},
        },
        run_candidates=None,
        run_meta={
            "preset_name": "trend_equities_4h_baseline",
            "preset_universe": ["NVDA"],
        },
        defensibility=None,
        regime=None,
        cost_sens=None,
    )


@pytest.fixture
def written(tmp_path: Path) -> dict[str, dict]:
    ctx = _ctx()
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry.json",
        history_path=tmp_path / "history.json",
        agent_definitions_path=tmp_path / "agent_defs.json",
    )
    return {name: json.loads(p.read_text(encoding="utf-8")) for name, p in paths.items()}


REGISTRY_V2_TOP_LEVEL_KEYS = {
    "schema_version",
    "status_model_version",
    "generated_at_utc",
    "run_id",
    "git_revision",
    "summary",
    "entries",
}

REGISTRY_V2_ENTRY_KEYS = {
    "candidate_id",
    "experiment_family",
    "preset_origin",
    "strategy_name",
    "parameter_set",
    "asset",
    "interval",
    "asset_universe",
    "processing_state",
    "lifecycle_status",
    "legacy_verdict",
    "mapping_reason",
    "observed_reason_codes",
    "taxonomy_rejection_codes",
    "taxonomy_derivations",
    "scores",
    "paper_readiness_flags",
    "paper_readiness_assessment_status",
    "deployment_eligibility",
    "lineage_metadata",
    "source_artifact_references",
}

STATUS_HISTORY_TOP_LEVEL_KEYS = {
    "schema_version",
    "status_model_version",
    "generated_at_utc",
    "history",
}

HISTORY_EVENT_KEYS = {
    "event_id",
    "candidate_id",
    "from_status",
    "to_status",
    "reason_code",
    "run_id",
    "at_utc",
    "source_artifact",
}

AGENT_DEFINITIONS_TOP_LEVEL_KEYS = {
    "schema_version",
    "advisory_only",
    "runnable_entries",
    "generated_at_utc",
    "scope_allowed_presets",
    "entries",
    "skipped",
}

AGENT_DEFINITIONS_ENTRY_KEYS = {
    "candidate_id",
    "strategy_name",
    "parameter_set",
    "asset_universe",
    "interval",
    "experiment_family",
    "runnable",
    "execution_scope",
    "advisory_note",
    "source_candidate_registry_v2",
}


def test_registry_v2_top_level_keys(written: dict[str, dict]) -> None:
    assert set(written["candidate_registry_v2"].keys()) == REGISTRY_V2_TOP_LEVEL_KEYS


def test_registry_v2_schema_version_pin(written: dict[str, dict]) -> None:
    assert written["candidate_registry_v2"]["schema_version"] == "2.0"


def test_registry_v2_entry_keys(written: dict[str, dict]) -> None:
    (entry,) = written["candidate_registry_v2"]["entries"]
    assert set(entry.keys()) == REGISTRY_V2_ENTRY_KEYS


def test_registry_v2_taxonomy_derivations_have_no_timestamps(written: dict[str, dict]) -> None:
    (entry,) = written["candidate_registry_v2"]["entries"]
    for derivation in entry["taxonomy_derivations"]:
        assert "derived_at_utc" not in derivation
        assert "at_utc" not in derivation
        assert "timestamp" not in derivation


def test_status_history_top_level_keys(written: dict[str, dict]) -> None:
    assert set(written["candidate_status_history"].keys()) == STATUS_HISTORY_TOP_LEVEL_KEYS


def test_status_history_schema_version_pin(written: dict[str, dict]) -> None:
    assert written["candidate_status_history"]["schema_version"] == "1.0"


def test_status_history_event_keys(written: dict[str, dict]) -> None:
    events = [e for bucket in written["candidate_status_history"]["history"].values() for e in bucket]
    assert events, "expected at least one event"
    for event in events:
        assert set(event.keys()) == HISTORY_EVENT_KEYS


def test_agent_definitions_top_level_keys(written: dict[str, dict]) -> None:
    assert set(written["agent_definitions"].keys()) == AGENT_DEFINITIONS_TOP_LEVEL_KEYS


def test_agent_definitions_schema_version_pin(written: dict[str, dict]) -> None:
    assert written["agent_definitions"]["schema_version"] == "1.0"


def test_agent_definitions_runnable_entries_is_zero(written: dict[str, dict]) -> None:
    assert written["agent_definitions"]["runnable_entries"] == 0


def test_agent_definitions_entry_keys(written: dict[str, dict]) -> None:
    entries = written["agent_definitions"]["entries"]
    assert entries, "expected at least one advisory entry"
    for entry in entries:
        assert set(entry.keys()) == AGENT_DEFINITIONS_ENTRY_KEYS


def test_agent_definitions_every_entry_is_not_runnable(written: dict[str, dict]) -> None:
    for entry in written["agent_definitions"]["entries"]:
        assert entry["runnable"] is False
        assert entry["execution_scope"] == "future_paper_phase_only"


def test_registry_v2_paper_readiness_is_null(written: dict[str, dict]) -> None:
    (entry,) = written["candidate_registry_v2"]["entries"]
    assert entry["paper_readiness_flags"] is None
    assert entry["paper_readiness_assessment_status"] == "reserved_for_future_phase"


def test_registry_v2_status_model_version_pin(written: dict[str, dict]) -> None:
    assert written["candidate_registry_v2"]["status_model_version"] == "v3.12.0"
    assert written["candidate_status_history"]["status_model_version"] == "v3.12.0"
