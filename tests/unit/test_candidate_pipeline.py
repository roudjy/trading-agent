from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from research.candidate_pipeline import (
    FIT_ALLOWED,
    FIT_BLOCKED,
    FIT_DISCOURAGED,
    apply_fit_prior,
    build_candidate_artifact_payload,
    build_filter_summary_payload,
    deduplicate_candidates,
    plan_candidates,
)


AS_OF_UTC = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _strategy(name: str, *, family: str, strategy_family: str, position_structure: str = "outright", initial_lane_support: str = "supported"):
    return {
        "name": name,
        "family": family,
        "strategy_family": strategy_family,
        "position_structure": position_structure,
        "initial_lane_support": initial_lane_support,
        "params": {"periode": [14, 21, 28]},
        "factory": lambda **params: None,
        "hypothesis": "fixture",
    }


def test_candidate_planning_is_deterministic():
    strategies = [
        _strategy(name="b", family="trend", strategy_family="breakout"),
        _strategy(name="a", family="trend", strategy_family="trend_following"),
    ]
    assets = [
        SimpleNamespace(symbol="ETH-USD", asset_type="crypto", asset_class="crypto"),
        SimpleNamespace(symbol="BTC-USD", asset_type="crypto", asset_class="crypto"),
    ]
    intervals = ["4h", "1h"]

    first = plan_candidates(strategies=strategies, assets=assets, intervals=intervals)
    second = plan_candidates(strategies=strategies, assets=assets, intervals=intervals)

    assert first == second
    assert [candidate["strategy_name"] for candidate in first[:2]] == ["a", "a"]
    assert first[0]["asset"] == "BTC-USD"
    assert first[0]["interval"] == "1h"
    assert first[0]["asset_type"] == "crypto"


def test_deduplication_is_exact_and_reproducible():
    strategies = [
        _strategy(name="dup", family="trend", strategy_family="trend_following"),
        _strategy(name="dup", family="trend", strategy_family="trend_following"),
    ]
    assets = [SimpleNamespace(symbol="BTC-USD", asset_type="crypto", asset_class="crypto")]
    intervals = ["1h"]

    planned = plan_candidates(strategies=strategies, assets=assets, intervals=intervals)
    deduplicated, summary = deduplicate_candidates(planned)

    assert summary == {
        "raw_candidate_count": 2,
        "deduplicated_candidate_count": 1,
        "duplicates_removed": 1,
    }
    assert deduplicated[0]["dedupe"]["raw_occurrences"] == 2
    assert deduplicated[0]["dedupe"]["duplicate_removed"] is True


def test_fit_prior_gating_is_deterministic_and_explicit():
    strategies = [
        _strategy(name="trend", family="trend", strategy_family="trend_following"),
        _strategy(name="mr", family="mean_reversion", strategy_family="mean_reversion"),
        _strategy(
            name="pairs",
            family="stat_arb",
            strategy_family="stat_arb",
            position_structure="spread",
            initial_lane_support="blocked",
        ),
    ]
    assets = [
        SimpleNamespace(symbol="BTC-USD", asset_type="crypto", asset_class="crypto"),
        SimpleNamespace(symbol="AAPL", asset_type="equity", asset_class="equity"),
    ]
    planned = plan_candidates(strategies=strategies, assets=assets, intervals=["1h"])
    deduplicated, _ = deduplicate_candidates(planned)

    candidates, summary = apply_fit_prior(deduplicated)
    fit_by_name_asset = {
        (candidate["strategy_name"], candidate["asset"]): candidate["fit_prior"]["status"]
        for candidate in candidates
    }

    assert fit_by_name_asset[("trend", "BTC-USD")] == FIT_ALLOWED
    assert fit_by_name_asset[("mr", "BTC-USD")] == FIT_DISCOURAGED
    assert fit_by_name_asset[("mr", "AAPL")] == FIT_DISCOURAGED
    assert fit_by_name_asset[("pairs", "AAPL")] == FIT_BLOCKED
    assert summary["fit_blocked_reasons"] == {"requires_spread_not_outright": 2}


def test_candidate_sidecar_payloads_include_reduction_counts():
    strategies = [
        _strategy(name="trend", family="trend", strategy_family="trend_following"),
        _strategy(name="pairs", family="stat_arb", strategy_family="stat_arb", position_structure="spread", initial_lane_support="blocked"),
    ]
    assets = [SimpleNamespace(symbol="BTC-USD", asset_type="crypto", asset_class="crypto")]
    planned = plan_candidates(strategies=strategies, assets=assets, intervals=["1h"])
    deduplicated, _ = deduplicate_candidates(planned)
    fitted, _ = apply_fit_prior(deduplicated)
    fitted[0]["eligibility"] = {"status": "eligible", "reason": None}
    fitted[0]["screening"] = {"status": "promoted_to_validation", "reason": None}
    fitted[0]["validation"] = {"status": "validated", "result_success": True}
    fitted[0]["current_status"] = "validated"

    candidate_payload = build_candidate_artifact_payload(
        run_id="run-1",
        as_of_utc=AS_OF_UTC,
        candidates=fitted,
    )
    filter_payload = build_filter_summary_payload(
        run_id="run-1",
        as_of_utc=AS_OF_UTC,
        candidates=fitted,
    )

    assert candidate_payload["summary"]["raw_candidate_count"] == 2
    assert candidate_payload["summary"]["fit_blocked_count"] == 1
    assert candidate_payload["summary"]["validation_candidate_count"] == 1
    assert filter_payload["fit_blocked_reasons"] == {"requires_spread_not_outright": 1}
    assert filter_payload["screening_decisions"]["promoted_to_validation"] == 1


def test_asset_type_normalization_uses_explicit_mapping():
    strategies = [_strategy(name="trend", family="trend", strategy_family="trend_following")]
    assets = [SimpleNamespace(symbol="SPY", asset_type="ETF", asset_class="index")]

    planned = plan_candidates(strategies=strategies, assets=assets, intervals=["1d"])

    assert planned[0]["asset_type"] == "index_like"
    assert planned[0]["asset_class"] == "index"
