from __future__ import annotations

from research import qre_bounded_aapl_nvda_current_basket_generation_discovery as discovery


def test_discovery_reports_no_safe_bounded_generation_command_found() -> None:
    report = discovery.build_bounded_aapl_nvda_current_basket_generation_discovery()

    summary = report["summary"]
    assert summary["approval_scope_id"] == discovery.APPROVAL_SCOPE_ID
    assert summary["safe_bounded_generation_command_found"] is False
    assert summary["final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
    assert summary["exact_scope_candidate_count"] == 2


def test_discovery_classifies_exact_scope_candidates_fail_closed() -> None:
    report = discovery.build_bounded_aapl_nvda_current_basket_generation_discovery()
    rows = report["command_surface"]["rows"]
    exact_scope_rows = [row for row in rows if row["exact_scope_match"]]

    assert len(exact_scope_rows) == 2
    assert all(row["safe_command_available"] is False for row in exact_scope_rows)
    assert all(row["disposition"] != "bounded_generation_approved_for_this_pr" for row in exact_scope_rows)


def test_discovery_preserves_forbidden_command_boundaries() -> None:
    report = discovery.build_bounded_aapl_nvda_current_basket_generation_discovery()
    rows = report["command_surface"]["rows"]
    row_by_command = {row["command"]: row for row in rows}

    assert row_by_command[
        "python -m research.campaign_launcher --preset trend_pullback_continuation_daily_v1"
    ]["disposition"] == "forbidden_mutation"
    assert row_by_command[
        "python -m research.run_research --preset trend_pullback_continuation_daily_v1"
    ]["safe_command_available"] is False


def test_discovery_output_is_deterministic() -> None:
    first = discovery.build_bounded_aapl_nvda_current_basket_generation_discovery()
    second = discovery.build_bounded_aapl_nvda_current_basket_generation_discovery()

    assert first == second
