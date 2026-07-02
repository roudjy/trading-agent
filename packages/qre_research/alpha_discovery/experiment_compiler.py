from __future__ import annotations

from .contracts import ExperimentContract, MechanisticHypothesis, content_id


class CanonicalExperimentPlanner:
    def plan(self, hypothesis: MechanisticHypothesis) -> ExperimentContract:
        required_fields = tuple(sorted({"open", "high", "low", "close", "volume"}))
        required_features = hypothesis.required_features
        return ExperimentContract(
            experiment_id=content_id("qexp", {"hypothesis_id": hypothesis.hypothesis_id, "mechanism": hypothesis.mechanism_family}),
            hypothesis_id=hypothesis.hypothesis_id,
            research_question=f"Does {hypothesis.causal_mechanism_statement} produce {hypothesis.predicted_observable_effect}?",
            predicted_observable=hypothesis.predicted_observable_effect,
            counter_hypothesis=f"Alternative explanation: {hypothesis.mechanism_family} is spurious.",
            universe_spec=hypothesis.universe_intent,
            timeframe=hypothesis.timeframe_intent,
            sampling_frequency=hypothesis.timeframe_intent,
            required_data_fields=required_fields,
            required_history="one continuous ready cache window",
            required_point_in_time_metadata=("timestamp_utc",),
            required_features=required_features,
            signal_semantics=hypothesis.behavior_family,
            position_semantics=hypothesis.expected_direction,
            entry_semantics="frozen deterministic entry condition",
            exit_semantics="frozen deterministic exit condition",
            portfolio_semantics="single-strategy unit-notional research only",
            null_models=("null_hold", "cost_only"),
            falsification_tests=hypothesis.falsification_conditions,
            confounder_controls=hypothesis.required_controls,
            transaction_cost_model="canonical_fixed_cost_proxy",
            slippage_model="canonical_zero_slippage_proxy",
            IS_policy="bounded in-sample only",
            validation_policy="no OOS selection",
            locked_OOS_policy="static window if available, else unavailable",
            embargo_policy="short embargo around boundary bars",
            warmup_policy="use primitive warmup requirements",
            minimum_signal_count=1,
            minimum_trade_count=1,
            success_criteria=("supports_mechanism", "evidence_is_not_null"),
            failure_criteria=("no_activity", "negative_after_costs", "support_lost"),
            required_evidence_families=("controlled_evaluation", "transaction_costs", "null_comparison"),
            content_identity=content_id("qexpc", {"hypothesis": hypothesis.hypothesis_id, "features": required_features}),
        )

