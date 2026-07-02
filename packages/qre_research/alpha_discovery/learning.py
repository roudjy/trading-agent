from __future__ import annotations

from .contracts import EvidenceAssessment, ResearchLesson, content_id


class StructuredLessonCompressor:
    def compress(self, assessment: EvidenceAssessment, prior_memory: dict[str, object]) -> ResearchLesson:
        if assessment.terminal_disposition == "READY_FOR_SYNTHESIS":
            supported = "supported"
            contradicted = "not_contradicted"
            next_question = "promote the mechanism into a narrower preregistered follow-up"
        elif assessment.terminal_disposition == "REJECTED":
            supported = "not_supported"
            contradicted = "contradicted"
            next_question = "tighten falsification conditions or switch mechanism family"
        else:
            supported = "inconclusive"
            contradicted = "uncertain"
            next_question = "obtain more decisive data or lower the minimum activity threshold"
        cause = "cost_drag" if "cost" in " ".join(assessment.reason_codes) else "insufficient_activity"
        lesson = ResearchLesson(
            lesson_id=content_id("qrl", {"assessment_id": assessment.assessment_id, "terminal": assessment.terminal_disposition}),
            hypothesis_id=assessment.hypothesis_id,
            experiment_id=assessment.experiment_id,
            strategy_spec_id=str(prior_memory.get("strategy_spec_id") or ""),
            campaign_id=assessment.campaign_id,
            terminal_disposition=assessment.terminal_disposition,
            mechanism_supported=supported,
            mechanism_contradicted=contradicted,
            decisive_evidence=assessment.supporting_evidence,
            unresolved_uncertainty=assessment.inconclusive_evidence,
            failure_mode=cause,
            actionable_cause="strengthen regime filter" if cause == "cost_drag" else "expand evidence window",
            non_actionable_cause="raw market randomness is not a code gap",
            do_not_repeat=("do not rerun the same unchanged contract",),
            generator_constraints=("max_three_hypotheses", "max_one_rewrite", "no_oos_selection"),
            new_falsification_requirements=("require explicit cost comparison", "require regime-neutral null"),
            prior_adjustments=("lower prior on duplicated mechanism families",),
            recommended_next_question=next_question,
            supporting_artifact_refs=(assessment.content_identity,),
            content_identity=content_id("qrlp", {"assessment": assessment.assessment_id, "next_question": next_question}),
        )
        return lesson

