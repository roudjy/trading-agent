from __future__ import annotations

from research import qre_controlled_discovery_preset_executability as executability


def _row(symbol: str, preset_id: str) -> dict[str, object]:
    rows = executability.build_preset_executability_report(max_candidates=15)["rows"]
    return next(
        row
        for row in rows
        if row["instrument_symbol"] == symbol and row["behavior_preset_id"] == preset_id
    )


def test_executable_row_is_classified_as_executable() -> None:
    row = _row("AAPL", "trend_continuation_daily_v1")
    assert row["classification"] == "executable"


def test_intentionally_non_executable_row_is_classified() -> None:
    row = _row("AAPL", "relative_strength_vs_sector_daily_v1")
    assert row["classification"] == "intentionally_non_executable"


def test_region_and_asset_class_mismatches_are_classified() -> None:
    region_row = _row("ASML", "vol_compression_breakout_4h_v1")
    asset_row = _row("SPY", "trend_pullback_continuation_daily_v1")

    assert region_row["classification"] == "region_constraint_mismatch"
    assert asset_row["classification"] == "asset_class_constraint_mismatch"


def test_source_identity_block_can_preempt_executability() -> None:
    row = _row("ASMI", "trend_continuation_daily_v1")
    assert row["classification"] == "source_identity_blocked"


def test_deterministic_order_and_write_outputs() -> None:
    report = executability.build_preset_executability_report(max_candidates=15)

    assert report["rows"][0]["classification"] != "executable"
    assert report["summary"]["total_combinations"] == 328
