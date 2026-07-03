from __future__ import annotations

from .contracts import (
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EvidenceAssessment,
    ExperimentAdmissionDecision,
    HypothesisCritique,
    HypothesisScorecard,
    ObservationSnapshot,
    content_id,
)


def _score_component(base: float, bonus: float = 0.0, penalty: float = 0.0) -> float:
    return max(0.0, min(1.0, base + bonus - penalty))


class DeterministicExAnteEvaluator:
    weights = {
        "mechanistic_clarity": 0.12,
        "falsifiability": 0.14,
        "novelty": 0.10,
        "observation_grounding": 0.10,
        "data_feasibility": 0.10,
        "identity_readiness": 0.05,
        "primitive_readiness": 0.05,
        "executor_readiness": 0.05,
        "confounder_coverage": 0.08,
        "leakage_safety": 0.10,
        "complexity": 0.05,
        "expected_information_gain": 0.07,
        "expected_decisiveness": 0.04,
        "portfolio_orthogonality": 0.03,
        "prior_failure_distance": 0.02,
        "estimated_compute_cost": 0.01,
    }

    def evaluate(
        self,
        hypothesis,
        critique: HypothesisCritique,
        context: ObservationSnapshot,
    ) -> HypothesisScorecard:
        observation_grounding = 0.9 if hypothesis.support_observation_refs else 0.4
        novelty = 0.8 if "new" in " ".join(hypothesis.novelty_dimensions).lower() else 0.6
        data_feasibility = 0.9 if hypothesis.required_features else 0.2
        primitive_readiness = 0.95 if hypothesis.required_features else 0.0
        executor_readiness = 0.85 if context.executor_inventory else 0.2
        confounder_coverage = 0.7 if critique.missing_confounders else 0.4
        leakage_safety = 1.0 if not critique.data_leakage_risks else 0.8
        complexity = 0.9 - 0.1 * max(0, hypothesis.parameter_count - 1)
        expected_information_gain = 0.8 if hypothesis.mechanism_family != "mean_reversion" else 0.7
        expected_decisiveness = 0.75 if hypothesis.mechanism_family == "volatility_breakout" else 0.65
        portfolio_orthogonality = 0.6 if hypothesis.mechanism_family != "trend_persistence" else 0.5
        prior_failure_distance = 0.7 if hypothesis.related_hypotheses else 0.5
        estimated_compute_cost = 0.8 if hypothesis.mechanism_family != "volatility_breakout" else 0.7
        hard_blockers: list[str] = []
        if not hypothesis.required_features:
            hard_blockers.append("missing_features")
        if critique.fatal_objections:
            hard_blockers.extend(critique.fatal_objections)
        if hypothesis.parameter_count > 3:
            hard_blockers.append("parameter_cap_exceeded")
        scores = {
            "mechanistic_clarity": _score_component(0.88),
            "falsifiability": _score_component(0.82 if hypothesis.falsification_conditions else 0.3),
            "novelty": _score_component(novelty),
            "observation_grounding": _score_component(observation_grounding),
            "data_feasibility": _score_component(data_feasibility),
            "identity_readiness": _score_component(0.85 if context.identity_readiness == "ready" else 0.45),
            "primitive_readiness": _score_component(primitive_readiness),
            "executor_readiness": _score_component(executor_readiness),
            "confounder_coverage": _score_component(confounder_coverage),
            "leakage_safety": _score_component(leakage_safety),
            "complexity": _score_component(complexity),
            "expected_information_gain": _score_component(expected_information_gain),
            "expected_decisiveness": _score_component(expected_decisiveness),
            "portfolio_orthogonality": _score_component(portfolio_orthogonality),
            "prior_failure_distance": _score_component(prior_failure_distance),
            "estimated_compute_cost": _score_component(estimated_compute_cost),
        }
        overall = sum(scores[name] * weight for name, weight in self.weights.items()) * 100.0
        if hard_blockers:
            overall *= 0.4
        return HypothesisScorecard(
            hypothesis_id=hypothesis.hypothesis_id,
            mechanistic_clarity=scores["mechanistic_clarity"],
            falsifiability=scores["falsifiability"],
            novelty=scores["novelty"],
            observation_grounding=scores["observation_grounding"],
            data_feasibility=scores["data_feasibility"],
            identity_readiness=scores["identity_readiness"],
            primitive_readiness=scores["primitive_readiness"],
            executor_readiness=scores["executor_readiness"],
            confounder_coverage=scores["confounder_coverage"],
            leakage_safety=scores["leakage_safety"],
            complexity=scores["complexity"],
            expected_information_gain=scores["expected_information_gain"],
            expected_decisiveness=scores["expected_decisiveness"],
            portfolio_orthogonality=scores["portfolio_orthogonality"],
            prior_failure_distance=scores["prior_failure_distance"],
            estimated_compute_cost=scores["estimated_compute_cost"],
            overall_score=round(overall, 3),
            hard_blockers=tuple(hard_blockers),
            reason_codes=tuple(sorted({*critique.required_repairs, *critique.strongest_counter_hypothesis.split()})),
            content_identity=content_id("qasc", {"hypothesis_id": hypothesis.hypothesis_id, "overall": overall}),
        )


