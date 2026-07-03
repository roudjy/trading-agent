from __future__ import annotations

from dataclasses import replace
from typing import Any

from .contracts import (
    AlphaSearchLedger,
    HypothesisCritique,
    MechanisticHypothesis,
    ObservationSnapshot,
    content_id,
    stable_digest,
)


def _lesson_penalty(memory: dict[str, Any], fingerprint: str) -> float:
    lesson = memory.get("lesson") if isinstance(memory, dict) else None
    if not isinstance(lesson, dict):
        return 0.0
    return 1.0 if fingerprint == str(lesson.get("prior_fingerprint") or "") else 0.0


def _proposal(
    *,
    provider_id: str,
    mechanism_family: str,
    behavior_family: str,
    causal_mechanism_statement: str,
    predicted_observable_effect: str,
    expected_direction: str,
    regime_scope: str,
    required_features: tuple[str, ...],
    required_controls: tuple[str, ...],
    falsification_conditions: tuple[str, ...],
    confounders: tuple[str, ...],
    novelty_dimensions: tuple[str, ...],
    support_observation_refs: tuple[str, ...],
    contradicting_observation_refs: tuple[str, ...],
    related_hypotheses: tuple[str, ...],
    parameter_schema: tuple[dict[str, Any], ...],
) -> MechanisticHypothesis:
    payload = {
        "provider_id": provider_id,
        "mechanism_family": mechanism_family,
        "behavior_family": behavior_family,
        "causal_mechanism_statement": causal_mechanism_statement,
        "predicted_observable_effect": predicted_observable_effect,
        "expected_direction": expected_direction,
        "regime_scope": regime_scope,
        "required_features": required_features,
        "required_controls": required_controls,
        "falsification_conditions": falsification_conditions,
        "confounders": confounders,
        "novelty_dimensions": novelty_dimensions,
        "parameter_schema": parameter_schema,
    }
    hypothesis_id = content_id("qah", payload)
    stable_fingerprint = stable_digest(
        {
            "mechanism_family": mechanism_family,
            "behavior_family": behavior_family,
            "causal_mechanism_statement": causal_mechanism_statement,
            "predicted_observable_effect": predicted_observable_effect,
            "universe": "single_asset_liquid_cache_universe",
            "timeframe": "1d",
            "regime_scope": regime_scope,
            "controls": required_controls,
            "falsification_conditions": falsification_conditions,
            "parameter_schema": parameter_schema,
            "required_features": required_features,
        }
    )
    return MechanisticHypothesis(
        hypothesis_id=hypothesis_id,
        schema_version="1.1",
        provider_id=provider_id,
        generation_policy_version="qre_alpha_generation_policy_v2",
        parent_hypothesis_id=None,
        mechanism_family=mechanism_family,
        behavior_family=behavior_family,
        causal_mechanism_statement=causal_mechanism_statement,
        predicted_observable_effect=predicted_observable_effect,
        expected_direction=expected_direction,
        universe_intent="single_asset_liquid_cache_universe",
        timeframe_intent="1d",
        regime_scope=regime_scope,
        required_features=required_features,
        required_controls=required_controls,
        null_hypothesis=f"{predicted_observable_effect} is indistinguishable from null after costs.",
        falsification_conditions=falsification_conditions,
        confounders=confounders,
        minimum_activity_expectation="at least a few signals in discovery history",
        cost_sensitivity_expectation="must survive conservative non-zero slippage",
        support_observation_refs=support_observation_refs,
        contradicting_observation_refs=contradicting_observation_refs,
        related_hypotheses=related_hypotheses,
        related_campaigns=(),
        novelty_dimensions=novelty_dimensions,
        parameter_schema=parameter_schema,
        parameter_count=len(parameter_schema),
        content_identity=content_id("qahp", payload),
        stable_fingerprint=stable_fingerprint,
    )


