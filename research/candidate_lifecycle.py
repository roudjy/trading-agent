"""Candidate lifecycle status model for v3.12.

Two-layer validation:

1. ``FULL_LIFECYCLE_GRAPH`` defines every legal transition across the
   complete 8-status model spanning v3.12 through v3.17. It is the
   durable reference for downstream phases.

2. ``ACTIVE_TRANSITIONS_V3_12`` is the strict subset the v3.12 runtime
   is permitted to traverse. Only three statuses are active this phase:
   ``REJECTED``, ``EXPLORATORY``, ``CANDIDATE``. Transitions into any
   reserved status (paper_ready, paper_validated, live_shadow_ready,
   live_enabled, retired) raise ``ReservedStatusError`` so reserved
   slots cannot be entered accidentally before their owning phase ships.

Legacy auditability:
``LEGACY_MAPPING`` documents how v3.11 promotion verdicts
(``rejected`` / ``needs_investigation`` / ``candidate``) are mapped to
v3.12 lifecycle statuses, with a ``mapping_reason`` string preserved
per entry in the registry-v2 sidecar.
"""

from __future__ import annotations

from enum import Enum


STATUS_MODEL_VERSION = "v3.12.0"


class CandidateLifecycleStatus(str, Enum):
    """First-class lifecycle status for promoted candidates.

    v3.12 only assigns the first three values at runtime; the rest are
    defined here so downstream phases can activate them incrementally
    without schema churn.
    """

    REJECTED = "rejected"
    EXPLORATORY = "exploratory"
    CANDIDATE = "candidate"
    PAPER_READY = "paper_ready"                # reserved: activated in v3.15
    PAPER_VALIDATED = "paper_validated"        # reserved: activated in v3.15
    LIVE_SHADOW_READY = "live_shadow_ready"    # reserved: activated in v3.16
    LIVE_ENABLED = "live_enabled"              # reserved: activated in v3.17
    RETIRED = "retired"                        # reserved: activated in v3.17


ACTIVE_IN_V3_12: frozenset[CandidateLifecycleStatus] = frozenset({
    CandidateLifecycleStatus.REJECTED,
    CandidateLifecycleStatus.EXPLORATORY,
    CandidateLifecycleStatus.CANDIDATE,
})


RESERVED_FOR_LATER_PHASES: frozenset[CandidateLifecycleStatus] = frozenset({
    CandidateLifecycleStatus.PAPER_READY,
    CandidateLifecycleStatus.PAPER_VALIDATED,
    CandidateLifecycleStatus.LIVE_SHADOW_READY,
    CandidateLifecycleStatus.LIVE_ENABLED,
    CandidateLifecycleStatus.RETIRED,
})


# Full directed graph of legal transitions across the entire lifecycle.
# Used as the durable reference; NOT consulted by v3.12 runtime.
FULL_LIFECYCLE_GRAPH: dict[CandidateLifecycleStatus, frozenset[CandidateLifecycleStatus]] = {
    CandidateLifecycleStatus.EXPLORATORY: frozenset({
        CandidateLifecycleStatus.CANDIDATE,
        CandidateLifecycleStatus.REJECTED,
    }),
    CandidateLifecycleStatus.CANDIDATE: frozenset({
        CandidateLifecycleStatus.PAPER_READY,
        CandidateLifecycleStatus.REJECTED,
        CandidateLifecycleStatus.RETIRED,
    }),
    CandidateLifecycleStatus.PAPER_READY: frozenset({
        CandidateLifecycleStatus.PAPER_VALIDATED,
        CandidateLifecycleStatus.REJECTED,
    }),
    CandidateLifecycleStatus.PAPER_VALIDATED: frozenset({
        CandidateLifecycleStatus.LIVE_SHADOW_READY,
        CandidateLifecycleStatus.RETIRED,
    }),
    CandidateLifecycleStatus.LIVE_SHADOW_READY: frozenset({
        CandidateLifecycleStatus.LIVE_ENABLED,
        CandidateLifecycleStatus.RETIRED,
    }),
    CandidateLifecycleStatus.LIVE_ENABLED: frozenset({
        CandidateLifecycleStatus.RETIRED,
    }),
    CandidateLifecycleStatus.REJECTED: frozenset(),
    CandidateLifecycleStatus.RETIRED: frozenset(),
}


