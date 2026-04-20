"""v3.6 Step 4 - pairs end-to-end integration (planner -> engine -> output).

This module is the integration pin for pairs as a real Tier 1 baseline.
It exercises the full chain with the registry flipped `enabled=True`
for `pairs_zscore`, and asserts five contracts in a single path:

1. The planner produces exactly one pairs candidate with
   `reference_asset` threaded through `strategy_requirements` and the
   public `asset` field carrying only the primary symbol (no
   concatenation like `"BTC-EUR|ETH-EUR"`).
2. `apply_fit_prior` does NOT block the pairs candidate - reference
   presence relaxes the spread-blanket rule, as pinned in
   test_candidate_reference_asset.py.
3. The engine's multi-asset loader path is reached via the mocked
   MarketRepository, the aligned primary + reference frames flow into
   the fold loop, and thin-strategy feature resolution goes through
   `build_features_for_multi` so the `close_ref`-backed `spread_zscore`
   feature materialises.
4. The engine returns public OOS metrics that `make_result_row`
   successfully consumes, and the resulting row matches
   `ROW_SCHEMA` exactly (the v3.5 frozen public surface). No
   `reference_asset` key leaks into the row.
5. The top-level `research_latest.json` payload built from that row
   matches `JSON_TOP_LEVEL_SCHEMA` exactly. No new top-level keys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest

from agent.backtesting.engine import BacktestEngine
from agent.backtesting.strategies import pairs_zscore_strategie
from data.contracts import Provenance
from data.repository import BarsResponse
from research.candidate_pipeline import (
    FIT_BLOCKED,
    apply_fit_prior,
    plan_candidates,
)
from research.results import (
    JSON_TOP_LEVEL_SCHEMA,
    ROW_SCHEMA,
    make_result_row,
    write_latest_json,
)
from tests._harness_helpers import build_aligned_pair_frames


AS_OF_UTC = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)


def _provenance() -> Provenance:
    return Provenance(
        adapter="fixture",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg",
        source_version="1.0",
        cache_hit=False,
    )


def _pairs_registry_entry() -> dict:
    """Mirror the registry entry used in research/registry.py.

    Kept test-local so that this integration fixture stays meaningful
    even if the registry is reordered - and so the test fails loudly
    if the contract drifts (e.g. reference_asset renamed).
    """
    return {
        "name": "pairs_zscore",
        "factory": pairs_zscore_strategie,
        "params": {
            "lookback": [30],
            "entry_z": [2.0],
            "exit_z": [0.5],
            "hedge_ratio": [1.0],
        },
        "family": "stat_arb",
        "strategy_family": "stat_arb",
        "position_structure": "spread",
        "initial_lane_support": "supported",
        "reference_asset": "ETH-EUR",
        "hypothesis": "Spread z-score pairs trading tier 1 baseline.",
        "enabled": True,
    }


def _build_repo_with_pair_frames() -> MagicMock:
    primary_frame, reference_frame = build_aligned_pair_frames(
        seed_primary=11, seed_reference=19, length=260
    )
    calls: list[str] = []
    repo = MagicMock()

    def _get_bars(*, instrument, interval, start_utc, end_utc):
        calls.append(instrument.native_symbol)
        if instrument.native_symbol.startswith("BTC"):
            return BarsResponse(frame=primary_frame.copy(), provenance=_provenance())
        return BarsResponse(frame=reference_frame.copy(), provenance=_provenance())

    repo.get_bars.side_effect = _get_bars
    repo._call_log = calls
    return repo


def test_plan_produces_pairs_candidate_with_internal_reference_only():
    """Contract pin: planner carries reference_asset only on internal
    strategy_requirements; public `asset` remains singular."""
    assets = [SimpleNamespace(symbol="BTC-EUR", asset_type="crypto", asset_class="crypto")]

    candidates = plan_candidates(
        strategies=[_pairs_registry_entry()], assets=assets, intervals=["1d"]
    )

    assert len(candidates) == 1
    candidate = candidates[0]

    assert candidate["asset"] == "BTC-EUR"
    assert "|" not in candidate["asset"]
    assert "ETH-EUR" not in candidate["asset"]
    assert candidate["strategy_requirements"]["reference_asset"] == "ETH-EUR"
    assert candidate["strategy_requirements"]["position_structure"] == "spread"


def test_apply_fit_prior_does_not_block_pairs_when_reference_declared():
    assets = [SimpleNamespace(symbol="BTC-EUR", asset_type="crypto", asset_class="crypto")]
    candidates = plan_candidates(
        strategies=[_pairs_registry_entry()], assets=assets, intervals=["1d"]
    )
    updated, counts = apply_fit_prior(candidates)

    assert counts["fit_blocked_count"] == 0
    assert counts["fit_blocked_reasons"] == {}
    statuses = [item["fit_prior"]["status"] for item in updated]
    assert FIT_BLOCKED not in statuses


def test_engine_run_reaches_pair_loader_and_feature_multi_path(monkeypatch):
    """End-to-end wiring pin: engine.run with reference_asset ->
    MarketRepository.get_bars fetches both legs -> load_aligned_pair
    produces AlignedPairFrame -> AssetContext.reference_frame is set
    -> _invoke_strategy routes through build_features_for_multi."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
    )

    metrics = engine.run(
        strategy, assets=["BTC-EUR"], interval="1d", reference_asset="ETH-EUR"
    )

    symbols_fetched = repo._call_log
    assert any(s.startswith("BTC") for s in symbols_fetched)
    assert any(s.startswith("ETH") for s in symbols_fetched)
    assert isinstance(metrics, dict)
    for key in ("sharpe", "win_rate", "max_drawdown", "totaal_trades", "goedgekeurd"):
        assert key in metrics, f"missing metric key: {key}"


