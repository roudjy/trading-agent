from __future__ import annotations

from dataclasses import replace
from typing import Any

from .contracts import (
    DiscoveryContext,
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
    repeated = fingerprint == str(lesson.get("prior_fingerprint") or "")
    if repeated:
        return 1.0
    return 0.0


def _h(
    *,
    provider_id: str,
    generation_policy_version: str,
    parent_hypothesis_id: str | None,
    mechanism_family: str,
    behavior_family: str,
    causal_mechanism_statement: str,
    predicted_observable_effect: str,
    expected_direction: str,
    universe_intent: str,
    timeframe_intent: str,
    regime_scope: str,
    required_features: tuple[str, ...],
    required_controls: tuple[str, ...],
    null_hypothesis: str,
    falsification_conditions: tuple[str, ...],
    confounders: tuple[str, ...],
    minimum_activity_expectation: str,
    cost_sensitivity_expectation: str,
    support_observation_refs: tuple[str, ...],
    contradicting_observation_refs: tuple[str, ...],
    related_hypotheses: tuple[str, ...],
    related_campaigns: tuple[str, ...],
    novelty_dimensions: tuple[str, ...],
    parameter_schema: tuple[dict[str, Any], ...],
) -> MechanisticHypothesis:
    payload = {
        "provider_id": provider_id,
        "generation_policy_version": generation_policy_version,
        "parent_hypothesis_id": parent_hypothesis_id,
        "mechanism_family": mechanism_family,
        "behavior_family": behavior_family,
        "causal_mechanism_statement": causal_mechanism_statement,
        "predicted_observable_effect": predicted_observable_effect,
        "expected_direction": expected_direction,
        "universe_intent": universe_intent,
        "timeframe_intent": timeframe_intent,
        "regime_scope": regime_scope,
        "required_features": required_features,
        "required_controls": required_controls,
        "null_hypothesis": null_hypothesis,
        "falsification_conditions": falsification_conditions,
        "confounders": confounders,
        "minimum_activity_expectation": minimum_activity_expectation,
        "cost_sensitivity_expectation": cost_sensitivity_expectation,
        "support_observation_refs": support_observation_refs,
        "contradicting_observation_refs": contradicting_observation_refs,
        "related_hypotheses": related_hypotheses,
        "related_campaigns": related_campaigns,
        "novelty_dimensions": novelty_dimensions,
        "parameter_schema": parameter_schema,
    }
    hypothesis_id = content_id("qah", payload)
    stable_fingerprint = stable_digest(
        {
            "mechanism_family": mechanism_family,
            "behavior_family": behavior_family,
            "causal_mechanism_statement": causal_mechanism_statement,
            "universe_intent": universe_intent,
            "timeframe_intent": timeframe_intent,
            "regime_scope": regime_scope,
            "required_features": required_features,
            "required_controls": required_controls,
            "null_hypothesis": null_hypothesis,
            "falsification_conditions": falsification_conditions,
            "parameter_schema": parameter_schema,
        }
    )
    return MechanisticHypothesis(
        hypothesis_id=hypothesis_id,
        schema_version="1.0",
        provider_id=provider_id,
        generation_policy_version=generation_policy_version,
        parent_hypothesis_id=parent_hypothesis_id,
        mechanism_family=mechanism_family,
        behavior_family=behavior_family,
        causal_mechanism_statement=causal_mechanism_statement,
        predicted_observable_effect=predicted_observable_effect,
        expected_direction=expected_direction,
        universe_intent=universe_intent,
        timeframe_intent=timeframe_intent,
        regime_scope=regime_scope,
        required_features=required_features,
        required_controls=required_controls,
        null_hypothesis=null_hypothesis,
        falsification_conditions=falsification_conditions,
        confounders=confounders,
        minimum_activity_expectation=minimum_activity_expectation,
        cost_sensitivity_expectation=cost_sensitivity_expectation,
        support_observation_refs=support_observation_refs,
        contradicting_observation_refs=contradicting_observation_refs,
        related_hypotheses=related_hypotheses,
        related_campaigns=related_campaigns,
        novelty_dimensions=novelty_dimensions,
        parameter_schema=parameter_schema,
        parameter_count=len(parameter_schema),
        content_identity=content_id("qahp", payload),
        stable_fingerprint=stable_fingerprint,
    )


class DeterministicMechanisticHypothesisProvider:
    provider_id = "deterministic_mechanistic_hypothesis_provider"
    generation_policy_version = "qre_alpha_generation_policy_v1"

    def propose(
        self,
        observation: ObservationSnapshot,
        memory: dict[str, Any],
        budget: int,
    ) -> list[MechanisticHypothesis]:
        base_refs = (observation.observation_snapshot_id,)
        memory_note = str(memory.get("lesson", {}).get("actionable_cause") or "")
        hypotheses = [
            _h(
                provider_id=self.provider_id,
                generation_policy_version=self.generation_policy_version,
                parent_hypothesis_id=None,
                mechanism_family="trend_persistence",
                behavior_family="trend_continuation",
                causal_mechanism_statement="trend persistence should continue when an anchored trend remains positive and volatility-normalised move stays elevated.",
                predicted_observable_effect="positive continuation with modest holding periods",
                expected_direction="long_only",
                universe_intent="single_asset_liquid_cache_universe",
                timeframe_intent="1d",
                regime_scope="trend_or_expanding_volatility",
                required_features=("trend_anchor", "trend_anchor_delta", "normalized_trend_move"),
                required_controls=("cost_only_baseline", "null_hold_baseline"),
                null_hypothesis="positive anchored trend does not predict forward continuation after costs.",
                falsification_conditions=(
                    "trend_anchor_delta turns negative before trade horizon",
                    "normalized_trend_move stays below entry threshold",
                ),
                confounders=("broad market drift", "simple momentum crowding", "cost drag"),
                minimum_activity_expectation="at least a few aligned signals in the selected history",
                cost_sensitivity_expectation="moderate; should tolerate small costs but not heavy turnover",
                support_observation_refs=base_refs,
                contradicting_observation_refs=(),
                related_hypotheses=("cross_sectional_momentum_v0",),
                related_campaigns=(),
                novelty_dimensions=("anchored trend with volatility-normalised continuation",),
                parameter_schema=(
                    {"name": "trend_anchor_window", "type": "int", "value": 50},
                    {"name": "atr_window", "type": "int", "value": 14},
                    {"name": "entry_threshold", "type": "float", "value": 0.75},
                ),
            ),
            _h(
                provider_id=self.provider_id,
                generation_policy_version=self.generation_policy_version,
                parent_hypothesis_id=None,
                mechanism_family="volatility_breakout",
                behavior_family="compression_release",
                causal_mechanism_statement="compression should precede directional release when short-term volatility is suppressed and the trend-normalised move is constructive.",
                predicted_observable_effect="a breakout after compression with fewer but sharper trades",
                expected_direction="long_only",
                universe_intent="single_asset_liquid_cache_universe",
                timeframe_intent="1d",
                regime_scope="compression_then_expansion",
                required_features=("compression_ratio", "normalized_trend_move", "rolling_high_previous"),
                required_controls=("null_hold_baseline", "cost_only_baseline"),
                null_hypothesis="volatility compression does not improve forward breakout expectancy after costs.",
                falsification_conditions=(
                    "compression ratio remains above threshold",
                    "normalized_trend_move fails to expand after entry",
                ),
                confounders=("event-driven jumps", "calendar effects", "survivorship bias"),
                minimum_activity_expectation="activity can be sparse but should not be absent",
                cost_sensitivity_expectation="high; breakout edge weakens quickly with cost drag",
                support_observation_refs=base_refs,
                contradicting_observation_refs=(memory_note,) if memory_note else (),
                related_hypotheses=("volatility_compression_breakout_v0",),
                related_campaigns=(),
                novelty_dimensions=("volatility compression release relation",),
                parameter_schema=(
                    {"name": "atr_short_window", "type": "int", "value": 5},
                    {"name": "atr_long_window", "type": "int", "value": 20},
                    {"name": "compression_threshold", "type": "float", "value": 0.6},
                ),
            ),
            _h(
                provider_id=self.provider_id,
                generation_policy_version=self.generation_policy_version,
                parent_hypothesis_id=None,
                mechanism_family="mean_reversion",
                behavior_family="overextension_reversion",
                causal_mechanism_statement="short-horizon overextension should mean revert when z-scores are extreme and volatility is not collapsing.",
                predicted_observable_effect="contrarian recovery after extended move",
                expected_direction="long_only",
                universe_intent="single_asset_liquid_cache_universe",
                timeframe_intent="1d",
                regime_scope="overextended_and_stable_liquidity",
                required_features=("zscore", "rolling_volatility", "log_returns"),
                required_controls=("null_hold_baseline", "cost_only_baseline"),
                null_hypothesis="extreme z-score does not predict forward reversal after costs.",
                falsification_conditions=(
                    "zscore fails to revert toward zero",
                    "rolling volatility collapses into invalid data",
                ),
                confounders=("news shocks", "trend continuation", "volatility clustering"),
                minimum_activity_expectation="moderate signal frequency",
                cost_sensitivity_expectation="moderate; fewer trades should reduce cost pressure",
                support_observation_refs=base_refs,
                contradicting_observation_refs=(),
                related_hypotheses=("pairs_zscore_strategie",),
                related_campaigns=(),
                novelty_dimensions=("extreme move reversion",),
                parameter_schema=(
                    {"name": "lookback", "type": "int", "value": 20},
                    {"name": "entry_z", "type": "float", "value": -1.5},
                    {"name": "exit_z", "type": "float", "value": -0.25},
                ),
            ),
        ]
        scored: list[tuple[float, MechanisticHypothesis]] = []
        for hypothesis in hypotheses[: max(1, budget)]:
            penalty = _lesson_penalty(memory, hypothesis.stable_fingerprint)
            if penalty >= 1.0:
                continue
            scored.append((1.0 - penalty, hypothesis))
        scored.sort(key=lambda item: (-item[0], item[1].hypothesis_id))
        return [hypothesis for _, hypothesis in scored[:budget]]


class DeterministicHypothesisCritic:
    def critique(
        self,
        hypothesis: MechanisticHypothesis,
        observation: ObservationSnapshot,
        memory: dict[str, Any],
    ) -> HypothesisCritique:
        weaknesses = []
        if hypothesis.mechanism_family == "trend_persistence":
            weaknesses.append("trend persistence can be a proxy for broad drift rather than a mechanism.")
        elif hypothesis.mechanism_family == "volatility_breakout":
            weaknesses.append("compression releases are often event driven and may be unstable across regimes.")
        else:
            weaknesses.append("mean reversion can be dominated by trend continuation and cost drag.")
        return HypothesisCritique(
            critique_id=content_id("qac", {"hypothesis_id": hypothesis.hypothesis_id, "observation": observation.content_identity}),
            hypothesis_id=hypothesis.hypothesis_id,
            strongest_counter_hypothesis=f"the apparent effect is explained by {hypothesis.mechanism_family.replace('_', ' ')} noise rather than the claimed causal mechanism",
            mechanism_weaknesses=tuple(weaknesses),
            alternative_explanations=("cost drag", "calendar bias", "broad market drift"),
            missing_confounders=("market regime", "transaction costs", "selection bias"),
            data_leakage_risks=("none from ex-ante snapshot, but the hypothesis must remain frozen",),
            selection_bias_risks=("selection on visible cache coverage",),
            survivorship_bias_risks=("ready cache may omit unavailable series",),
            data_feasibility_risks=("history may be too short for decisive OOS separation",),
            primitive_gaps=tuple(),
            executor_gaps=tuple(),
            cost_risks=("higher turnover can erase signal edge",),
            activity_risks=("sparse activity can leave the signal underpowered",),
            overfitting_risks=("parameter freedom must stay at three or fewer",),
            semantic_duplicate_risks=("near-duplicate to prior mechanism family",),
            required_repairs=(
                "add an explicit regime condition",
                "tighten falsification conditions",
            ),
            fatal_objections=tuple(),
            content_identity=content_id("qacp", hypothesis.stable_fingerprint),
        )


class DeterministicHypothesisRewriter:
    def revise(
        self,
        hypothesis: MechanisticHypothesis,
        critique: HypothesisCritique,
    ) -> MechanisticHypothesis:
        repairs = set(critique.required_repairs)
        if not repairs:
            return hypothesis
        adjusted = replace(
            hypothesis,
            regime_scope=f"{hypothesis.regime_scope}|regime_conditioned",
            required_controls=tuple(dict.fromkeys((*hypothesis.required_controls, "regime_filter"))),
            falsification_conditions=tuple(dict.fromkeys((*hypothesis.falsification_conditions, "explicit_cost_falsification"))),
            novelty_dimensions=tuple(dict.fromkeys((*hypothesis.novelty_dimensions, "regime_conditioning"))),
            parameter_schema=tuple(list(hypothesis.parameter_schema)[:3]),
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
                    "universe_intent": adjusted.universe_intent,
                    "timeframe_intent": adjusted.timeframe_intent,
                    "regime_scope": adjusted.regime_scope,
                    "required_features": adjusted.required_features,
                    "required_controls": adjusted.required_controls,
                    "null_hypothesis": adjusted.null_hypothesis,
                    "falsification_conditions": adjusted.falsification_conditions,
                    "parameter_schema": adjusted.parameter_schema,
                }
            ),
        )
