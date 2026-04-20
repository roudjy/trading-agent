"""v3.6 Step 3 — candidate-identity plumbing for reference_asset.

The critical invariants this module pins:

- `candidate_id` for strategies without `reference_asset` must hash
  byte-identically to the v3.5 payload. This protects every existing
  Tier 1 candidate hash from drifting when the new field is added.
- `assess_fit_prior` blocks `position_structure == "spread"` candidates
  only when `reference_asset` is absent - when a reference asset is
  declared, spread strategies fall through to the normal matrix.
- The public `asset` column stays singular for pair candidates; the
  `reference_asset` field lives exclusively on internal surfaces
  (`strategy_requirements`) and is never concatenated into `asset`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from research.candidate_pipeline import (
    FIT_BLOCKED,
    apply_fit_prior,
    assess_fit_prior,
    plan_candidates,
)


AS_OF_UTC = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _crypto_asset(symbol: str) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, asset_type="crypto", asset_class="crypto")


def _strategy(
    name: str,
    *,
    family: str = "trend",
    strategy_family: str = "trend_following",
    position_structure: str = "outright",
    initial_lane_support: str = "supported",
    reference_asset: str | None = None,
) -> dict:
    entry: dict = {
        "name": name,
        "family": family,
        "strategy_family": strategy_family,
        "position_structure": position_structure,
        "initial_lane_support": initial_lane_support,
        "params": {"periode": [14]},
        "factory": lambda **params: None,
        "hypothesis": "fixture",
    }
    if reference_asset is not None:
        entry["reference_asset"] = reference_asset
    return entry


def _legacy_v35_hash(
    *,
    strategy_name: str,
    strategy_family: str,
    asset: str,
    asset_type: str,
    asset_class: str,
    interval: str,
    param_grid_hash: str,
    position_structure: str,
    initial_lane_support: str,
) -> str:
    """Mirror the v3.5 _hash_payload payload exactly.

    This is the payload shape that existed before v3.6 added the
    optional `reference_asset` key. The new path must produce the
    same digest when reference_asset is absent.
    """
    payload = {
        "strategy_name": strategy_name,
        "strategy_family": strategy_family,
        "asset": asset,
        "asset_type": asset_type,
        "asset_class": asset_class,
        "interval": interval,
        "param_grid_hash": param_grid_hash,
        "position_structure": position_structure,
        "initial_lane_support": initial_lane_support,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_candidate_id_unchanged_when_reference_asset_absent():
    """SMA-style strategy without reference_asset must hash byte-identically
    to the pre-v3.6 payload shape."""
    strategies = [_strategy(name="sma_crossover")]
    assets = [_crypto_asset("BTC-USD")]

    candidates = plan_candidates(
        strategies=strategies, assets=assets, intervals=["1d"]
    )
    assert len(candidates) == 1
    candidate = candidates[0]

    expected = _legacy_v35_hash(
        strategy_name="sma_crossover",
        strategy_family="trend_following",
        asset="BTC-USD",
        asset_type="crypto",
        asset_class="crypto",
        interval="1d",
        param_grid_hash=candidate["parameter_space_identity"]["param_grid_hash"],
        position_structure="outright",
        initial_lane_support="supported",
    )

    assert candidate["candidate_id"] == expected, (
        "v3.5 candidate_id must be byte-identical when reference_asset is "
        "absent; any drift breaks every persisted Tier 1 hash downstream."
    )


def test_candidate_id_differs_when_reference_asset_declared():
    """A strategy that declares reference_asset must produce a new hash -
    ensures pair candidates are distinguishable from outright ones."""
    base = _strategy(name="pairs_zscore", position_structure="spread")
    with_ref = _strategy(
        name="pairs_zscore",
        position_structure="spread",
        reference_asset="ETH-EUR",
    )
    assets = [_crypto_asset("BTC-EUR")]

    base_candidate = plan_candidates(
        strategies=[base], assets=assets, intervals=["1d"]
    )[0]
    with_ref_candidate = plan_candidates(
        strategies=[with_ref], assets=assets, intervals=["1d"]
    )[0]

    assert base_candidate["candidate_id"] != with_ref_candidate["candidate_id"]


def test_strategy_requirements_carries_reference_asset_internally():
    strategies = [
        _strategy(
            name="pairs_zscore",
            position_structure="spread",
            reference_asset="ETH-EUR",
        )
    ]
    assets = [_crypto_asset("BTC-EUR")]

    candidate = plan_candidates(
        strategies=strategies, assets=assets, intervals=["1d"]
    )[0]

    requirements = candidate["strategy_requirements"]
    assert requirements["reference_asset"] == "ETH-EUR"
    assert requirements["position_structure"] == "spread"


def test_strategy_requirements_omits_reference_asset_when_absent():
    """v3.5 strategies must retain their v3.5 strategy_requirements shape -
    no spurious reference_asset key should appear."""
    strategies = [_strategy(name="sma_crossover")]
    assets = [_crypto_asset("BTC-USD")]

    candidate = plan_candidates(
        strategies=strategies, assets=assets, intervals=["1d"]
    )[0]

    assert "reference_asset" not in candidate["strategy_requirements"]


def test_fit_prior_pairs_unblocked_when_reference_declared():
    """A pair candidate with a declared reference_asset must not be
    FIT_BLOCKED on the 'requires_spread_not_outright' rule."""
    candidate = {
        "strategy_requirements": {
            "position_structure": "spread",
            "initial_lane_support": "supported",
            "reference_asset": "ETH-EUR",
        },
        "asset_type": "crypto",
        "asset_class": "crypto",
        "strategy_family": "stat_arb",
    }

    status, reason = assess_fit_prior(candidate)
    assert (status, reason) != (FIT_BLOCKED, "requires_spread_not_outright")


def test_fit_prior_pairs_still_blocked_without_reference():
    """Spread candidate without reference_asset stays FIT_BLOCKED -
    the relaxation is strictly keyed on reference_asset presence."""
    candidate = {
        "strategy_requirements": {
            "position_structure": "spread",
            "initial_lane_support": "supported",
        },
        "asset_type": "crypto",
        "asset_class": "crypto",
        "strategy_family": "stat_arb",
    }

    status, reason = assess_fit_prior(candidate)
    assert (status, reason) == (FIT_BLOCKED, "requires_spread_not_outright")


def test_fit_prior_empty_reference_asset_treated_as_absent():
    """Empty string / None reference_asset must still trip the block rule -
    we only relax when a real symbol is declared."""
    candidate = {
        "strategy_requirements": {
            "position_structure": "spread",
            "initial_lane_support": "supported",
            "reference_asset": "",
        },
        "asset_type": "crypto",
        "asset_class": "crypto",
        "strategy_family": "stat_arb",
    }

    status, reason = assess_fit_prior(candidate)
    assert (status, reason) == (FIT_BLOCKED, "requires_spread_not_outright")


def test_apply_fit_prior_pair_candidate_falls_through_to_matrix():
    """With reference_asset declared, a pair candidate is reached by the
    normal fit-prior matrix instead of short-circuiting on spread."""
    strategies = [
        _strategy(
            name="pairs_zscore",
            family="stat_arb",
            strategy_family="stat_arb",
            position_structure="spread",
            reference_asset="ETH-EUR",
        )
    ]
    assets = [_crypto_asset("BTC-EUR")]

    candidates = plan_candidates(
        strategies=strategies, assets=assets, intervals=["1d"]
    )
    updated, counts = apply_fit_prior(candidates)

    assert counts["fit_blocked_count"] == 0
    assert counts["fit_blocked_reasons"] == {}
    statuses = {item["fit_prior"]["reason"] for item in updated}
    assert "requires_spread_not_outright" not in statuses


def test_asset_column_stays_singular_for_pair_candidates():
    """Public `asset` field must carry the primary symbol only - no
    concatenation like 'BTC-EUR|ETH-EUR' is allowed under v3.6 scope."""
    strategies = [
        _strategy(
            name="pairs_zscore",
            family="stat_arb",
            strategy_family="stat_arb",
            position_structure="spread",
            reference_asset="ETH-EUR",
        )
    ]
    assets = [_crypto_asset("BTC-EUR")]

    candidate = plan_candidates(
        strategies=strategies, assets=assets, intervals=["1d"]
    )[0]

    assert candidate["asset"] == "BTC-EUR"
    assert "|" not in candidate["asset"]
    assert "ETH-EUR" not in candidate["asset"]


def test_registry_pairs_zscore_declares_reference_asset():
    """Guard: the pairs_zscore registry entry must carry reference_asset
    so downstream planners / engine wiring resolve the pair."""
    from research.registry import STRATEGIES

    pairs_entries = [s for s in STRATEGIES if s["name"] == "pairs_zscore"]
    assert len(pairs_entries) == 1
    assert pairs_entries[0].get("reference_asset") == "ETH-EUR"
