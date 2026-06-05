from __future__ import annotations

from research import production_discovery_catalog as catalog


def test_production_discovery_assets_are_regionally_diverse_and_read_only() -> None:
    assets = catalog.list_assets()

    assert len(assets) == 41
    assert {asset.region for asset in assets} == {
        "NL/EU",
        "US",
        "Asia/proxies",
        "ETFs/context",
    }
    for asset in assets:
        payload = asset.to_payload()
        assert payload["enabled_for_discovery"] is True
        assert payload["enabled_for_validation"] is True
        assert payload["not_alpha_claim"] is True
        assert payload["paper_activation_allowed"] is False
        assert payload["shadow_activation_allowed"] is False
        assert payload["live_activation_allowed"] is False
        assert payload["source_quality_status"] == "reviewed_seed_only"
        assert isinstance(payload["canonical_instrument_id"], str)
        assert payload["canonical_instrument_id"]


def test_production_discovery_presets_are_non_executable_seed_metadata() -> None:
    presets = catalog.list_presets()

    assert [preset.preset_id for preset in presets] == [
        "trend_continuation_daily_v1",
        "trend_pullback_continuation_daily_v1",
        "vol_compression_breakout_daily_v1",
        "vol_compression_breakout_4h_v1",
        "relative_strength_vs_sector_daily_v1",
        "relative_strength_vs_region_daily_v1",
        "post_shock_stabilization_daily_v1",
        "index_regime_filter_daily_v1",
    ]
    for preset in presets:
        payload = preset.to_payload()
        assert payload["enabled_for_discovery"] is True
        assert payload["enabled_for_validation"] is True
        assert payload["not_alpha_claim"] is True
        assert payload["paper_activation_allowed"] is False
        assert payload["shadow_activation_allowed"] is False
        assert payload["live_activation_allowed"] is False
        assert payload["expected_failure_modes"]
        assert payload["allowed_timeframes"]
        assert payload["min_history_bars"] >= 750


def test_bounded_candidate_basket_supports_controlled_sprint_without_runtime_activation() -> None:
    basket = catalog.build_bounded_candidate_basket(max_candidates=15)

    assert len(basket) == 15
    assert len({row["candidate_id"] for row in basket}) == 15
    assert len({row["preset_id"] for row in basket}) >= 6
    assert len({row["region"] for row in basket}) == 4
    assert {row["asset_class"] for row in basket} == {"equity", "etf"}
    for row in basket:
        assert row["enabled_for_discovery"] is True
        assert row["enabled_for_validation"] is True
        assert row["not_alpha_claim"] is True
        assert row["paper_activation_allowed"] is False
        assert row["shadow_activation_allowed"] is False
        assert row["live_activation_allowed"] is False


def test_catalog_payload_exposes_seed_only_metadata_and_basket() -> None:
    payload = catalog.production_discovery_catalog_payload(max_candidates=15)

    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["not_alpha_claim"] is True
    assert payload["paper_activation_allowed"] is False
    assert payload["shadow_activation_allowed"] is False
    assert payload["live_activation_allowed"] is False
    assert len(payload["assets"]) == 41
    assert len(payload["presets"]) == 8
    assert len(payload["bounded_candidate_basket"]) == 15