def test_engine_grid_search_reaches_pair_loader(monkeypatch):
    """Batch-execution path pin: engine.grid_search accepts
    reference_asset and threads it through asset-context loading."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )

    metrics = engine.grid_search(
        strategie_factory=pairs_zscore_strategie,
        param_grid={
            "lookback": [30],
            "entry_z": [2.0],
            "exit_z": [0.5],
            "hedge_ratio": [1.0],
        },
        assets=["BTC-EUR"],
        interval="1d",
        reference_asset="ETH-EUR",
    )

    symbols_fetched = repo._call_log
    assert any(s.startswith("BTC") for s in symbols_fetched)
    assert any(s.startswith("ETH") for s in symbols_fetched)
    assert "beste_params" in metrics or "reden" in metrics


def test_pairs_result_row_matches_frozen_output_schema(monkeypatch):
    """Public output contract pin: a pairs result row built via
    make_result_row matches ROW_SCHEMA exactly. No reference_asset
    key leaks into the public row."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )
    metrics = engine.grid_search(
        strategie_factory=pairs_zscore_strategie,
        param_grid={
            "lookback": [30],
            "entry_z": [2.0],
            "exit_z": [0.5],
            "hedge_ratio": [1.0],
        },
        assets=["BTC-EUR"],
        interval="1d",
        reference_asset="ETH-EUR",
    )

    row = make_result_row(
        strategy=_pairs_registry_entry(),
        asset="BTC-EUR",
        interval="1d",
        params=metrics.get("beste_params", {}),
        as_of_utc=AS_OF_UTC,
        metrics=metrics,
    )

    assert tuple(row.keys()) == ROW_SCHEMA
    assert "reference_asset" not in row
    assert row["asset"] == "BTC-EUR"
    assert "|" not in str(row["asset"])
    assert "ETH-EUR" not in str(row["asset"])


def test_pairs_latest_json_payload_schema_stable(monkeypatch, tmp_path):
    """Public output contract pin: research_latest.json top-level
    schema stays frozen when a pairs row is written. write_latest_json
    invokes the SchemaDriftError guard if a key leaks."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )
    metrics = engine.grid_search(
        strategie_factory=pairs_zscore_strategie,
        param_grid={
            "lookback": [30],
            "entry_z": [2.0],
            "exit_z": [0.5],
            "hedge_ratio": [1.0],
        },
        assets=["BTC-EUR"],
        interval="1d",
        reference_asset="ETH-EUR",
    )
    row = make_result_row(
        strategy=_pairs_registry_entry(),
        asset="BTC-EUR",
        interval="1d",
        params=metrics.get("beste_params", {}),
        as_of_utc=AS_OF_UTC,
        metrics=metrics,
    )
    out_path = tmp_path / "research_latest.json"

    write_latest_json([row], AS_OF_UTC, path=str(out_path))

    import json
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert tuple(payload.keys()) == JSON_TOP_LEVEL_SCHEMA
    assert "reference_asset" not in payload
    for result_row in payload["results"]:
        assert tuple(result_row.keys()) == ROW_SCHEMA
        assert "reference_asset" not in result_row


def test_pairs_candidate_uses_multi_asset_feature_resolution(monkeypatch):
    """Feature-resolution path pin: when the engine runs pairs with a
    reference_asset, thin-strategy feature resolution MUST go through
    build_features_for_multi (primary + reference frames), not the
    single-frame build_features_for path."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    multi_calls: list[tuple[int, set[str]]] = []
    single_calls: list[int] = []

    import agent.backtesting.engine as engine_module
    real_multi = engine_module.build_features_for_multi
    real_single = engine_module.build_features_for

    def _tracking_multi(requirements, frames):
        multi_calls.append((len(requirements), set(frames.keys())))
        return real_multi(requirements, frames)

    def _tracking_single(requirements, df):
        single_calls.append(len(requirements))
        return real_single(requirements, df)

    monkeypatch.setattr(engine_module, "build_features_for_multi", _tracking_multi)
    monkeypatch.setattr(engine_module, "build_features_for", _tracking_single)

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
    )
    engine.run(
        strategy, assets=["BTC-EUR"], interval="1d", reference_asset="ETH-EUR"
    )

    assert multi_calls, (
        "build_features_for_multi was never invoked for a pairs run - "
        "pair reference_frame did not reach the fold loop"
    )
    for _n_reqs, keys in multi_calls:
        assert "primary" in keys
        assert "reference" in keys


@pytest.mark.parametrize("reference_asset", [None, ""])
def test_engine_run_without_reference_asset_never_fetches_reference(
    monkeypatch, reference_asset
):
    """Scope-lock pin: reference_asset is inert when absent. No pair
    load is attempted, single-asset path is fully preserved for
    non-pair strategies / non-pair calls."""
    repo = _build_repo_with_pair_frames()
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repo)

    from agent.backtesting.strategies import sma_crossover_strategie

    engine = BacktestEngine(
        "2024-01-01",
        "2024-09-16",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )
    strategy = sma_crossover_strategie(fast_window=10, slow_window=50)

    kwargs: dict = {"assets": ["BTC-EUR"], "interval": "1d"}
    if reference_asset is not None:
        kwargs["reference_asset"] = reference_asset if reference_asset else None
    engine.run(strategy, **kwargs)

    symbols_fetched = repo._call_log
    assert all(not s.startswith("ETH") for s in symbols_fetched), (
        f"reference leg fetched without reference_asset declared: {symbols_fetched}"
    )
