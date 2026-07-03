from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import canonical_payload, content_id, stable_digest

GRAMMAR_VERSION = "1.1"
MAX_AST_NODES = 16
MAX_PARAMETERS = 4
MAX_FEATURE_BRANCHES = 3
MAX_CONTROLS = 3
MAX_REGIME_FILTERS = 1
MAX_PORTFOLIO_RULES = 1
MAX_EXIT_RULES = 1

ALLOWED_PRIMITIVES = {
    "atr",
    "compression_ratio",
    "cross_sectional_rank",
    "dispersion",
    "drawdown",
    "lagged_return",
    "log_returns",
    "normalized_trend_move",
    "pullback_distance",
    "realized_volatility",
    "relative_strength",
    "rolling_correlation",
    "rolling_high_previous",
    "rolling_low_previous",
    "rolling_mean",
    "rolling_median",
    "rolling_standard_deviation",
    "rolling_volatility",
    "spread_zscore",
    "time_series_rank",
    "trend_anchor",
    "trend_anchor_delta",
    "zscore",
}

ALLOWED_OPERATORS = {
    "greater_than",
    "less_than",
    "between",
    "and",
    "or",
    "not",
    "crosses_above",
    "crosses_below",
}

ALLOWED_TRANSFORMS = {
    "lag",
    "difference",
    "ratio",
    "normalize",
    "rank",
    "winsorize",
    "demean",
    "volatility_scale",
}

ALLOWED_CONTROL_TYPES = {
    "regime_filter",
    "market_beta_proxy_control",
    "sector_group_control",
    "leave_one_out",
    "cost_stress",
    "slippage_stress",
    "parameter_neighborhood",
}

ALLOWED_PORTFOLIO_SEMANTICS = {
    "equal_weight",
    "rank_weight",
    "single_strategy_unit_notional",
}

ALLOWED_BUCKET_SEMANTICS = {
    "top_bucket",
    "bottom_bucket",
    "relative_to_universe",
    "leave_one_out",
}


@dataclass(frozen=True, slots=True)
class FeatureNode:
    primitive: str
    params: dict[str, Any] = field(default_factory=dict)
    alias: str | None = None
    source_field: str = "close"


@dataclass(frozen=True, slots=True)
class TransformNode:
    operator: str
    input_alias: str
    output_alias: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConditionNode:
    operator: str
    left: Any
    right: Any | None = None


@dataclass(frozen=True, slots=True)
class SignalNode:
    entry: ConditionNode
    exit: ConditionNode
    direction: str = "long_only"


@dataclass(frozen=True, slots=True)
class PositionRule:
    direction: str = "long_only"
    max_legs: int = 1


@dataclass(frozen=True, slots=True)
class PortfolioRule:
    weight_semantics: str = "single_strategy_unit_notional"
    selection_semantics: str = "equal_weight"
    max_gross_exposure: float = 1.0
    max_rules: int = 1


@dataclass(frozen=True, slots=True)
class ExitRule:
    operator: str
    threshold: Any


@dataclass(frozen=True, slots=True)
class ControlNode:
    control_type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CostAssumption:
    transaction_cost_bps: float = 0.0
    slippage_bps: float = 0.0
    spread_bps: float = 0.0


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_spec_id: str
    grammar_version: str
    hypothesis_id: str
    mechanism_family: str
    behavior_family: str
    universe: str
    timeframe: str
    regime_scope: str
    feature_nodes: tuple[FeatureNode, ...]
    transforms: tuple[TransformNode, ...]
    controls: tuple[ControlNode, ...]
    signal: SignalNode
    position_rule: PositionRule
    portfolio_rule: PortfolioRule
    exit_rules: tuple[ExitRule, ...]
    cost_assumption: CostAssumption
    parameter_schema: tuple[dict[str, Any], ...]
    content_identity: str

    def to_payload(self) -> dict[str, Any]:
        return canonical_payload(self)


def _normalize_condition(value: Any) -> Any:
    if isinstance(value, ConditionNode):
        left = _normalize_condition(value.left)
        right = _normalize_condition(value.right)
        if value.operator in {"and", "or"} and right is not None:
            operands = sorted([left, right], key=lambda item: stable_digest(canonical_payload(item)))
            return ConditionNode(operator=value.operator, left=operands[0], right=operands[1])
        return ConditionNode(operator=value.operator, left=left, right=right)
    if isinstance(value, FeatureNode):
        return FeatureNode(
            primitive=value.primitive,
            params=dict(sorted(value.params.items())),
            alias=value.alias,
            source_field=value.source_field,
        )
    if isinstance(value, TransformNode):
        return TransformNode(
            operator=value.operator,
            input_alias=value.input_alias,
            output_alias=value.output_alias,
            params=dict(sorted(value.params.items())),
        )
    if isinstance(value, SignalNode):
        return SignalNode(
            entry=_normalize_condition(value.entry),
            exit=_normalize_condition(value.exit),
            direction=value.direction,
        )
    if isinstance(value, ControlNode):
        return ControlNode(control_type=value.control_type, params=dict(sorted(value.params.items())))
    if isinstance(value, tuple):
        return tuple(_normalize_condition(item) for item in value)
    return value