# Strict v3.12 runtime subset. Attempts to transition into a reserved
# status raise ``ReservedStatusError`` rather than being silently
# routed through the fuller graph.
ACTIVE_TRANSITIONS_V3_12: dict[CandidateLifecycleStatus, frozenset[CandidateLifecycleStatus]] = {
    CandidateLifecycleStatus.EXPLORATORY: frozenset({
        CandidateLifecycleStatus.CANDIDATE,
        CandidateLifecycleStatus.REJECTED,
    }),
    CandidateLifecycleStatus.CANDIDATE: frozenset({
        CandidateLifecycleStatus.REJECTED,
    }),
    CandidateLifecycleStatus.REJECTED: frozenset(),
}


# Mapping from v3.11 promotion.py statuses to v3.12 lifecycle statuses.
# Each entry records the mapping_reason string that travels alongside
# the candidate through registry-v2 for audit traceability.
LEGACY_MAPPING: dict[str, tuple[CandidateLifecycleStatus, str]] = {
    "rejected": (
        CandidateLifecycleStatus.REJECTED,
        "legacy_rejected_preserved",
    ),
    "needs_investigation": (
        CandidateLifecycleStatus.EXPLORATORY,
        "legacy_needs_investigation_mapped_to_exploratory",
    ),
    "candidate": (
        CandidateLifecycleStatus.CANDIDATE,
        "legacy_candidate_preserved",
    ),
}


class ReservedStatusError(Exception):
    """Raised when v3.12 runtime code attempts to assign a reserved status."""


class InvalidTransitionError(Exception):
    """Raised when a transition is not permitted by ACTIVE_TRANSITIONS_V3_12."""


class UnknownLegacyVerdictError(Exception):
    """Raised when a legacy verdict string has no defined mapping."""


def is_active_in_v3_12(status: CandidateLifecycleStatus) -> bool:
    """Return True iff ``status`` may be assigned by v3.12 runtime code."""
    return status in ACTIVE_IN_V3_12


def map_legacy_verdict(v1_status: str) -> tuple[CandidateLifecycleStatus, str]:
    """Map a v3.11 promotion verdict to a v3.12 lifecycle status.

    Returns a tuple ``(lifecycle_status, mapping_reason)``. The
    mapping_reason is preserved verbatim in registry-v2 entries so the
    audit trail shows both the original verdict and the mapping that
    produced the new status.
    """
    try:
        return LEGACY_MAPPING[v1_status]
    except KeyError as exc:
        raise UnknownLegacyVerdictError(
            f"no lifecycle mapping defined for legacy verdict {v1_status!r}"
        ) from exc


def validate_active_transition(
    from_: CandidateLifecycleStatus,
    to_: CandidateLifecycleStatus,
) -> None:
    """v3.12 runtime validator.

    Refuses:
    - transitions into any reserved status
      (raises ``ReservedStatusError``)
    - transitions not present in ``ACTIVE_TRANSITIONS_V3_12``
      (raises ``InvalidTransitionError``)
    """
    if to_ in RESERVED_FOR_LATER_PHASES:
        raise ReservedStatusError(
            f"status {to_.value!r} is reserved for a future phase and "
            "cannot be assigned by v3.12 runtime code"
        )
    allowed = ACTIVE_TRANSITIONS_V3_12.get(from_, frozenset())
    if to_ not in allowed:
        raise InvalidTransitionError(
            f"transition {from_.value!r} -> {to_.value!r} is not permitted "
            "by ACTIVE_TRANSITIONS_V3_12"
        )
