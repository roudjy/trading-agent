from __future__ import annotations

from .contracts import (
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EvidenceAssessment,
    LESSON_TYPE_DATA,
    LESSON_TYPE_EMPIRICAL_MECHANISM,
    LESSON_TYPE_EVIDENCE_DESIGN,
    LESSON_TYPE_PROCESS,
    ResearchLesson,
    content_id,
)


class StructuredLessonCompressor:
    def compress(self, assessment: EvidenceAssessment, prior_memory: dict[str, object]) -> ResearchLesson:
        if assessment.execution_tier == EXECUTION_TIER_EXECUTOR_SMOKE:
            lesson_type = LESSON_TYPE_PROCESS
            next_question = "obtain evidence-grade data before empirical screening"
            supported = "not_evaluable"
            contradicted = "not_evaluable"
            actionable = "route future runs through evidence-grade admission"
            non_actionable = "executor smoke does not imply mechanism evidence"
            prior_allowed = False
            prior_adjustments: tuple[str, ...] = tuple()
        elif assessment.prior_adjustment_allowed:
            lesson_type = LESSON_TYPE_EMPIRICAL_MECHANISM
            if assessment.terminal_disposition == "READY_FOR_SYNTHESIS":
                next_question = "freeze the stronger design and prepare the next bounded validation"
                supported = "supported"
                contradicted = "not_contradicted"
                actionable = "preserve the qualified empirical design"
            else:
                next_question = "tighten falsification conditions or switch mechanism family"
                supported = "not_supported"
                contradicted = "contradicted"
                actionable = "change the mechanism or falsification path"
            non_actionable = "one empirical campaign does not establish robustness"
            prior_allowed = True
            prior_adjustments = ("bounded empirical prior update",)
        elif "insufficient_activity" in assessment.reason_codes or assessment.OOS_sufficiency == "INSUFFICIENT":
            lesson_type = LESSON_TYPE_DATA
            next_question = "obtain more history or a broader justified universe"
            supported = "inconclusive"
            contradicted = "uncertain"
            actionable = "obtain evidence-grade data without weakening thresholds"
            non_actionable = "insufficient data cannot lower a mechanism prior"
            prior_allowed = False
            prior_adjustments = tuple()
        else:
            lesson_type = LESSON_TYPE_EVIDENCE_DESIGN
            next_question = "improve controls before rerunning a changed experiment"
            supported = "inconclusive"
            contradicted = "uncertain"
            actionable = "strengthen controls and falsification design"
            non_actionable = "design gaps are not mechanism failure"
            prior_allowed = False
            prior_adjustments = tuple()

        cause = "cost_drag" if "cost" in " ".join(assessment.reason_codes) else "insufficient_activity"
        return ResearchLesson(
            lesson_id=content_id(
                "qrl",
                {
                    "assessment_id": assessment.assessment_id,
                    "terminal": assessment.terminal_disposition,
                    "lesson_type": lesson_type,
                },
            ),
            hypothesis_id=assessment.hypothesis_id,
            experiment_id=assessment.experiment_id,
            strategy_spec_id=str(prior_memory.get("strategy_spec_id") or ""),
            campaign_id=assessment.campaign_id,
            lesson_type=lesson_type,
            terminal_disposition=assessment.terminal_disposition,
            mechanism_supported=supported,
            mechanism_contradicted=contradicted,
            decisive_evidence=assessment.supporting_evidence,
            unresolved_uncertainty=assessment.inconclusive_evidence,
            failure_mode=cause,
            actionable_cause=actionable,
            non_actionable_cause=non_actionable,
            do_not_repeat=("do not rerun the same unchanged contract",),
            generator_constraints=("max_three_hypotheses", "max_one_rewrite", "no_oos_selection"),
            new_falsification_requirements=("require explicit cost comparison", "require regime-neutral null"),
            prior_adjustment_allowed=prior_allowed,
            prior_adjustment_basis=assessment.prior_adjustment_basis,
            prior_adjustments=prior_adjustments,
            recommended_next_question=next_question,
            supporting_artifact_refs=(assessment.content_identity,),
            content_identity=content_id(
                "qrlp",
                {
                    "assessment": assessment.assessment_id,
                    "lesson_type": lesson_type,
                    "next_question": next_question,
                },
            ),
        )
