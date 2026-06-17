"""Canonical QRE behavior catalog.

This module defines the research-intelligence taxonomy for market
behaviors. It is context-only: it does not create strategy authority,
does not authorize execution, and does not clear evidence blockers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal


BehaviorStatus = Literal["active", "provisional", "deprecated", "blocked"]

BEHAVIOR_CATALOG_SCHEMA_VERSION: Final[str] = "1.0"


@dataclass(frozen=True)
class BehaviorFamily:
    behavior_id: str
    display_name: str
    description: str
    expected_observables: tuple[str, ...]
    typical_timeframes: tuple[str, ...]
    compatible_preset_patterns: tuple[str, ...]
    required_data_capabilities: tuple[str, ...]
    common_failure_modes: tuple[str, ...]
    forbidden_interpretations: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    status: BehaviorStatus

    def to_payload(self) -> dict[str, Any]:
        return {
            "behavior_id": self.behavior_id,
            "display_name": self.display_name,
            "description": self.description,
            "expected_observables": list(self.expected_observables),
            "typical_timeframes": list(self.typical_timeframes),
            "compatible_preset_patterns": list(self.compatible_preset_patterns),
            "required_data_capabilities": list(self.required_data_capabilities),
            "common_failure_modes": list(self.common_failure_modes),
            "forbidden_interpretations": list(self.forbidden_interpretations),
            "evidence_requirements": list(self.evidence_requirements),
            "status": self.status,
        }


BEHAVIOR_CATALOG: Final[tuple[BehaviorFamily, ...]] = (
    BehaviorFamily(
        behavior_id="trend_continuation",
        display_name="Trend Continuation",
        description=(
            "Price continues in the direction of an established trend after "
            "a bounded consolidation or minor retracement."
        ),
        expected_observables=(
            "higher_highs_or_lower_lows",
            "trend_aligned_breakout_follow_through",
            "compression_then_expansion",
        ),
        typical_timeframes=("1d", "4h", "1h"),
        compatible_preset_patterns=("trend_*", "*continuation*", "*breakout*"),
        required_data_capabilities=(
            "time_series_ohlcv",
            "regime_context",
            "cost_model",
        ),
        common_failure_modes=(
            "trend_exhaustion",
            "late_entry",
            "mean_reversion_snapback",
        ),
        forbidden_interpretations=(
            "guaranteed_alpha",
            "execution_authorization",
            "candidate_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="pullback_continuation",
        display_name="Pullback Continuation",
        description=(
            "Temporary retracement within a trend resolves and resumes the "
            "prior directional move."
        ),
        expected_observables=(
            "retracement_into_trend_zone",
            "support_or_resistance_reclaim",
            "post_pullback_expansion",
        ),
        typical_timeframes=("1d", "4h"),
        compatible_preset_patterns=("trend_pullback*", "*reclaim*", "*retracement*"),
        required_data_capabilities=(
            "time_series_ohlcv",
            "trend_context",
            "cost_model",
        ),
        common_failure_modes=(
            "pullback_becomes_reversal",
            "insufficient_trades",
            "cost_fragility",
        ),
        forbidden_interpretations=(
            "guaranteed_rebound",
            "strategy_registration",
            "campaign_launch_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="volatility_compression_breakout",
        display_name="Volatility Compression Breakout",
        description=(
            "Compressed volatility resolves into expansion with a directional "
            "breakout after a bounded consolidation."
        ),
        expected_observables=(
            "narrow_range_compression",
            "range_break_or_gap",
            "post_breakout_expansion",
        ),
        typical_timeframes=("1d", "4h"),
        compatible_preset_patterns=("vol_compression*", "*breakout*", "*expansion*"),
        required_data_capabilities=(
            "time_series_ohlcv",
            "volatility_measurements",
            "cost_model",
        ),
        common_failure_modes=(
            "false_breakout",
            "whipsaw",
            "liquidity_thinness",
        ),
        forbidden_interpretations=(
            "signal_to_trade_without_validation",
            "proof_of_edge",
            "candidate_promotion_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="relative_strength",
        display_name="Relative Strength",
        description=(
            "A basket or symbol outperforms a peer set or benchmark across a "
            "bounded window."
        ),
        expected_observables=(
            "benchmark_relative_outperformance",
            "peer_rank_persistence",
            "leadership_retention",
        ),
        typical_timeframes=("1d", "1w", "4h"),
        compatible_preset_patterns=("relative_strength*", "*leader*", "*outperform*"),
        required_data_capabilities=(
            "cross_sectional_prices",
            "benchmark_series",
            "cost_model",
        ),
        common_failure_modes=(
            "benchmark_instability",
            "narrow_sample",
            "regime_shift",
        ),
        forbidden_interpretations=(
            "portfolio_allocation_authority",
            "execution_authority",
            "alpha_proof_without_oos",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="post_shock_stabilization",
        display_name="Post-Shock Stabilization",
        description=(
            "After a shock event, price action compresses and stabilizes "
            "before choosing a direction."
        ),
        expected_observables=(
            "shock_gap_or_spike",
            "volatility_decay",
            "range_contraction",
        ),
        typical_timeframes=("1d", "4h"),
        compatible_preset_patterns=("post_shock*", "*stabilization*", "*recovery*"),
        required_data_capabilities=(
            "event_context",
            "time_series_ohlcv",
            "cost_model",
        ),
        common_failure_modes=(
            "continuing_dislocation",
            "news_driven_instability",
            "thin_liquidity",
        ),
        forbidden_interpretations=(
            "shock_recovery_assurance",
            "strategy_synthesis_authority",
            "live_trading_permission",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="index_regime_filter",
        display_name="Index Regime Filter",
        description=(
            "Broad index regime state informs whether a tighter research or "
            "sampling path is appropriate."
        ),
        expected_observables=(
            "index_trend_state",
            "breadth_pressure",
            "regime_shift_signal",
        ),
        typical_timeframes=("1d", "1w"),
        compatible_preset_patterns=("index_*", "*regime*", "*filter*"),
        required_data_capabilities=(
            "index_series",
            "breadth_context",
            "cost_model",
        ),
        common_failure_modes=(
            "regime_label_drift",
            "broad_market_noise",
            "sample_misalignment",
        ),
        forbidden_interpretations=(
            "trade_signal_on_its_own",
            "campaign_authority",
            "candidate_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="mean_reversion",
        display_name="Mean Reversion",
        description=(
            "Transient deviations revert toward a local mean after bounded "
            "extreme moves or overextension."
        ),
        expected_observables=(
            "overshoot_then_revert",
            "extreme_distance_from_mean",
            "fade_then_normalize",
        ),
        typical_timeframes=("1d", "4h", "1h"),
        compatible_preset_patterns=("mean_reversion*", "*fade*", "*revert*"),
        required_data_capabilities=(
            "time_series_ohlcv",
            "mean_reversion_context",
            "cost_model",
        ),
        common_failure_modes=(
            "trend_regime_inversion",
            "cost_fragility",
            "tail_risk",
        ),
        forbidden_interpretations=(
            "guaranteed_recovery",
            "alpha_proof_without_oos",
            "deployment_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="provisional",
    ),
    BehaviorFamily(
        behavior_id="momentum_acceleration",
        display_name="Momentum Acceleration",
        description=(
            "Momentum strengthens over a bounded window, often with rising "
            "participation or volatility."
        ),
        expected_observables=(
            "range_expansion",
            "increasing_slope",
            "participation_strength",
        ),
        typical_timeframes=("1d", "4h"),
        compatible_preset_patterns=("momentum*", "*acceleration*", "*impulse*"),
        required_data_capabilities=(
            "time_series_ohlcv",
            "participation_context",
            "cost_model",
        ),
        common_failure_modes=(
            "late_entry",
            "exhaustion_move",
            "whipsaw",
        ),
        forbidden_interpretations=(
            "strategy_authority",
            "execution_authority",
            "candidate_promotion_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="active",
    ),
    BehaviorFamily(
        behavior_id="defensive_rotation",
        display_name="Defensive Rotation",
        description=(
            "Risk-off style rotation into defensive exposures during stress or "
            "uncertainty."
        ),
        expected_observables=(
            "relative_defensive_strength",
            "risk_off_breadth",
            "rotation_persistence",
        ),
        typical_timeframes=("1d", "1w"),
        compatible_preset_patterns=("defensive_rotation*", "*defensive*", "*risk_off*"),
        required_data_capabilities=(
            "cross_sectional_prices",
            "sector_context",
            "cost_model",
        ),
        common_failure_modes=(
            "regime_flip",
            "benchmark_mismatch",
            "sector_concentration",
        ),
        forbidden_interpretations=(
            "capital_allocation_authority",
            "live_permission",
            "risk_override",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="provisional",
    ),
    BehaviorFamily(
        behavior_id="liquidity_stress_response",
        display_name="Liquidity Stress Response",
        description=(
            "Price and spread behavior under stress, thin liquidity, or "
            "market microstructure strain."
        ),
        expected_observables=(
            "widened_spread_proxy",
            "gap_or_slippage_stress",
            "microstructure_instability",
        ),
        typical_timeframes=("1d", "4h", "1h"),
        compatible_preset_patterns=("liquidity*", "*stress*", "*microstructure*"),
        required_data_capabilities=(
            "microstructure_context",
            "time_series_ohlcv",
            "cost_model",
        ),
        common_failure_modes=(
            "thin_liquidity",
            "cost_blindness",
            "data_instability",
        ),
        forbidden_interpretations=(
            "trade_signal_on_its_own",
            "execution_authority",
            "provider_activation_authority",
        ),
        evidence_requirements=(
            "screening_evidence",
            "oos_evidence",
            "lineage_evidence",
        ),
        status="blocked",
    ),
)

_BEHAVIOR_BY_ID: Final[dict[str, BehaviorFamily]] = {
    behavior.behavior_id: behavior for behavior in BEHAVIOR_CATALOG
}


def list_behavior_families() -> tuple[BehaviorFamily, ...]:
    return BEHAVIOR_CATALOG


def get_behavior_family(behavior_id: str) -> BehaviorFamily:
    try:
        return _BEHAVIOR_BY_ID[behavior_id]
    except KeyError as exc:
        raise KeyError(f"unknown behavior_id: {behavior_id!r}") from exc

