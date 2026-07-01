from __future__ import annotations

from reporting import qre_decision_calibration_review as review


def test_decision_calibration_review_reads_current_artifacts_and_is_fail_closed() -> None:
    snapshot = review.run_decision_calibration_review(write_outputs_flag=False)

    assert snapshot["report_kind"] == "qre_decision_calibration_review"
    assert snapshot["real_hypothesis"]["terminal_disposition_after"] == "NEEDS_MORE_EVIDENCE"
    assert snapshot["real_hypothesis"]["next_action_after"] == "launch_data_oos_capacity_expansion"
    assert snapshot["real_hypothesis"]["evidence_sufficiency"]["transaction_costs"] == "INSUFFICIENT"
    assert snapshot["decision_quality_kpis"]["benchmark_decision_accuracy"] == 100.0
    assert snapshot["decision_quality_kpis"]["false_synthesis_ready_count"] == 0
    assert snapshot["conditional_synthesis"]["benchmark_candidates_enabled"] is False
    assert snapshot["conditional_synthesis"]["provenance_isolation_passed"] is True

