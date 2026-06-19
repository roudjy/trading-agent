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

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


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


QRE_STATUS_MODEL_VERSION = "qre.v1"


class QRECandidateLifecycleStatus(str, Enum):
    DRAFT = "draft"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    EVIDENCE_COMPLETE = "evidence_complete"
    QUALITY_REVIEW = "quality_review"
    PROMOTION_REVIEW = "promotion_review"
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"
    COOLDOWN = "cooldown"
    RETIRED = "retired"
    SHADOW_READINESS_CANDIDATE = "shadow_readiness_candidate"


QRE_FULL_LIFECYCLE_GRAPH: dict[QRECandidateLifecycleStatus, frozenset[QRECandidateLifecycleStatus]] = {
    QRECandidateLifecycleStatus.DRAFT: frozenset(
        {
            QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE,
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE: frozenset(
        {
            QRECandidateLifecycleStatus.EVIDENCE_COMPLETE,
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.EVIDENCE_COMPLETE: frozenset(
        {
            QRECandidateLifecycleStatus.QUALITY_REVIEW,
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.QUALITY_REVIEW: frozenset(
        {
            QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.PROMOTION_REVIEW: frozenset(
        {
            QRECandidateLifecycleStatus.SHADOW_READINESS_CANDIDATE,
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.SUPPRESSED: frozenset(
        {
            QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.COOLDOWN: frozenset(
        {
            QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE,
            QRECandidateLifecycleStatus.SUPPRESSED,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.SHADOW_READINESS_CANDIDATE: frozenset(
        {
            QRECandidateLifecycleStatus.REJECTED,
            QRECandidateLifecycleStatus.COOLDOWN,
            QRECandidateLifecycleStatus.RETIRED,
        }
    ),
    QRECandidateLifecycleStatus.REJECTED: frozenset(),
    QRECandidateLifecycleStatus.RETIRED: frozenset(),
}


class QREInvalidTransitionError(Exception):
    """Raised when a QRE lifecycle transition is not allowed."""


class QREDuplicateScopeError(Exception):
    """Raised when two QRE candidate records share the same deterministic scope."""


def _qre_text(value: Any) -> str:
    return str(value or "").strip()


def _qre_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _scope_seed(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": _qre_text(scope.get("hypothesis_id")),
        "behavior_id": _qre_text(scope.get("behavior_id")),
        "preset_id": _qre_text(scope.get("preset_id")),
        "timeframe": _qre_text(scope.get("timeframe")),
        "universe_or_basket_scope": _qre_text(scope.get("universe_or_basket_scope")),
        "region": _qre_text(scope.get("region")),
        "symbol": _qre_text(scope.get("symbol")),
    }


def compute_qre_scope_signature(scope: dict[str, Any]) -> str:
    payload = _scope_seed(scope)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_qre_candidate_identity(scope: dict[str, Any]) -> dict[str, str]:
    signature = compute_qre_scope_signature(scope)
    version_seed = {
        **_scope_seed(scope),
        "sampling_plan_ref": _qre_text(scope.get("sampling_plan_ref")),
        "accepted_lineage_count": int(scope.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(scope.get("accepted_oos_count", 0) or 0),
    }
    version_raw = json.dumps(version_seed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    version_hash = hashlib.sha256(version_raw.encode("utf-8")).hexdigest()
    return {
        "candidate_id": "qre_cand_" + signature[:16],
        "scope_signature": signature,
        "candidate_version": "qre_v_" + version_hash[:16],
    }


@dataclass(frozen=True)
class QRETransitionContext:
    accepted_lineage_count: int = 0
    accepted_oos_count: int = 0
    evidence_complete: bool = False
    quality_gate_passed: bool = False
    promotion_gate_passed: bool = False
    readiness_gate_passed: bool = False
    operator_shadow_authority: bool = False
    rejected_scope: bool = False
    suppressed_scope: bool = False
    duplicate_scope: bool = False


def validate_qre_transition(
    from_: QRECandidateLifecycleStatus,
    to_: QRECandidateLifecycleStatus,
    *,
    context: QRETransitionContext,
) -> None:
    allowed = QRE_FULL_LIFECYCLE_GRAPH.get(from_, frozenset())
    if to_ not in allowed:
        raise QREInvalidTransitionError(f"transition {from_.value!r} -> {to_.value!r} is not permitted")
    if context.duplicate_scope:
        raise QREInvalidTransitionError("duplicate_scope_blocked")
    if to_ == QRECandidateLifecycleStatus.EVIDENCE_COMPLETE:
        if not context.evidence_complete or context.accepted_lineage_count <= 0 or context.accepted_oos_count <= 0:
            raise QREInvalidTransitionError("evidence_complete_requires_accepted_evidence")
    if to_ == QRECandidateLifecycleStatus.QUALITY_REVIEW and not context.evidence_complete:
        raise QREInvalidTransitionError("quality_review_requires_evidence_complete")
    if to_ == QRECandidateLifecycleStatus.PROMOTION_REVIEW and not context.quality_gate_passed:
        raise QREInvalidTransitionError("promotion_review_requires_quality_gate")
    if to_ == QRECandidateLifecycleStatus.SHADOW_READINESS_CANDIDATE:
        if not context.promotion_gate_passed:
            raise QREInvalidTransitionError("shadow_readiness_requires_promotion_gate")
        if not context.readiness_gate_passed:
            raise QREInvalidTransitionError("shadow_readiness_requires_readiness_gate")
        if not context.operator_shadow_authority:
            raise QREInvalidTransitionError("shadow_readiness_requires_operator_authority")


def build_qre_candidate_record(
    scope: dict[str, Any],
    *,
    context: QRETransitionContext,
) -> dict[str, Any]:
    identity = build_qre_candidate_identity(scope)
    blockers: list[str] = []
    status = QRECandidateLifecycleStatus.DRAFT

    if context.duplicate_scope:
        blockers.append("duplicate_scope_blocked")
        status = QRECandidateLifecycleStatus.SUPPRESSED
    elif context.rejected_scope:
        blockers.append("rejected_scope_cannot_become_candidate")
        status = QRECandidateLifecycleStatus.REJECTED
    elif context.suppressed_scope:
        blockers.append("suppressed_scope_requires_material_novelty")
        status = QRECandidateLifecycleStatus.SUPPRESSED
    elif context.evidence_complete and context.accepted_lineage_count > 0 and context.accepted_oos_count > 0:
        status = QRECandidateLifecycleStatus.EVIDENCE_COMPLETE
    else:
        blockers.append("accepted_evidence_incomplete")
        status = QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE

    return {
        **identity,
        "status_model_version": QRE_STATUS_MODEL_VERSION,
        "scope": dict(_scope_seed(scope)),
        "sampling_plan_ref": _qre_text(scope.get("sampling_plan_ref")),
        "accepted_lineage_count": int(context.accepted_lineage_count),
        "accepted_oos_count": int(context.accepted_oos_count),
        "status": status.value,
        "blockers": _qre_unique(blockers),
        "authority": {
            "non_authoritative": True,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
            "can_activate_paper": False,
            "can_activate_live": False,
        },
    }


def assert_unique_qre_scope(records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for record in records:
        signature = _qre_text(record.get("scope_signature"))
        if signature in seen:
            raise QREDuplicateScopeError(f"duplicate scope signature: {signature}")
        seen.add(signature)


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
