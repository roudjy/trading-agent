from research.qre_state_transition_diagnostics import (
    diagnose_state_transition,
    diagnose_transition_rows,
    transition_diagnostic_manifest,
)


def test_transition_manifest_is_context_only():
    manifest = transition_diagnostic_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "candidate_discovered" in manifest["state_names"]
    assert "validated" in manifest["state_names"]
    assert "fail_closed" in manifest["state_names"]
    assert "null_model_required" in manifest["transition_reasons"]

    authority = manifest["authority"]
    assert authority["state_transition_diagnostics_are_context_only"] is True
    assert authority["not_alpha_authority"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
    assert authority["does_not_fetch_data"] is True
    assert authority["does_not_mutate_candidates"] is True
    assert authority["does_not_mutate_frozen_contracts"] is True


def test_positive_progress_transition():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:1",
        prior_state="screened",
        new_state="validation_candidate",
        transition_reason="criteria_passed",
        evidence_ref="research/example.json",
        artifact_ref="logs/example/latest.json",
    )

    assert diagnostic.subject_id == "candidate:1"
    assert diagnostic.prior_state == "screened"
    assert diagnostic.new_state == "validation_candidate"
    assert diagnostic.transition_reason == "criteria_passed"
    assert diagnostic.transition_state == "positive_progress_transition"
    assert diagnostic.evidence_ref == "research/example.json"
    assert diagnostic.artifact_ref == "logs/example/latest.json"


def test_terminal_negative_transition():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:2",
        prior_state="screened",
        new_state="blocked",
        transition_reason="data_readiness_blocked",
        blocker_class="missing_required_field",
    )

    assert diagnostic.transition_state == "terminal_negative_transition"
    assert diagnostic.blocker_class == "missing_required_field"


def test_fail_closed_transition_is_terminal_negative():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:3",
        prior_state="validation_candidate",
        new_state="fail_closed",
        transition_reason="lineage_missing",
    )

    assert diagnostic.transition_state == "terminal_negative_transition"


def test_no_state_change_transition():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:4",
        prior_state="screened",
        new_state="screened",
        transition_reason="operator_review_required",
    )

    assert diagnostic.transition_state == "no_state_change"


def test_unknown_states_fail_closed_to_insufficient_state_data():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:5",
        prior_state="not_real",
        new_state="validated",
        transition_reason="criteria_passed",
    )

    assert diagnostic.prior_state == "unknown"
    assert diagnostic.transition_state == "insufficient_state_data"


def test_unknown_reason_is_normalized():
    diagnostic = diagnose_state_transition(
        subject_id="candidate:6",
        prior_state="candidate_discovered",
        new_state="screened",
        transition_reason="not_real",
    )

    assert diagnostic.transition_reason == "unknown"
    assert diagnostic.transition_state == "positive_progress_transition"


def test_missing_subject_id_is_normalized():
    diagnostic = diagnose_state_transition(
        subject_id="",
        prior_state="candidate_discovered",
        new_state="screened",
    )

    assert diagnostic.subject_id == "unknown"


def test_diagnose_transition_rows_ignores_non_mappings():
    rows = [
        {
            "subject_id": "candidate:1",
            "prior_state": "candidate_discovered",
            "new_state": "screened",
            "transition_reason": "criteria_passed",
        },
        "bad",
        {
            "subject_id": "candidate:2",
            "prior_state": "screened",
            "new_state": "rejected",
            "transition_reason": "criteria_failed",
        },
    ]

    diagnostics = diagnose_transition_rows(rows)  # type: ignore[arg-type]

    assert len(diagnostics) == 2
    assert diagnostics[0].transition_state == "positive_progress_transition"
    assert diagnostics[1].transition_state == "terminal_negative_transition"