class DiagnosticAnomalyProvider:
    provider_id = "anomaly"

    def propose(self, observation: ObservationSnapshot, memory: dict[str, Any], budget: int) -> list[MechanisticHypothesis]:
        market = observation.market_diagnostics
        recent_trend = float(market.get("recent_trend") or 0.0)
        recent_vol = float(market.get("recent_volatility") or 0.0)
        refs = (observation.observation_snapshot_id,)
        proposals: list[MechanisticHypothesis] = []
        proposals.append(
            _proposal(
                provider_id=self.provider_id,
                mechanism_family="trend_persistence",
                behavior_family="trend_continuation",
                causal_mechanism_statement="persistent positive trend with still-contained volatility should continue over a short holding horizon.",
                predicted_observable_effect="positive continuation over the next few bars",
                expected_direction="long_only",
                regime_scope="trend_positive_and_volatility_contained",
                required_features=("trend_anchor_delta", "normalized_trend_move"),
                required_controls=("regime_filter", "cost_only_baseline"),
                falsification_conditions=("trend_anchor_delta turns negative", "move falls below entry threshold"),
                confounders=("broad market beta", "calendar drift", "cost drag"),
                novelty_dimensions=("new diagnostic anomaly grounding", "trend continuation"),
                support_observation_refs=refs,
                contradicting_observation_refs=(),
                related_hypotheses=("cross_sectional_momentum_v0",),
                parameter_schema=(
                    {"name": "trend_anchor_window", "type": "int", "value": 50},
                    {"name": "atr_window", "type": "int", "value": 14},
                    {"name": "entry_threshold", "type": "float", "value": 0.75},
                ),
            )
        )
        proposals.append(
            _proposal(
                provider_id=self.provider_id,
                mechanism_family="volatility_breakout",
                behavior_family="compression_release",
                causal_mechanism_statement="volatility compression followed by constructive directional pressure should release into a directional move.",
                predicted_observable_effect="fewer but sharper directional breakouts after compression",
                expected_direction="long_only",
                regime_scope="compression_then_expansion",
                required_features=("compression_ratio", "normalized_trend_move", "rolling_high_previous"),
                required_controls=("regime_filter", "cost_stress"),
                falsification_conditions=("compression ratio remains elevated", "directional move fails to expand"),
                confounders=("event shocks", "news clusters", "beta drift"),
                novelty_dimensions=("volatility clustering change", "diagnostic anomaly grounding"),
                support_observation_refs=refs,
                contradicting_observation_refs=(str(memory.get("lesson", {}).get("actionable_cause") or ""),) if memory.get("lesson") else (),
                related_hypotheses=("volatility_compression_breakout_v0",),
                parameter_schema=(
                    {"name": "atr_short_window", "type": "int", "value": 5},
                    {"name": "atr_long_window", "type": "int", "value": 20},
                    {"name": "compression_threshold", "type": "float", "value": 0.6 if recent_vol <= 0.0 else min(max(recent_vol, 0.3), 0.8)},
                ),
            )
        )
        if recent_trend < 0:
            proposals.reverse()
        return proposals[: min(2, budget)]


class ContradictionFailureProvider:
    provider_id = "contradiction"

    def propose(self, observation: ObservationSnapshot, memory: dict[str, Any], budget: int) -> list[MechanisticHypothesis]:
        lesson = memory.get("lesson") if isinstance(memory, dict) else {}
        if not isinstance(lesson, dict):
            return []
        next_question = str(lesson.get("recommended_next_question") or "")
        if not next_question:
            return []
        refs = (observation.observation_snapshot_id,)
        return [
            _proposal(
                provider_id=self.provider_id,
                mechanism_family="regime_transition",
                behavior_family="regime_conditioned_follow_up",
                causal_mechanism_statement="an effect previously weakened by cost or sparse activity may survive only in a conditioned regime with explicit falsification controls.",
                predicted_observable_effect="effect appears only when the regime filter is active and disappears otherwise",
                expected_direction="long_only",
                regime_scope="regime_conditioned_follow_up",
                required_features=("trend_anchor_delta", "compression_ratio"),
                required_controls=("regime_filter", "leave_one_asset_out", "cost_stress"),
                falsification_conditions=("effect disappears outside conditioned regime", "cost stress removes signal"),
                confounders=("selection bias", "generic market drift", "cost drag"),
                novelty_dimensions=("new contradiction resolution angle", "new falsification control"),
                support_observation_refs=refs,
                contradicting_observation_refs=(next_question,),
                related_hypotheses=(str(lesson.get("hypothesis_id") or ""),),
                parameter_schema=(
                    {"name": "trend_anchor_window", "type": "int", "value": 50},
                    {"name": "compression_window", "type": "int", "value": 20},
                    {"name": "regime_threshold", "type": "float", "value": 0.5},
                ),
            )
        ][: min(1, budget)]


