from __future__ import annotations

from research import equity_universe_catalog as catalog


def test_required_universe_ids_and_counts_exist() -> None:
    snapshot = catalog.build_equity_universe_catalog()
    universe_ids = {row["universe_id"] for row in snapshot["universes"]}
    for required in {
        "nl_equities",
        "europe_large_mid",
        "europe_small_mid",
        "us_large_mid",
        "asia_developed_liquid",
        "global_developed_liquid",
    }:
        assert required in universe_ids
    summary = catalog.build_equity_universe_summary()
    assert summary["universe_counts"]["nl_equities"] >= 16
    assert summary["universe_counts"]["europe_large_mid"] >= 40
    assert summary["universe_counts"]["us_large_mid"] >= 25
    assert summary["universe_counts"]["asia_developed_liquid"] >= 20


def test_catalog_is_deterministic_and_research_only() -> None:
    left = catalog.build_equity_universe_catalog()
    right = catalog.build_equity_universe_catalog()
    assert left == right
    assert left["safety_invariants"]["research_only"] is True
    assert left["safety_invariants"]["paper_shadow_live_forbidden"] is True
    assert all(row["asset_class"] == "equity" for row in left["instruments"])
