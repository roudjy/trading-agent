"""Deterministic QRE state-transition diagnostics scaffold.

This module explains candidate/research state transitions as read-only context.
It does not mutate candidates, promote strategies, fetch data, or authorize
paper/shadow/live/broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"


STATE_NAMES: tuple[str, ...] = (
    "unknown",
    "candidate_discovered",
    "screened",
    "validation_candidate",
    "validated",
    "rejected",
    "blocked",
    "fail_closed",
)


TRANSITION_REASONS: tuple[str, ...] = (
    "criteria_passed",
    "criteria_failed",
    "insufficient_evidence",
    "missing_required_field",
    "data_readiness_blocked",
    "identity_ambiguous",
    "lineage_missing",
    "null_model_required",
    "tail_risk_required",
    "operator_review_required",
    "unknown",
)


TERMINAL_NEGATIVE_STATES: tuple[str, ...] = (
    "rejected",
    "blocked",
    "fail_closed",
)


POSITIVE_PROGRESS_STATES: tuple[str, ...] = (
    "screened",
    "validation_candidate",
    "validated",
)


@dataclass(frozen=True)
class StateTransitionDiagnostic:
    subject_id: str
    prior_state: str
    new_state: str
    transition_reason: str
    blocker_class: str | None
    evidence_ref: str | None
    artifact_ref: str | None
    transition_state: str
    explanation: str


def _normalize(value: Any, allowed: tuple[str, ...], *, fallback: str = "unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text in allowed else fallback


def diagnose_state_transition(
    *,
    subject_id: Any,
    prior_state: Any,
    new_state: Any,
    transition_reason: Any = None,
    blocker_class: Any = None,
    evidence_ref: Any = None,
    artifact_ref: Any = None,
) -> StateTransitionDiagnostic:
    """Create a deterministic diagnostic for one state transition.

    The diagnostic is context only. It does not authorize promotion or execution.
    """

    normalized_prior = _normalize(prior_state, STATE_NAMES)
    normalized_new = _normalize(new_state, STATE_NAMES)
    normalized_reason = _normalize(transition_reason, TRANSITION_REASONS)

    clean_subject_id = str(subject_id or "").strip() or "unknown"
    clean_blocker = str(blocker_class).strip() if blocker_class is not None else None
    clean_evidence = str(evidence_ref).strip() if evidence_ref is not None else None
    clean_artifact = str(artifact_ref).strip() if artifact_ref is not None else None

    if normalized_prior == "unknown" or normalized_new == "unknown":
        transition_state = "insufficient_state_data"
        explanation = "Prior and new state must both be known before transition trust can be assessed."
    elif normalized_prior == normalized_new:
        transition_state = "no_state_change"
        explanation = "Prior and new state are identical; this is a stable/no-op transition."
    elif normalized_new in TERMINAL_NEGATIVE_STATES:
        transition_state = "terminal_negative_transition"
        explanation = "Transition ends in a negative or fail-closed state and requires blocker/evidence context."
    elif normalized_new in POSITIVE_PROGRESS_STATES:
        transition_state = "positive_progress_transition"
        explanation = "Transition progresses to a more advanced research state; this remains diagnostic only."
    else:
        transition_state = "other_transition"
        explanation = "Transition is recognized but does not map to a positive or terminal-negative class."

    return StateTransitionDiagnostic(
        subject_id=clean_subject_id,
        prior_state=normalized_prior,
        new_state=normalized_new,
        transition_reason=normalized_reason,
        blocker_class=clean_blocker,
        evidence_ref=clean_evidence,
        artifact_ref=clean_artifact,
        transition_state=transition_state,
        explanation=explanation,
    )


def diagnose_transition_rows(rows: list[Mapping[str, Any]]) -> list[StateTransitionDiagnostic]:
    return [
        diagnose_state_transition(
            subject_id=row.get("subject_id"),
            prior_state=row.get("prior_state"),
            new_state=row.get("new_state"),
            transition_reason=row.get("transition_reason"),
            blocker_class=row.get("blocker_class"),
            evidence_ref=row.get("evidence_ref"),
            artifact_ref=row.get("artifact_ref"),
        )
        for row in rows
        if isinstance(row, Mapping)
    ]


def transition_diagnostic_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state_names": list(STATE_NAMES),
        "transition_reasons": list(TRANSITION_REASONS),
        "terminal_negative_states": list(TERMINAL_NEGATIVE_STATES),
        "positive_progress_states": list(POSITIVE_PROGRESS_STATES),
        "authority": {
            "state_transition_diagnostics_are_context_only": True,
            "not_alpha_authority": True,
            "not_candidate_promotion": True,
            "not_strategy_registration": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "does_not_fetch_data": True,
            "does_not_mutate_candidates": True,
            "does_not_mutate_frozen_contracts": True,
        },
    }