def normalize_strategy_spec(spec: StrategySpec) -> StrategySpec:
    normalized = StrategySpec(
        strategy_spec_id=spec.strategy_spec_id,
        grammar_version=spec.grammar_version,
        hypothesis_id=spec.hypothesis_id,
        mechanism_family=spec.mechanism_family,
        behavior_family=spec.behavior_family,
        universe=spec.universe,
        timeframe=spec.timeframe,
        regime_scope=spec.regime_scope,
        feature_nodes=tuple(
            sorted(
                (
                    FeatureNode(
                        primitive=node.primitive,
                        params=dict(sorted(node.params.items())),
                        alias=node.alias,
                        source_field=node.source_field,
                    )
                    for node in spec.feature_nodes
                ),
                key=lambda node: (
                    node.primitive,
                    node.alias or "",
                    node.source_field,
                    stable_digest(node.params),
                ),
            )
        ),
        transforms=tuple(
            sorted(
                (
                    TransformNode(
                        operator=node.operator,
                        input_alias=node.input_alias,
                        output_alias=node.output_alias,
                        params=dict(sorted(node.params.items())),
                    )
                    for node in spec.transforms
                ),
                key=lambda node: (node.operator, node.input_alias, node.output_alias, stable_digest(node.params)),
            )
        ),
        controls=tuple(
            sorted(
                (
                    ControlNode(control_type=node.control_type, params=dict(sorted(node.params.items())))
                    for node in spec.controls
                ),
                key=lambda node: (node.control_type, stable_digest(node.params)),
            )
        ),
        signal=_normalize_condition(spec.signal),
        position_rule=spec.position_rule,
        portfolio_rule=spec.portfolio_rule,
        exit_rules=tuple(
            sorted((ExitRule(operator=node.operator, threshold=node.threshold) for node in spec.exit_rules), key=lambda node: (node.operator, stable_digest(node.threshold)))
        ),
        cost_assumption=spec.cost_assumption,
        parameter_schema=tuple(
            sorted((dict(sorted(item.items())) for item in spec.parameter_schema), key=lambda item: str(item.get("name") or ""))
        ),
        content_identity="",
    )
    payload = canonical_payload(normalized)
    object.__setattr__(normalized, "content_identity", content_id("qasd", payload))
    object.__setattr__(normalized, "strategy_spec_id", spec.strategy_spec_id)
    return normalized


def validate_strategy_spec(spec: StrategySpec) -> list[str]:
    errors: list[str] = []
    if spec.grammar_version != GRAMMAR_VERSION:
        errors.append("unsupported_grammar_version")
    total_nodes = 1 + len(spec.feature_nodes) + len(spec.transforms) + len(spec.controls) + 1 + len(spec.exit_rules) + 1
    if total_nodes > MAX_AST_NODES:
        errors.append("ast_node_limit_exceeded")
    if len(spec.parameter_schema) > MAX_PARAMETERS:
        errors.append("parameter_limit_exceeded")
    if len(spec.feature_nodes) > MAX_FEATURE_BRANCHES:
        errors.append("feature_branch_limit_exceeded")
    if len(spec.controls) > MAX_CONTROLS:
        errors.append("control_limit_exceeded")
    if len(spec.exit_rules) > MAX_EXIT_RULES:
        errors.append("exit_rule_limit_exceeded")
    if len(spec.feature_nodes) == 0:
        errors.append("missing_features")
    if spec.portfolio_rule.max_rules > MAX_PORTFOLIO_RULES:
        errors.append("portfolio_rule_limit_exceeded")
    if spec.portfolio_rule.selection_semantics not in ALLOWED_PORTFOLIO_SEMANTICS | ALLOWED_BUCKET_SEMANTICS:
        errors.append(f"unsupported_portfolio_semantics:{spec.portfolio_rule.selection_semantics}")
    for feature in spec.feature_nodes:
        if feature.primitive not in ALLOWED_PRIMITIVES:
            errors.append(f"unsupported_primitive:{feature.primitive}")
    for transform in spec.transforms:
        if transform.operator not in ALLOWED_TRANSFORMS:
            errors.append(f"unsupported_transform:{transform.operator}")
    for control in spec.controls:
        if control.control_type not in ALLOWED_CONTROL_TYPES:
            errors.append(f"unsupported_control:{control.control_type}")
    for exit_rule in spec.exit_rules:
        if exit_rule.operator not in ALLOWED_OPERATORS:
            errors.append(f"unsupported_exit_operator:{exit_rule.operator}")
    return errors
