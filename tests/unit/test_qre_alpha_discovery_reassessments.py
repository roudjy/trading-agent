from __future__ import annotations

from pathlib import Path

from packages.qre_research.alpha_discovery.runner import _historical_reassessments


def test_historical_reassessments_preserve_mvp_provenance_but_remove_empirical_authority(tmp_path: Path) -> None:
    payload = _historical_reassessments(tmp_path)
    rows = {str(row.get("artifact_id") or ""): row for row in payload["rows"]}

    assert rows["qcam_4c691604bc936a8e"]["corrected_evidence_tier"] == "EXECUTOR_SMOKE"
    assert rows["qcam_4c691604bc936a8e"]["mechanism_prior_authority"] == "none"
    assert rows["qrl_48a61c8a441143f6"]["corrected_lesson_type"] == "PROCESS_LESSON"
    assert rows["qrl_48a61c8a441143f6"]["prior_adjustment_retained"] is False


def test_pr726_authority_reassessment_separates_execution_science_and_evidence(tmp_path: Path) -> None:
    payload = _historical_reassessments(tmp_path)
    rows = {str(row.get("artifact_id") or ""): row for row in payload["rows"]}
    reassessment = rows["pr726_authority_reassessment"]

    assert reassessment["original_requested_tier"] == "EMPIRICAL_SCREENING"
    assert reassessment["original_admitted_tier"] == "LOCKED_OOS_VALIDATION"
    assert reassessment["source_run_id"] == "qarr_d48faec61478b4c4"
    assert reassessment["source_campaign_id"] == "qcam_00498b2704a7deef"
    assert reassessment["source_experiment_id"] == "qexp_7e21c050e448d71a"
    assert reassessment["current_or_child_experiment_id"] == "qexp_fe7bfe9caccaec74"
    assert reassessment["corrected_admitted_tier"] == "EMPIRICAL_SCREENING"
    assert reassessment["corrected_execution_status"] == "COMPLETED"
    assert reassessment["corrected_evidence_tier_reached"] == "EMPIRICAL_SCREENING"
    assert reassessment["scientific_disposition"] == "NEEDS_MORE_EVIDENCE"
    assert reassessment["candidate_created"] is False
    assert reassessment["mechanism_prior_changed"] is False
