"""Tests for research.candidate_sidecars (v3.12 facade)."""

from __future__ import annotations

import json
from pathlib import Path

from research._sidecar_io import serialize_canonical
from research.candidate_sidecars import (
    SidecarBuildContext,
    build_and_write_all,
)


RUN_ID = "20260423T120000000000Z"
GIT = "abc123"
NOW = "2026-04-23T12:00:00+00:00"


def _v1_registry() -> dict:
    return {
        "version": "v1",
        "generated_at_utc": NOW,
        "git_revision": GIT,
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
        "summary": {"total": 1},
    }


def _research_latest() -> dict:
    return {
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
                "sharpe": 1.0,
                "deflated_sharpe": 0.7,
                "max_drawdown": 0.25,
                "trades_per_maand": 5.0,
                "consistentie": 0.5,
                "totaal_trades": 60,
                "goedgekeurd": True,
                "criteria_checks_json": "{}",
                "reden": "",
            }
        ],
    }


def _context(tmp_path: Path) -> SidecarBuildContext:
    return SidecarBuildContext(
        run_id=RUN_ID,
        generated_at_utc=NOW,
        git_revision=GIT,
        research_latest=_research_latest(),
        candidate_registry_v1=_v1_registry(),
        run_candidates=None,
        run_meta={"preset_name": "trend_equities_4h_baseline", "preset_universe": ["NVDA"]},
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
    )


def test_facade_writes_all_three_sidecars(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )

    assert set(paths.keys()) == {
        "candidate_registry_v2",
        "candidate_status_history",
        "agent_definitions",
    }
    for p in paths.values():
        assert p.exists()


def test_facade_writes_only_three_artifacts(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["agent_definitions.json", "registry_v2.json", "status_history.json"]


def test_facade_registry_v2_has_correct_schema_version(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    payload = json.loads(paths["candidate_registry_v2"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2.0"


def test_facade_status_history_is_populated(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    payload = json.loads(paths["candidate_status_history"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert "history" in payload
    assert len(payload["history"]) == 1


def test_facade_agent_definitions_runnable_entries_is_zero(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    payload = json.loads(paths["agent_definitions"].read_text(encoding="utf-8"))
    assert payload["runnable_entries"] == 0
    assert payload["advisory_only"] is True


def test_facade_is_idempotent_across_reruns(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    first = (tmp_path / "status_history.json").read_bytes()
    # rerun with identical context
    build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    second = (tmp_path / "status_history.json").read_bytes()
    assert first == second


def test_facade_output_is_byte_canonical(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    paths = build_and_write_all(
        ctx,
        registry_path=tmp_path / "registry_v2.json",
        history_path=tmp_path / "status_history.json",
        agent_definitions_path=tmp_path / "agent_definitions.json",
    )
    for p in paths.values():
        raw = p.read_bytes()
        loaded = json.loads(raw.decode("utf-8"))
        assert raw == serialize_canonical(loaded).encode("utf-8")
