"""Integration: v3.12 candidate sidecars end-to-end via the facade.

Uses the facade directly (not the full research run) so the test is
fast and self-contained, while still exercising the full write path
through _sidecar_io and the actual v2 / status_history / agent_defs
builders.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research._sidecar_io import serialize_canonical
from research.candidate_sidecars import (
    SidecarBuildContext,
    build_and_write_all,
)


RUN_ID = "20260423T120000000000Z"
GIT = "abc123"
NOW = "2026-04-23T12:00:00+00:00"


def _make_research_row(
    strategy_name: str,
    asset: str,
    interval: str = "4h",
    success: bool = True,
    params: dict | None = None,
) -> dict:
    params = params if params is not None else {"fast": 20, "slow": 100}
    return {
        "timestamp_utc": NOW,
        "strategy_name": strategy_name,
        "family": "trend",
        "hypothesis": "",
        "asset": asset,
        "interval": interval,
        "params_json": json.dumps(params, sort_keys=True),
        "success": success,
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


def _make_v1_candidate(strategy_name: str, asset: str, status: str = "candidate") -> dict:
    params = {"fast": 20, "slow": 100}
    params_json = json.dumps(params, sort_keys=True)
    return {
        "strategy_id": f"{strategy_name}|{asset}|4h|{params_json}",
        "strategy_name": strategy_name,
        "asset": asset,
        "interval": "4h",
        "selected_params": params,
        "status": status,
        "reasoning": {"passed": [], "failed": [], "escalated": []},
    }


@pytest.fixture
def sidecar_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "registry": tmp_path / "registry_v2.json",
        "history": tmp_path / "status_history.json",
        "agent_defs": tmp_path / "agent_defs.json",
    }


def _build_context() -> SidecarBuildContext:
    rows = [
        _make_research_row("sma_crossover", "NVDA"),
        _make_research_row("sma_crossover", "AMD"),
        _make_research_row("breakout_momentum", "MSFT"),
    ]
    candidates = [
        _make_v1_candidate("sma_crossover", "NVDA", "candidate"),
        _make_v1_candidate("sma_crossover", "AMD", "needs_investigation"),
        _make_v1_candidate("breakout_momentum", "MSFT", "rejected"),
    ]
    return SidecarBuildContext(
        run_id=RUN_ID,
        generated_at_utc=NOW,
        git_revision=GIT,
        research_latest={
            "generated_at_utc": NOW,
            "count": 3,
            "summary": {"success": 3, "failed": 0, "goedgekeurd": 3},
            "results": rows,
        },
        candidate_registry_v1={
            "version": "v1",
            "generated_at_utc": NOW,
            "git_revision": GIT,
            "promotion_config": {},
            "candidates": candidates,
            "summary": {"total": 3},
        },
        run_candidates=None,
        run_meta={
            "preset_name": "trend_equities_4h_baseline",
            "preset_universe": ["NVDA", "AMD", "ASML", "MSFT"],
            "config_hash": "deadbeef",
            "random_seed": 42,
        },
        defensibility=None,
        regime=None,
        cost_sens=None,
    )


def test_facade_produces_all_three_sidecars_with_content(sidecar_paths: dict[str, Path]) -> None:
    ctx = _build_context()
    paths = build_and_write_all(
        ctx,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )

    registry = json.loads(paths["candidate_registry_v2"].read_text(encoding="utf-8"))
    assert registry["schema_version"] == "2.0"
    assert len(registry["entries"]) == 3

    history = json.loads(paths["candidate_status_history"].read_text(encoding="utf-8"))
    assert len(history["history"]) == 3

    agent_defs = json.loads(paths["agent_definitions"].read_text(encoding="utf-8"))
    assert agent_defs["advisory_only"] is True
    assert agent_defs["runnable_entries"] == 0
    # rejected candidate is out of scope; only exploratory + candidate flow through
    assert len(agent_defs["entries"]) == 2
    assert len(agent_defs["skipped"]) == 1


def test_legacy_verdict_preserved_in_v2(sidecar_paths: dict[str, Path]) -> None:
    ctx = _build_context()
    paths = build_and_write_all(
        ctx,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    registry = json.loads(paths["candidate_registry_v2"].read_text(encoding="utf-8"))
    by_legacy = {e["legacy_verdict"] for e in registry["entries"]}
    assert by_legacy == {"candidate", "needs_investigation", "rejected"}

    by_lifecycle = {e["lifecycle_status"] for e in registry["entries"]}
    assert by_lifecycle == {"candidate", "exploratory", "rejected"}


def test_rerun_with_identical_input_is_byte_identical(sidecar_paths: dict[str, Path]) -> None:
    ctx = _build_context()
    build_and_write_all(
        ctx,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    registry_bytes_1 = sidecar_paths["registry"].read_bytes()
    history_bytes_1 = sidecar_paths["history"].read_bytes()
    agent_defs_bytes_1 = sidecar_paths["agent_defs"].read_bytes()

    # rerun
    build_and_write_all(
        ctx,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    assert sidecar_paths["registry"].read_bytes() == registry_bytes_1
    assert sidecar_paths["history"].read_bytes() == history_bytes_1
    assert sidecar_paths["agent_defs"].read_bytes() == agent_defs_bytes_1


def test_status_history_is_append_only_across_different_run_ids(sidecar_paths: dict[str, Path]) -> None:
    ctx1 = _build_context()
    build_and_write_all(
        ctx1,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    history_after_first = json.loads(sidecar_paths["history"].read_text(encoding="utf-8"))
    events_before = sum(len(v) for v in history_after_first["history"].values())

    # Simulate a later run with a different run_id but same candidates.
    ctx2 = SidecarBuildContext(
        run_id="20260424T120000000000Z",
        generated_at_utc="2026-04-24T12:00:00+00:00",
        git_revision=GIT,
        research_latest=ctx1.research_latest,
        candidate_registry_v1=ctx1.candidate_registry_v1,
        run_candidates=ctx1.run_candidates,
        run_meta=ctx1.run_meta,
        defensibility=ctx1.defensibility,
        regime=ctx1.regime,
        cost_sens=ctx1.cost_sens,
    )
    build_and_write_all(
        ctx2,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    history_after_second = json.loads(sidecar_paths["history"].read_text(encoding="utf-8"))
    events_after = sum(len(v) for v in history_after_second["history"].values())
    # Each candidate gained exactly one additional event on the rerun
    assert events_after == events_before * 2


def test_all_artifacts_are_byte_canonical(sidecar_paths: dict[str, Path]) -> None:
    ctx = _build_context()
    paths = build_and_write_all(
        ctx,
        registry_path=sidecar_paths["registry"],
        history_path=sidecar_paths["history"],
        agent_definitions_path=sidecar_paths["agent_defs"],
    )
    for p in paths.values():
        raw = p.read_bytes()
        assert raw.endswith(b"\n")
        loaded = json.loads(raw.decode("utf-8"))
        assert raw == serialize_canonical(loaded).encode("utf-8")
