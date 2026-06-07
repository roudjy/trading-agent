from __future__ import annotations

from research.equity_factors import recipe_catalog


def test_recipe_catalog_has_unique_ids_and_closed_vocabularies() -> None:
    report = recipe_catalog.build_equity_factor_recipe_catalog()
    rows = report["rows"]
    recipe_ids = [row["recipe_id"] for row in rows]
    assert len(recipe_ids) == len(set(recipe_ids))
    assert report["policy_vocabulary"]["output_type"] == ["hypothesis_seed_candidates"]
    blocked_vocab = set(report["policy_vocabulary"]["blocked_reason_codes"])
    for row in rows:
        assert row["output_type"] == "hypothesis_seed_candidates"
        assert set(row["blocked_reason_codes"]).issubset(blocked_vocab)
        assert row["feasibility_status"] in blocked_vocab


def test_recipe_catalog_references_existing_universes_and_factors() -> None:
    report = recipe_catalog.build_equity_factor_recipe_catalog()
    for row in report["rows"]:
        assert row["feasibility_status"] == "BLOCKED_DATA_READINESS_MISSING"
        assert "trade_signal" in row["forbidden_outputs"]
        assert "paper_candidate" in row["forbidden_outputs"]
        assert "live_candidate" in row["forbidden_outputs"]
        assert row["research_only"] is True