class CoverageMechanismGapProvider:
    provider_id = "coverage"

    def propose(self, observation: ObservationSnapshot, memory: dict[str, Any], budget: int) -> list[MechanisticHypothesis]:
        del memory
        refs = (observation.observation_snapshot_id,)
        return [
            _proposal(
                provider_id=self.provider_id,
                mechanism_family="correlation_change",
                behavior_family="relative_strength_dispersion",
                causal_mechanism_statement="changes in relative strength and dispersion can indicate a regime where broad drift is insufficient to explain cross-instrument separation.",
                predicted_observable_effect="relative-strength leadership persists while laggards remain weak",
                expected_direction="long_only",
                regime_scope="dispersion_expanding",
                required_features=("relative_strength", "dispersion", "cross_sectional_rank"),
                required_controls=("market_beta_proxy_control", "leave_one_asset_out"),
                falsification_conditions=("dispersion contracts immediately", "rank leadership mean reverts before holding horizon"),
                confounders=("market beta", "index concentration", "selection bias"),
                novelty_dimensions=("underexplored mechanism family", "portfolio orthogonality gap"),
                support_observation_refs=refs,
                contradicting_observation_refs=(),
                related_hypotheses=(),
                parameter_schema=(
                    {"name": "lookback", "type": "int", "value": 20},
                    {"name": "top_bucket", "type": "float", "value": 0.2},
                    {"name": "hold_bars", "type": "int", "value": 5},
                ),
            ),
            _proposal(
                provider_id=self.provider_id,
                mechanism_family="liquidity_response",
                behavior_family="activity_conditioned_breakout",
                causal_mechanism_statement="a change in activity/liquidity can mediate whether breakout moves persist or mean revert.",
                predicted_observable_effect="breakout persistence strengthens when activity expands with the move",
                expected_direction="long_only",
                regime_scope="activity_expanding",
                required_features=("compression_ratio", "volume", "normalized_trend_move"),
                required_controls=("cost_stress", "slippage_stress"),
                falsification_conditions=("activity fails to expand", "slippage stress erases effect"),
                confounders=("news shocks", "event drift", "execution friction"),
                novelty_dimensions=("underexplored regime interaction", "new confounder control"),
                support_observation_refs=refs,
                contradicting_observation_refs=(),
                related_hypotheses=(),
                parameter_schema=(
                    {"name": "compression_window", "type": "int", "value": 20},
                    {"name": "activity_window", "type": "int", "value": 10},
                    {"name": "entry_threshold", "type": "float", "value": 0.75},
                ),
            ),
        ][: min(2, budget)]


class MultiProviderHypothesisProvider:
    provider_id = "ensemble"

    def __init__(self) -> None:
        self.providers = (
            DiagnosticAnomalyProvider(),
            ContradictionFailureProvider(),
            CoverageMechanismGapProvider(),
        )

    def propose(self, observation: ObservationSnapshot, memory: dict[str, Any], budget: int) -> list[MechanisticHypothesis]:
        raw: list[MechanisticHypothesis] = []
        for provider in self.providers:
            raw.extend(provider.propose(observation, memory, budget=min(2, budget)))
        deduped: list[MechanisticHypothesis] = []
        seen: set[str] = set()
        for hypothesis in raw:
            if hypothesis.stable_fingerprint in seen:
                continue
            if _lesson_penalty(memory, hypothesis.stable_fingerprint) >= 1.0:
                continue
            seen.add(hypothesis.stable_fingerprint)
            deduped.append(hypothesis)
        return deduped[: min(4, budget)]

    def build_search_ledger(
        self,
        *,
        hypotheses: list[MechanisticHypothesis],
        selected_hypothesis_id: str | None,
        observation: ObservationSnapshot,
        critic_rejections: int,
    ) -> AlphaSearchLedger:
        provider_ids = tuple(sorted({hypothesis.provider_id for hypothesis in hypotheses}))
        return AlphaSearchLedger(
            search_run_id=content_id("qsl", {"observation": observation.content_identity, "selected": selected_hypothesis_id or ""}),
            discovery_dataset_fingerprint=str(observation.data_coverage.get("catalog_content_identity") or observation.content_identity),
            provider_ids=provider_ids,
            raw_proposals=sum(1 for _ in hypotheses),
            deduplicated_proposals=len(hypotheses),
            critic_rejections=critic_rejections,
            policy_rejections=0,
            scored_hypotheses=len(hypotheses),
            selected_hypothesis=selected_hypothesis_id,
            parameter_degrees_of_freedom=sum(h.parameter_count for h in hypotheses),
            feature_degrees_of_freedom=sum(len(h.required_features) for h in hypotheses),
            strategy_tree_count=len(hypotheses),
            prior_related_tests=sum(len(h.related_hypotheses) for h in hypotheses),
            mechanism_family_test_count=len({h.mechanism_family for h in hypotheses}),
            universe_test_count=len({h.universe_intent for h in hypotheses}),
            timeframe_test_count=len({h.timeframe_intent for h in hypotheses}),
            validation_exposures=0,
            OOS_exposures=0,
            content_identity=content_id("qslc", {"providers": provider_ids, "count": len(hypotheses), "selected": selected_hypothesis_id or ""}),
        )


