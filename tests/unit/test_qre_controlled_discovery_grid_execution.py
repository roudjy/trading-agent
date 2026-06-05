from __future__ import annotations

from research import controlled_discovery_grid as grid
from research import controlled_discovery_grid_execution as execution


def _row(**overrides: object) -> dict[str, object]:
    row = grid.build_controlled_discovery_grid()[0]
    row.update(overrides)
    return row


def test_valid_mapping_returns_ready_single_asset_override() -> None:
    row = _row(
        instrument_symbol="ASML",
        region="NL/EU",
        asset_class="equity",
        behavior_preset_id="trend_continuation_daily_v1",
        hypothesis_id="trend_continuation_behavior_v1",
        timeframe="1d",
    )

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "ready"
    assert mapping.blocker_class is None
    assert mapping.strategy_or_preset_reference == "trend_equities_4h_baseline"
    assert mapping.validation_campaign_id == (
        "qre-grid-validation-001-asml-trend_continuation_daily_v1"
    )
    assert mapping.run_label == "qre_grid_seq_001_ASML_trend_continuation_daily_v1"
    assert mapping.output_subdir == "combination_001_ASML_trend_continuation_daily_v1"
    assert mapping.preset_override is not None
    assert mapping.preset_override.universe == ("ASML",)
    assert mapping.preset_override.timeframe == "1d"
    assert mapping.safety_flags["not_alpha_claim"] is True
    assert mapping.safety_flags["paper_activation_allowed"] is False
    assert mapping.safety_flags["shadow_activation_allowed"] is False
    assert mapping.safety_flags["live_activation_allowed"] is False


def test_unsupported_behavior_family_returns_skipped_blocker() -> None:
    row = _row(
        instrument_symbol="ASML",
        region="NL/EU",
        asset_class="equity",
        behavior_preset_id="relative_strength_vs_sector_daily_v1",
        hypothesis_id="relative_strength_sector_behavior_v1",
        timeframe="1d",
    )

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "skipped"
    assert mapping.blocker_class == "preset_not_executable"
    assert mapping.preset_override is None


def test_missing_metadata_returns_missing_validation_input_blocker() -> None:
    row = _row(hypothesis_id="")

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "skipped"
    assert mapping.blocker_class == "missing_validation_input"
    assert "missing_hypothesis_id" in mapping.mapping_notes


def test_safety_flag_violation_is_blocked_closed() -> None:
    row = _row(paper_activation_allowed=True)

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "skipped"
    assert mapping.blocker_class == "blocked_by_safety"
    assert mapping.preset_override is None


def test_region_constraint_mismatch_is_classified_without_crash() -> None:
    row = _row(
        instrument_symbol="ASML",
        region="NL/EU",
        asset_class="equity",
        behavior_preset_id="vol_compression_breakout_4h_v1",
        hypothesis_id="vol_compression_expansion_behavior_v1",
        timeframe="4h",
    )

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "skipped"
    assert mapping.blocker_class == "preset_region_constraint_mismatch"


def test_asset_class_constraint_mismatch_is_classified_without_crash() -> None:
    row = _row(
        instrument_symbol="SPY",
        region="ETFs/context",
        asset_class="etf",
        behavior_preset_id="trend_pullback_continuation_daily_v1",
        hypothesis_id="trend_pullback_behavior_v1",
        timeframe="1d",
    )

    mapping = execution.map_grid_row_to_execution(row)

    assert mapping.status == "skipped"
    assert mapping.blocker_class == "preset_asset_class_constraint_mismatch"


def test_mapping_is_deterministic_for_same_row() -> None:
    row = _row(
        instrument_symbol="AAPL",
        region="US",
        asset_class="equity",
        behavior_preset_id="vol_compression_breakout_daily_v1",
        hypothesis_id="vol_compression_expansion_behavior_v1",
        timeframe="1d",
    )

    first = execution.map_grid_row_to_execution(dict(row))
    second = execution.map_grid_row_to_execution(dict(row))

    assert first.validation_campaign_id == second.validation_campaign_id
    assert first.run_label == second.run_label
    assert first.output_subdir == second.output_subdir
