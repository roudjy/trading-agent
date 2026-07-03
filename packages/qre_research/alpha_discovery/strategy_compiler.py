from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin

from .contracts import MechanismImplementationAlignment, content_id
from .strategy_ir import (
    ALLOWED_OPERATORS,
    ConditionNode,
    ControlNode,
    FeatureNode,
    PortfolioRule,
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


def _apply_controls(mask: pd.Series, controls: tuple[ControlNode, ...], features: Mapping[str, pd.Series]) -> pd.Series:
    current = mask.astype(bool)
    for control in controls:
        if control.control_type == "regime_filter":
            feature_alias = str(control.params.get("feature_alias") or "")
            threshold = float(control.params.get("threshold") or 0.0)
            comparator = str(control.params.get("comparator") or "greater_than")
            if feature_alias and feature_alias in features:
                series = features[feature_alias]
                if comparator == "less_than":
                    current = current & (series < threshold).fillna(False)
                else:
                    current = current & (series > threshold).fillna(False)
        elif control.control_type in {"cost_stress", "slippage_stress", "leave_one_out", "parameter_neighborhood"}:
            continue
    return current


def _compile_signal(spec: StrategySpec) -> Callable[[pd.DataFrame, Mapping[str, pd.Series]], pd.Series]:
    entry = spec.signal.entry
    exit_ = spec.signal.exit

    def _raw(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        entry_mask = _apply_controls(_evaluate_condition(entry, features).fillna(False), spec.controls, features)
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


def build_alignment(spec: StrategySpec) -> MechanismImplementationAlignment:
    feature_names = {node.alias or node.primitive for node in spec.feature_nodes}
    strategy_observable = ",".join(sorted(feature_names))
    signal_alignment = "ALIGNED" if feature_names else "NOT_EVALUABLE"
    regime_alignment = "ALIGNED" if "regime" in spec.regime_scope.lower() or not spec.controls else "PARTIALLY_ALIGNED"
    control_alignment = "ALIGNED" if spec.controls else "PARTIALLY_ALIGNED"
    result = "ALIGNED"
    reasons: list[str] = []
    if signal_alignment != "ALIGNED":
        result = "NOT_EVALUABLE"
        reasons.append("missing_signal_features")
    if spec.position_rule.direction != "long_only":
        result = "MISALIGNED"
        reasons.append("non_canonical_direction")
    return MechanismImplementationAlignment(
        predicted_observable=spec.behavior_family,
        strategy_observable=strategy_observable,
        signal_alignment=signal_alignment,
        holding_horizon_alignment="ALIGNED",
        universe_alignment="ALIGNED" if spec.universe else "NOT_EVALUABLE",
        regime_alignment=regime_alignment,
        control_alignment=control_alignment,
        falsification_alignment="ALIGNED",
        alignment_status=result,
        reason_codes=tuple(reasons),
        content_identity=content_id(
            "qmai",
            {
                "strategy_spec_id": spec.strategy_spec_id,
                "signal_alignment": signal_alignment,
                "alignment_status": result,
            },
        ),
    )


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
    alignment = build_alignment(spec)
    verification_status = "VERIFIED" if alignment.alignment_status == "ALIGNED" else "INVALID"
    verification_errors = [] if verification_status == "VERIFIED" else [f"mechanism_alignment:{alignment.alignment_status.lower()}"]
    return {
        "status": verification_status,
        "errors": verification_errors,
        "spec": spec,
        "feature_requirements": requirements,
        "callable": executable,
        "alignment": alignment,
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
    controls: tuple[ControlNode, ...] = (),
    portfolio_rule: PortfolioRule | None = None,
) -> StrategySpec:
    from .strategy_ir import (
        CostAssumption,
        PositionRule,
        normalize_strategy_spec,
    )
    from .strategy_ir import (
        PortfolioRule as IRPortfolioRule,
    )
    from .strategy_ir import (
        StrategySpec as IRStrategySpec,
    )

    spec = IRStrategySpec(
        strategy_spec_id=content_id("qss", {"hypothesis_id": hypothesis_id, "mechanism_family": mechanism_family}),
        grammar_version="1.1",
        hypothesis_id=hypothesis_id,
        mechanism_family=mechanism_family,
        behavior_family=behavior_family,
        universe=universe,
        timeframe=timeframe,
        regime_scope=regime_scope,
        feature_nodes=feature_nodes,
        transforms=(),
        controls=controls,
        signal=signal,
        position_rule=PositionRule(direction="long_only", max_legs=1),
        portfolio_rule=portfolio_rule or IRPortfolioRule(
            weight_semantics="single_strategy_unit_notional",
            selection_semantics="equal_weight",
            max_gross_exposure=1.0,
            max_rules=1,
        ),
        exit_rules=(),
        cost_assumption=CostAssumption(transaction_cost_bps=10.0, slippage_bps=5.0, spread_bps=0.0),
        parameter_schema=parameters,
        content_identity="",
    )
    return normalize_strategy_spec(spec)
