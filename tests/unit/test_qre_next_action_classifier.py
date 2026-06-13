from __future__ import annotations

from research.qre_next_action_classifier import classify_next_action


def test_metric_action_is_code_required_safe_to_plan_not_execute() -> None:
    result = classify_next_action("add_cache_only_metric_path")

    assert result["action_class"] == "code_required"
    assert result["safety_class"] == "safe_to_plan_requires_pr"
    assert result["ade_build_allowed"] is True
    assert result["execution_allowed"] is False
    assert result["recommended_branch"] == "feat/qre-add-cache-only-metric-path"
    assert "paper_shadow_live" in result["blocked_authorities"]


def test_metric_rule_is_pattern_based_not_one_off() -> None:
    for action in (
        "add_safe_trade_count_metric",
        "add_safe_drawdown_metric",
        "add_safe_deflated_sharpe_metric",
        "repair_cache_or_add_safe_metric_input",
        "add_result_to_market_intake_feedback",
    ):
        result = classify_next_action(action)
        assert result["action_class"] == "code_required"
        assert result["ade_build_allowed"] is True
        assert result["execution_allowed"] is False


def test_reporting_action_is_reporting_or_ux_code_required() -> None:
    result = classify_next_action("add_universe_coverage_report")

    assert result["action_class"] == "reporting_or_ux_code_required"
    assert result["safety_class"] == "safe_to_plan_requires_pr"
    assert result["ade_build_allowed"] is True


def test_unsafe_actions_are_blocked_denylist_first() -> None:
    for action in (
        "enable_paper_runtime",
        "enable_shadow_mode",
        "activate_live_runtime",
        "broker_order_path",
        "execution_router",
        "place_order_now",
        "trade_signal_emit",
        "promote_candidate_alpha",
        "launch_campaign_direct",
        "mutate_preset_registry",
    ):
        result = classify_next_action(action)
        assert result["action_class"] == "blocked"
        assert result["safety_class"] == "unsafe_requires_explicit_separate_governance"
        assert result["ade_build_allowed"] is False
        assert result["execution_allowed"] is False


def test_hold_and_unknown_fail_closed() -> None:
    hold = classify_next_action("operator_review_required")
    unknown = classify_next_action("invent_new_autonomy_mode")

    assert hold["action_class"] == "review_required"
    assert hold["ade_build_allowed"] is False
    assert unknown["action_class"] == "unknown"
    assert unknown["safety_class"] == "fail_closed_human_review_required"
    assert unknown["ade_build_allowed"] is False
    assert unknown["execution_allowed"] is False