class DeterministicHypothesisCritic:
    def critique(
        self,
        hypothesis: MechanisticHypothesis,
        observation: ObservationSnapshot,
        memory: dict[str, Any],
    ) -> HypothesisCritique:
        del observation, memory
        weaknesses = {
            "trend_persistence": "trend persistence may just be broad market drift.",
            "volatility_breakout": "compression release may be event noise rather than a stable mechanism.",
            "regime_transition": "follow-up may be over-conditioned on a prior failure narrative.",
            "correlation_change": "cross-sectional separation may be market beta in disguise.",
            "liquidity_response": "apparent activity response may be a data-quality or event effect.",
        }
        counter = {
            "trend_persistence": "broad market beta explains the continuation without a distinct mechanism",
            "volatility_breakout": "event-driven gap risk, not compression, explains the move",
            "regime_transition": "the prior effect never existed and regime conditioning only hides the failure",
            "correlation_change": "leadership dispersion is generic drift plus benchmark concentration",
            "liquidity_response": "volume expansion reflects news shocks and adverse selection, not exploitable persistence",
        }
        required_repairs = ("add explicit regime condition", "tighten falsification condition")
        if hypothesis.mechanism_family in {"correlation_change", "liquidity_response"}:
            required_repairs = ("add explicit market-beta control", "tighten falsification condition")
        return HypothesisCritique(
            critique_id=content_id("qac", {"hypothesis_id": hypothesis.hypothesis_id}),
            hypothesis_id=hypothesis.hypothesis_id,
            strongest_counter_hypothesis=counter.get(hypothesis.mechanism_family, "generic market drift explains the effect"),
            mechanism_weaknesses=(weaknesses.get(hypothesis.mechanism_family, "mechanism remains weakly differentiated"),),
            alternative_explanations=("alternative risk premium", "market beta", "regime shift"),
            missing_confounders=("cost drag", "selection bias", "data quality"),
            data_leakage_risks=("discovery-only data must remain frozen before validation",),
            selection_bias_risks=("cache-visible assets can bias proposal generation",),
            survivorship_bias_risks=("single surviving series can overstate stability",),
            data_feasibility_risks=("history may remain insufficient for decisive screening",),
            primitive_gaps=(),
            executor_gaps=(),
            cost_risks=("costs can erase thin effects",),
            activity_risks=("expected signal density may remain too low",),
            overfitting_risks=("multiple hypothesis generation increases search risk",),
            semantic_duplicate_risks=("same mechanism under different phrasing",),
            required_repairs=required_repairs,
            fatal_objections=() if hypothesis.required_features else ("missing_features",),
            content_identity=content_id("qacp", hypothesis.stable_fingerprint),
        )


class DeterministicHypothesisRewriter:
    def revise(self, hypothesis: MechanisticHypothesis, critique: HypothesisCritique) -> MechanisticHypothesis:
        if critique.fatal_objections:
            return hypothesis
        adjusted = replace(
            hypothesis,
            regime_scope=f"{hypothesis.regime_scope}|critic_conditioned",
            required_controls=tuple(dict.fromkeys((*hypothesis.required_controls, "regime_filter"))),
            falsification_conditions=tuple(dict.fromkeys((*hypothesis.falsification_conditions, "explicit_cost_falsification"))),
            novelty_dimensions=tuple(dict.fromkeys((*hypothesis.novelty_dimensions, "critic_rewrite"))),
            parent_hypothesis_id=hypothesis.hypothesis_id,
        )
        payload = adjusted.to_payload()
        return replace(
            adjusted,
            hypothesis_id=content_id("qah", payload),
            content_identity=content_id("qahr", payload),
            stable_fingerprint=stable_digest(
                {
                    "mechanism_family": adjusted.mechanism_family,
                    "behavior_family": adjusted.behavior_family,
                    "causal_mechanism_statement": adjusted.causal_mechanism_statement,
                    "predicted_observable_effect": adjusted.predicted_observable_effect,
                    "universe": adjusted.universe_intent,
                    "timeframe": adjusted.timeframe_intent,
                    "regime_scope": adjusted.regime_scope,
                    "controls": adjusted.required_controls,
                    "falsification_conditions": adjusted.falsification_conditions,
                    "parameter_schema": adjusted.parameter_schema,
                    "required_features": adjusted.required_features,
                }
            ),
        )
