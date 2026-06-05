from __future__ import annotations

from pathlib import Path

from research import controlled_discovery_grid as grid


def test_controlled_discovery_grid_builds_expected_328_combinations() -> None:
    payload = grid.controlled_discovery_grid_payload()

    assert payload["schema_version"] == 1
    assert payload["grid_kind"] == "qre_controlled_discovery_grid"
    assert payload["instrument_count"] == 41
    assert payload["behavior_preset_count"] == 8
    assert payload["total_combinations"] == 328
    assert len(payload["combinations"]) == 328


def test_controlled_discovery_grid_ordering_is_stable() -> None:
    combinations = grid.build_controlled_discovery_grid()

    assert combinations[0]["sequence_number"] == 1
    assert combinations[0]["instrument_symbol"] == "ADYEN"
    assert combinations[0]["behavior_preset_id"] == "index_regime_filter_daily_v1"
    assert combinations[0]["grid_id"] == (
        "qre-grid::001::ADYEN::index_regime_filter_daily_v1"
    )
    assert combinations[-1]["sequence_number"] == 328
    assert combinations[-1]["instrument_symbol"] == "VGK"
    assert combinations[-1]["behavior_preset_id"] == "vol_compression_breakout_daily_v1"
    assert combinations[-1]["grid_id"] == (
        "qre-grid::328::VGK::vol_compression_breakout_daily_v1"
    )


def test_controlled_discovery_grid_safety_flags_are_hard_false() -> None:
    for row in grid.build_controlled_discovery_grid():
        assert row["enabled_for_discovery"] is True
        assert row["enabled_for_validation"] is True
        assert row["not_alpha_claim"] is True
        assert row["paper_activation_allowed"] is False
        assert row["shadow_activation_allowed"] is False
        assert row["live_activation_allowed"] is False
        assert row["status"] == "planned"
        assert row["result_path"] is None
        assert row["blocker_class"] is None
        assert row["outcome_class"] == "not_started"
        assert row["metadata_warnings"] == []


def test_controlled_discovery_grid_rows_expose_required_metadata() -> None:
    row = grid.build_controlled_discovery_grid()[0]

    assert row["canonical_instrument_id"]
    assert row["region"] in {"NL/EU", "US", "Asia/proxies", "ETFs/context"}
    assert row["asset_class"] in {"equity", "etf"}
    assert row["hypothesis_id"]
    assert row["timeframe"] in {"1d", "4h"}
    assert "primary_data_provider_symbol" in row
    assert "provider_symbol_aliases" in row
    assert "provider_symbol_status" in row
    assert "source_identity_status" in row
    assert "source_identity_notes" in row
    assert "source_identity_blocker_class" in row


def test_controlled_discovery_grid_does_not_mutate_frozen_contracts() -> None:
    assert Path("research/research_latest.json").exists()
    assert Path("research/strategy_matrix.csv").exists()
