from __future__ import annotations

from packages.qre_research import hypothesis_lifecycle as qhl


def test_current_cross_sectional_lifecycle_uses_readiness_bridge() -> None:
    feasibility = qhl.build_feasibility_snapshot()
    row = next(
        item
        for item in feasibility["rows"]
        if item["source_hypothesis_id"] == "cross_sectional_momentum_v0"
    )

    assert row["status"] == "ready"
    assert row["primitive_compatibility"] == "COMPILABLE_WITH_CURRENT_PRIMITIVES"
    assert row["portfolio_status"] == "READY_FOR_PREREGISTRATION"
    assert row["next_action"] == "create_second_campaign_preregistration_manifest"


def test_current_cross_sectional_sampling_materializes_exact_window_blocker() -> None:
    sampling = qhl.build_sampling_snapshot()
    row = next(
        item
        for item in sampling["rows"]
        if item["source_hypothesis_id"] == "cross_sectional_momentum_v0"
    )

    assert row["sampling_status"] == "ready"
    assert row["sampling_reason_codes"] == []
    assert row["next_action"] == "evaluate_exact_blocker_or_empirical_campaign_gap"
