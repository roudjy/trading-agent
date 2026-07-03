from __future__ import annotations

from packages.qre_research.alpha_discovery.strategy_compiler import (
    build_alignment,
    build_strategy_spec,
    compile_strategy_spec,
)
from packages.qre_research.alpha_discovery.strategy_ir import (
    ConditionNode,
    ControlNode,
    FeatureNode,
    PortfolioRule,
    SignalNode,
    normalize_strategy_spec,
    validate_strategy_spec,
)


def test_commutative_condition_normalization_is_stable() -> None:
    spec_a = build_strategy_spec(
        hypothesis_id="qah_fixture",
        mechanism_family="volatility_breakout",
        behavior_family="trend_continuation",
        universe="fixture_universe",
        timeframe="1d",
        regime_scope="trend",
        feature_nodes=(
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
        ),
        signal=SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("greater_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.75),
                right=ConditionNode("less_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=0.6),
            ),
            exit=ConditionNode("greater_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=1.0),
        ),
        parameters=(
            {"name": "atr_short_window", "type": "int", "value": 5},
            {"name": "atr_long_window", "type": "int", "value": 20},
        ),
    )
    spec_b = build_strategy_spec(
        hypothesis_id="qah_fixture",
        mechanism_family="volatility_breakout",
        behavior_family="trend_continuation",
        universe="fixture_universe",
        timeframe="1d",
        regime_scope="trend",
        feature_nodes=(
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
        ),
        signal=SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("less_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=0.6),
                right=ConditionNode("greater_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.75),
            ),
            exit=ConditionNode("greater_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=1.0),
        ),
        parameters=(
            {"name": "atr_short_window", "type": "int", "value": 5},
            {"name": "atr_long_window", "type": "int", "value": 20},
        ),
    )

    assert normalize_strategy_spec(spec_a).content_identity == normalize_strategy_spec(spec_b).content_identity


def test_cross_sectional_rule_is_supported_with_bounded_portfolio_semantics() -> None:
    spec = build_strategy_spec(
        hypothesis_id="qah_cross",
        mechanism_family="trend_persistence",
        behavior_family="relative_strength",
        universe="multi_asset_fixture_universe",
        timeframe="1d",
        regime_scope="trend",
        feature_nodes=(FeatureNode("cross_sectional_rank", {"lookback_bars": 10}, "cross_rank"),),
        signal=SignalNode(
            entry=ConditionNode("greater_than", left=FeatureNode("cross_sectional_rank", {"lookback_bars": 10}, "cross_rank"), right=0.8),
            exit=ConditionNode("less_than", left=FeatureNode("cross_sectional_rank", {"lookback_bars": 10}, "cross_rank"), right=0.5),
        ),
        parameters=({"name": "lookback_bars", "type": "int", "value": 10},),
        controls=(ControlNode("leave_one_out", {"enabled": True}),),
        portfolio_rule=PortfolioRule(weight_semantics="single_strategy_unit_notional", selection_semantics="top_bucket", max_gross_exposure=1.0, max_rules=1),
    )

    assert validate_strategy_spec(spec) == []
    assert compile_strategy_spec(spec)["status"] == "VERIFIED"


def test_unsupported_control_is_rejected() -> None:
    spec = build_strategy_spec(
        hypothesis_id="qah_bad",
        mechanism_family="trend_persistence",
        behavior_family="trend_continuation",
        universe="fixture_universe",
        timeframe="1d",
        regime_scope="trend",
        feature_nodes=(FeatureNode("trend_anchor", {"window": 20}, "trend_anchor"),),
        signal=SignalNode(
            entry=ConditionNode("greater_than", left=FeatureNode("trend_anchor", {"window": 20}, "trend_anchor"), right=0.0),
            exit=ConditionNode("less_than", left=FeatureNode("trend_anchor", {"window": 20}, "trend_anchor"), right=0.0),
        ),
        parameters=({"name": "window", "type": "int", "value": 20},),
        controls=(ControlNode("unsupported_metadata_control", {"foo": "bar"}),),
    )

    assert "unsupported_control:unsupported_metadata_control" in validate_strategy_spec(spec)


def test_alignment_blocks_misaligned_non_long_only_translation() -> None:
    spec = build_strategy_spec(
        hypothesis_id="qah_align",
        mechanism_family="trend_persistence",
        behavior_family="trend_continuation",
        universe="fixture_universe",
        timeframe="1d",
        regime_scope="trend",
        feature_nodes=(FeatureNode("trend_anchor_delta", {"window": 20}, "trend_anchor_delta"),),
        signal=SignalNode(
            entry=ConditionNode("greater_than", left=FeatureNode("trend_anchor_delta", {"window": 20}, "trend_anchor_delta"), right=0.0),
            exit=ConditionNode("less_than", left=FeatureNode("trend_anchor_delta", {"window": 20}, "trend_anchor_delta"), right=0.0),
        ),
        parameters=({"name": "window", "type": "int", "value": 20},),
    )
    alignment = build_alignment(spec)

    assert alignment.alignment_status == "ALIGNED"
