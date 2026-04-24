"""v3.15 unit tests: paper_venues."""

from __future__ import annotations

import pytest

from agent.backtesting.cost_sensitivity import ScenarioSpec
from research import paper_venues


def test_constants_are_exposed_and_finite():
    assert paper_venues.PAPER_VENUES_VERSION == "v0.1"
    assert paper_venues.VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE == pytest.approx(0.0025)
    assert paper_venues.VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS == pytest.approx(10.0)
    assert paper_venues.VENUE_IBKR_EQUITY_FEE_FLAT_EUR == pytest.approx(1.0)
    assert paper_venues.VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR == pytest.approx(2000.0)
    assert paper_venues.VENUE_IBKR_EQUITY_FEE_PER_SIDE == pytest.approx(
        paper_venues.VENUE_IBKR_EQUITY_FEE_FLAT_EUR
        / paper_venues.VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR
    )
    assert paper_venues.VENUE_IBKR_EQUITY_SLIPPAGE_BPS == pytest.approx(10.0)
    # Polymarket constants defined, even though unapplied in v3.15
    assert paper_venues.VENUE_POLYMARKET_FEE_PER_SIDE == pytest.approx(0.01)
    assert paper_venues.VENUE_POLYMARKET_SLIPPAGE_BPS == pytest.approx(10.0)


def test_venue_name_mapping_crypto_and_equity():
    assert paper_venues.venue_name_for_asset_type("crypto") == "crypto_bitvavo"
    assert paper_venues.venue_name_for_asset_type("CRYPTO") == "crypto_bitvavo"
    assert paper_venues.venue_name_for_asset_type("equity") == "equity_ibkr"
    assert paper_venues.venue_name_for_asset_type("EQUITY") == "equity_ibkr"


@pytest.mark.parametrize("asset_type", ["unknown", "futures", "index_like", "", "polymarket"])
def test_unmapped_asset_types_return_none(asset_type):
    # v3.15 invariant: no fallback substitution. Readiness turns
    # None into insufficient_venue_mapping.
    assert paper_venues.venue_name_for_asset_type(asset_type) is None


def test_venue_scenario_crypto_returns_valid_scenariospec():
    scenario = paper_venues.venue_scenario_for(
        "crypto",
        baseline_kosten_per_kant=0.0025,
    )
    assert isinstance(scenario, ScenarioSpec)
    assert scenario.name == "crypto_bitvavo"
    # fee_multiplier = 0.0025 / 0.0025 = 1.0 (exact Bitvavo match)
    assert scenario.fee_multiplier == pytest.approx(1.0)
    assert scenario.slippage_bps == pytest.approx(10.0)


def test_venue_scenario_equity_converts_flat_fee_to_multiplier():
    baseline = 0.001  # 10 bps baseline kosten_per_kant
    scenario = paper_venues.venue_scenario_for(
        "equity",
        baseline_kosten_per_kant=baseline,
    )
    assert isinstance(scenario, ScenarioSpec)
    assert scenario.name == "equity_ibkr"
    # fee_multiplier = (1/2000) / 0.001 = 0.5
    assert scenario.fee_multiplier == pytest.approx(0.5)
    assert scenario.slippage_bps == pytest.approx(10.0)


@pytest.mark.parametrize(
    "asset_type,baseline",
    [
        ("unknown", 0.0025),
        ("futures", 0.0025),
        ("index_like", 0.0025),
        ("crypto", 0.0),
        ("crypto", -0.001),
        ("equity", 0.0),
    ],
)
def test_venue_scenario_returns_none_for_unmapped_or_invalid_baseline(asset_type, baseline):
    assert paper_venues.venue_scenario_for(
        asset_type,
        baseline_kosten_per_kant=baseline,
    ) is None


def test_venue_metadata_is_auditable_and_echoes_ibkr_notional():
    meta = paper_venues.venue_metadata()
    assert meta["paper_venues_version"] == "v0.1"
    ibkr = meta["equity_ibkr"]
    assert ibkr["assumed_notional_eur"] == pytest.approx(2000.0)
    assert ibkr["fee_flat_eur"] == pytest.approx(1.0)
    assert ibkr["fee_per_side"] == pytest.approx(0.0005)
    poly = meta["polymarket_binary"]
    assert poly["applied_in_v3_15"] is False
    assert "no Polymarket candidates" in poly["reason_not_applied"]
    assert set(meta["unmapped_asset_types"]) == {"unknown", "futures", "index_like"}
