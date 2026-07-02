from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import pandas as pd

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin
from agent.backtesting.features import resolved_feature_registry

from .contracts import content_id
from .strategy_ir import (
    ALLOWED_OPERATORS,
    ALLOWED_PRIMITIVES,
    ConditionNode,
    FeatureNode,
    SignalNode,
    StrategySpec,
    validate_strategy_spec,
)


def _build_requirement(node: FeatureNode) -> FeatureRequirement:
    return FeatureRequirement(name=node.primitive, params=dict(node.params), alias=node.alias or node.primitive)


def _resolve_operand(operand: Any, features: Mapping[str, pd.Series]) -> Any:
    if isinstance(operand, FeatureNode):
        alias = operand.alias or operand.primitive
        return features[alias]
    if isinstance(operand, ConditionNode):
        return _evaluate_condition(operand, features)
    return operand


def _evaluate_condition(node: ConditionNode, features: Mapping[str, pd.Series]) -> pd.Series:
    if node.operator not in ALLOWED_OPERATORS:
        raise ValueError(f"unsupported operator: {node.operator}")
    left = _resolve_operand(node.left, features)
    right = _resolve_operand(node.right, features) if node.right is not None else None
    if node.operator == "greater_than":
        return left > right
    if node.operator == "less_than":
        return left < right
    if node.operator == "between":
        bounds = right if isinstance(right, tuple) and len(right) == 2 else (None, None)
        lower, upper = bounds
        return (left >= lower) & (left <= upper)
    if node.operator == "and":
        return left.astype(bool) & right.astype(bool)
    if node.operator == "or":
        return left.astype(bool) | right.astype(bool)
    if node.operator == "not":
        return ~left.astype(bool)
    if node.operator == "crosses_above":
        return (left > right) & (left.shift(1) <= right.shift(1))
    if node.operator == "crosses_below":
        return (left < right) & (left.shift(1) >= right.shift(1))
    raise ValueError(f"unsupported operator: {node.operator}")


def _compile_signal(spec: StrategySpec) -> Callable[[pd.DataFrame, Mapping[str, pd.Series]], pd.Series]:
    entry = spec.signal.entry
    exit_ = spec.signal.exit

    def _raw(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        entry_mask = _evaluate_condition(entry, features).fillna(False)
        exit_mask = _evaluate_condition(exit_, features).fillna(False)
        signal = pd.Series(0, index=df.index, dtype=int)
        active = False
        for idx in range(len(signal)):
            if not active and bool(entry_mask.iloc[idx]):
                active = True
            elif active and bool(exit_mask.iloc[idx]):
                active = False
            signal.iloc[idx] = 1 if active else 0
        return signal

    return _raw


def compile_strategy_spec(spec: StrategySpec) -> dict[str, Any]:
    errors = validate_strategy_spec(spec)
    if errors:
        return {"status": "INVALID", "errors": errors, "spec": spec}
    requirements = [_build_requirement(node) for node in spec.feature_nodes]
    raw = _compile_signal(spec)
    executable = declare_thin(
        raw,
        feature_requirements=requirements,
        sizing_spec={"mode": "unit_notional_research_only"},
    )
    return {
        "status": "VERIFIED",
        "spec": spec,
        "feature_requirements": requirements,
        "callable": executable,
        "content_identity": content_id("qsd", spec.to_payload()),
    }


def build_strategy_spec(
    *,
    hypothesis_id: str,
    mechanism_family: str,
    behavior_family: str,
    universe: str,
    timeframe: str,
    regime_scope: str,
    feature_nodes: tuple[FeatureNode, ...],
    signal: SignalNode,
    parameters: tuple[dict[str, Any], ...],
) -> StrategySpec:
    from .strategy_ir import CostAssumption, PortfolioRule, PositionRule, StrategySpec as IRStrategySpec, normalize_strategy_spec

    spec = IRStrategySpec(
        strategy_spec_id=content_id("qss", {"hypothesis_id": hypothesis_id, "mechanism_family": mechanism_family}),
        grammar_version="1.0",
        hypothesis_id=hypothesis_id,
        mechanism_family=mechanism_family,
        behavior_family=behavior_family,
        universe=universe,
        timeframe=timeframe,
        regime_scope=regime_scope,
        feature_nodes=feature_nodes,
        transforms=tuple(),
        signal=signal,
        position_rule=PositionRule(direction="long_only", max_legs=1),
        portfolio_rule=PortfolioRule(max_gross_exposure=1.0, max_rules=1),
        exit_rules=tuple(),
        cost_assumption=CostAssumption(transaction_cost_bps=0.0, slippage_bps=0.0, spread_bps=0.0),
        parameter_schema=parameters,
        content_identity="",
    )
    return normalize_strategy_spec(spec)
