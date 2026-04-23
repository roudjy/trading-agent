"""Tests for research.candidate_lifecycle (v3.12 status model)."""

from __future__ import annotations

import pytest

from research.candidate_lifecycle import (
    ACTIVE_IN_V3_12,
    ACTIVE_TRANSITIONS_V3_12,
    FULL_LIFECYCLE_GRAPH,
    LEGACY_MAPPING,
    RESERVED_FOR_LATER_PHASES,
    STATUS_MODEL_VERSION,
    CandidateLifecycleStatus,
    InvalidTransitionError,
    ReservedStatusError,
    UnknownLegacyVerdictError,
    is_active_in_v3_12,
    map_legacy_verdict,
    validate_active_transition,
)


EXPECTED_STATUSES = {
    "rejected",
    "exploratory",
    "candidate",
    "paper_ready",
    "paper_validated",
    "live_shadow_ready",
    "live_enabled",
    "retired",
}


def test_all_eight_statuses_are_defined() -> None:
    assert {s.value for s in CandidateLifecycleStatus} == EXPECTED_STATUSES


def test_active_in_v3_12_is_exactly_three_statuses() -> None:
    assert {s.value for s in ACTIVE_IN_V3_12} == {"rejected", "exploratory", "candidate"}


def test_reserved_and_active_partition_the_full_enum() -> None:
    union = ACTIVE_IN_V3_12 | RESERVED_FOR_LATER_PHASES
    assert union == set(CandidateLifecycleStatus)
    assert ACTIVE_IN_V3_12.isdisjoint(RESERVED_FOR_LATER_PHASES)


def test_status_model_version_is_pinned_for_v3_12() -> None:
    assert STATUS_MODEL_VERSION == "v3.12.0"


def test_full_graph_contains_all_statuses_as_sources() -> None:
    assert set(FULL_LIFECYCLE_GRAPH.keys()) == set(CandidateLifecycleStatus)


def test_full_graph_targets_are_all_valid_statuses() -> None:
    for _, targets in FULL_LIFECYCLE_GRAPH.items():
        for target in targets:
            assert isinstance(target, CandidateLifecycleStatus)


def test_active_transitions_v3_12_is_subset_of_full_graph() -> None:
    for src, targets in ACTIVE_TRANSITIONS_V3_12.items():
        assert targets.issubset(FULL_LIFECYCLE_GRAPH[src])


def test_active_transitions_only_reference_active_statuses() -> None:
    for src, targets in ACTIVE_TRANSITIONS_V3_12.items():
        assert src in ACTIVE_IN_V3_12
        for target in targets:
            assert target in ACTIVE_IN_V3_12


def test_legacy_mapping_covers_all_v3_11_verdicts() -> None:
    assert set(LEGACY_MAPPING.keys()) == {"rejected", "needs_investigation", "candidate"}


def test_legacy_mapping_reasons_are_non_empty_strings() -> None:
    for _, (status, reason) in LEGACY_MAPPING.items():
        assert isinstance(status, CandidateLifecycleStatus)
        assert isinstance(reason, str) and reason


def test_map_legacy_verdict_needs_investigation_becomes_exploratory() -> None:
    status, reason = map_legacy_verdict("needs_investigation")
    assert status is CandidateLifecycleStatus.EXPLORATORY
    assert reason == "legacy_needs_investigation_mapped_to_exploratory"


def test_map_legacy_verdict_rejected_preserved() -> None:
    status, reason = map_legacy_verdict("rejected")
    assert status is CandidateLifecycleStatus.REJECTED
    assert reason == "legacy_rejected_preserved"


def test_map_legacy_verdict_candidate_preserved() -> None:
    status, reason = map_legacy_verdict("candidate")
    assert status is CandidateLifecycleStatus.CANDIDATE
    assert reason == "legacy_candidate_preserved"


def test_map_legacy_verdict_unknown_raises() -> None:
    with pytest.raises(UnknownLegacyVerdictError):
        map_legacy_verdict("something_else")


def test_is_active_in_v3_12_true_for_active_statuses() -> None:
    for status in ACTIVE_IN_V3_12:
        assert is_active_in_v3_12(status) is True


def test_is_active_in_v3_12_false_for_reserved_statuses() -> None:
    for status in RESERVED_FOR_LATER_PHASES:
        assert is_active_in_v3_12(status) is False


def test_validate_active_transition_accepts_legal_v3_12_edges() -> None:
    validate_active_transition(
        CandidateLifecycleStatus.EXPLORATORY,
        CandidateLifecycleStatus.CANDIDATE,
    )
    validate_active_transition(
        CandidateLifecycleStatus.EXPLORATORY,
        CandidateLifecycleStatus.REJECTED,
    )
    validate_active_transition(
        CandidateLifecycleStatus.CANDIDATE,
        CandidateLifecycleStatus.REJECTED,
    )


def test_validate_active_transition_rejects_reserved_target() -> None:
    with pytest.raises(ReservedStatusError):
        validate_active_transition(
            CandidateLifecycleStatus.CANDIDATE,
            CandidateLifecycleStatus.PAPER_READY,
        )


def test_validate_active_transition_rejects_reserved_retired() -> None:
    with pytest.raises(ReservedStatusError):
        validate_active_transition(
            CandidateLifecycleStatus.CANDIDATE,
            CandidateLifecycleStatus.RETIRED,
        )


def test_validate_active_transition_rejects_illegal_edge() -> None:
    with pytest.raises(InvalidTransitionError):
        # candidate -> exploratory is not defined even in the full graph
        validate_active_transition(
            CandidateLifecycleStatus.CANDIDATE,
            CandidateLifecycleStatus.EXPLORATORY,
        )


def test_validate_active_transition_rejects_from_rejected_terminal() -> None:
    with pytest.raises(InvalidTransitionError):
        # rejected is terminal in v3.12
        validate_active_transition(
            CandidateLifecycleStatus.REJECTED,
            CandidateLifecycleStatus.CANDIDATE,
        )
