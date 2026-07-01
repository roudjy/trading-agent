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
    assert row["portfolio_status"] == "BLOCKED_WINDOWS"
    assert row["next_action"] == "preserve_fail_closed_data_window_capacity_blockers"


def test_current_cross_sectional_sampling_materializes_exact_window_blocker() -> None:
    sampling = qhl.build_sampling_snapshot()
    row = next(
        item
        for item in sampling["rows"]
        if item["source_hypothesis_id"] == "cross_sectional_momentum_v0"
    )

    assert row["sampling_status"] == "blocked"
    assert "usable_history_below_minimum_policy_span" in row["sampling_reason_codes"]
    assert row["next_action"] == "preserve_fail_closed_data_window_capacity_blockers"