class CanonicalEvidenceEvaluator:
    def evaluate(self, experiment, campaign_evidence, admission: ExperimentAdmissionDecision) -> EvidenceAssessment:
        result = campaign_evidence.backtest_result
        trade_count = int(result.get("summary", {}).get("totaal_trades") or 0)
        net_return = float(result.get("summary", {}).get("net_return_compound") or 0.0)
        empirical = bool(campaign_evidence.empirical)
        smoke = campaign_evidence.execution_tier == EXECUTION_TIER_EXECUTOR_SMOKE
        insufficient_activity = trade_count < max(int(experiment.minimum_trade_count), 1)
        has_locked_oos = admission.OOS_sufficiency == "SUFFICIENT"
        supporting: tuple[str, ...] = tuple()
        contradicting: tuple[str, ...] = tuple()
        inconclusive: tuple[str, ...] = tuple()
        null_presence = "AVAILABLE"
        null_applicability = "EVALUABLE"
        null_sufficiency = "INSUFFICIENT" if insufficient_activity else "SUFFICIENT"
        null_outcome = "INCONCLUSIVE" if insufficient_activity else ("REJECTED" if net_return <= 0 else "NOT_REJECTED")
        mechanism_support = "INCONCLUSIVE"
        terminal = "NEEDS_MORE_EVIDENCE"
        confidence = "UNCHANGED"
        prior_allowed = False
        prior_basis = "INSUFFICIENT_EMPIRICAL_EVIDENCE"
        evidence_grade = "smoke_only" if smoke else ("empirical" if empirical else "compiler_only")

        if smoke:
            contradicting = ("smoke_execution_only",)
            inconclusive = ("no_empirical_authority",)
        elif insufficient_activity:
            contradicting = ("insufficient_activity",)
            inconclusive = ("null_insufficient", "mechanism_not_decidable")
        elif net_return > 0:
            supporting = ("positive_compound_return", "trades_executed")
            mechanism_support = "SUPPORTED" if empirical else "INCONCLUSIVE"
            terminal = "READY_FOR_SYNTHESIS" if empirical and has_locked_oos else "NEEDS_MORE_EVIDENCE"
            confidence = "INCREASED" if empirical else "UNCHANGED"
            prior_allowed = empirical and has_locked_oos
            prior_basis = "QUALIFIED_EMPIRICAL_EVIDENCE" if prior_allowed else "INSUFFICIENT_OOS_VALIDATION"
        else:
            contradicting = ("negative_compound_return", "cost_drag_or_null_failure")
            mechanism_support = "CONTRADICTED" if empirical else "INCONCLUSIVE"
            terminal = "REJECTED" if empirical else "NEEDS_MORE_EVIDENCE"
            confidence = "DECREASED" if empirical else "UNCHANGED"
            prior_allowed = empirical
            prior_basis = "QUALIFIED_EMPIRICAL_EVIDENCE" if empirical else "INSUFFICIENT_EMPIRICAL_EVIDENCE"

        return EvidenceAssessment(
            assessment_id=content_id("qaea", {"experiment_id": experiment.experiment_id, "campaign_id": campaign_evidence.campaign_id}),
            hypothesis_id=experiment.hypothesis_id,
            experiment_id=experiment.experiment_id,
            campaign_id=campaign_evidence.campaign_id,
            execution_tier=campaign_evidence.execution_tier,
            empirical=empirical,
            evidence_grade=evidence_grade,
            prediction_tested=experiment.predicted_observable,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            inconclusive_evidence=inconclusive,
            null_presence=null_presence,
            null_applicability=null_applicability,
            null_sufficiency=null_sufficiency,
            null_outcome=null_outcome,
            mechanism_support_outcome=mechanism_support,
            OOS_presence="AVAILABLE" if has_locked_oos else "NOT_AVAILABLE",
            OOS_sufficiency="SUFFICIENT" if has_locked_oos else "INSUFFICIENT",
            OOS_outcome="EVALUATED" if has_locked_oos else "INCONCLUSIVE",
            cost_presence="AVAILABLE",
            cost_sufficiency="SUFFICIENT",
            slippage_presence="AVAILABLE",
            slippage_sufficiency="INSUFFICIENT" if "zero_slippage" in experiment.slippage_model or "zero_slippage" in admission.reason_codes else "SUFFICIENT",
            cost_effect="costs_included_in_backtest",
            activity_effect="activity_measured" if trade_count > 0 else "activity_insufficient",
            regime_effect=experiment.universe_spec,
            asset_effect=experiment.universe_spec,
            fragility_effect="stable" if trade_count > 1 else "fragile",
            outlier_effect="none_observed" if trade_count > 0 else "unknown",
            confidence_update=confidence,
            prior_adjustment_allowed=prior_allowed,
            prior_adjustment_basis=prior_basis,
            qualifying_evidence_refs=(campaign_evidence.content_identity,) if prior_allowed else tuple(),
            terminal_disposition=terminal,
            reason_codes=tuple(sorted(set((supporting + contradicting + inconclusive) or ("inconclusive",)))),
            content_identity=content_id(
                "qaea",
                {
                    "terminal": terminal,
                    "null_outcome": null_outcome,
                    "campaign": campaign_evidence.campaign_id,
                    "execution_tier": campaign_evidence.execution_tier,
                },
            ),
        )
