"""v3.15.11 — Stop-Condition Engine (ADVISORY ONLY).

Deterministic, rule-based engine that emits *advisory* recommendations
about cooldown / freeze / retire / review based on the rolled-up
evidence ledger and (optionally) per-campaign information gain
history.

HARD POSITIONING:

- This module emits **recommendations**, never enforcement.
- Every artifact carries ``enforcement_state = "advisory_only"`` at
  top level and on each decision record so downstream consumers
  cannot accidentally treat advisory output as policy.
- The field is named ``recommended_decision``, not ``decision``,
  to make the advisory nature explicit at the schema level.
- The existing ``research.campaign_policy.decide()`` is **NOT**
  modified by this module. Policy consumption is a separate future
  release. Until then, an operator reads the recommendations and
  applies them manually if appropriate.

SAFETY INVARIANTS:

- ``technical_failure`` evidence MUST NOT lead to retire decisions.
  Repeated technical failures route to ``REVIEW_REQUIRED`` so the
  operator can investigate worker/runtime problems.
- The presence of any promotion-grade or paper-ready candidate in
  the rolled evidence protects the scope from retirement.
- Degenerate ``no_survivors`` outcomes are treated as meaningful
  research signals — not technical failures — and DO contribute
  to research-rejection cooldown counters.

Pure derivation (``derive_stop_conditions``) + thin IO wrapper
(``write_stop_conditions_artifact``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

STOP_CONDITIONS_SCHEMA_VERSION: Final[str] = "1.0"
STOP_CONDITIONS_PATH: Final[Path] = Path(
    "research/campaigns/evidence/stop_conditions_latest.v1.json"
)

ENFORCEMENT_STATE_ADVISORY: Final[str] = "advisory_only"

# Decision constants. RETIRE_* are reserved for repeated genuine
# research rejection — never for technical failures.
DECISION_NONE: Final[str] = "NONE"
DECISION_COOLDOWN: Final[str] = "COOLDOWN"
DECISION_FREEZE_PRESET: Final[str] = "FREEZE_PRESET"
DECISION_RETIRE_HYPOTHESIS: Final[str] = "RETIRE_HYPOTHESIS"
DECISION_RETIRE_FAMILY: Final[str] = "RETIRE_FAMILY"
DECISION_REVIEW_REQUIRED: Final[str] = "REVIEW_REQUIRED"

SEVERITY_INFO: Final[str] = "info"
SEVERITY_WARNING: Final[str] = "warning"
SEVERITY_CRITICAL: Final[str] = "critical"

# Threshold constants — single inspection point for the policy.
STOP_INSUFFICIENT_TRADES_COOLDOWN: Final[int] = 3
STOP_REPEAT_REJECTION_FREEZE: Final[int] = 5
STOP_REPEAT_REJECTION_RETIRE: Final[int] = 10
STOP_TECHNICAL_FAILURE_REVIEW: Final[int] = 3
STOP_NO_INFO_REVIEW: Final[int] = 10

INSUFFICIENT_TRADES_REASON: Final[str] = "insufficient_trades"


@dataclass(frozen=True)
class StopDecision:
    scope_type: str
    scope_id: str
    recommended_decision: str
    severity: str
    reason_codes: list[str]
    evidence: dict[str, Any]
    cooldown_until_utc: str | None = None
    enforcement_state: str = ENFORCEMENT_STATE_ADVISORY


@dataclass
class _ScopeProtection:
    """Carries candidate-evidence protection signals for a scope."""

    has_promotion_candidate: bool = False
    has_paper_ready: bool = False
    has_recent_information: bool = False
    candidate_count: int = 0


def _is_protected(p: _ScopeProtection) -> bool:
    return (
        p.has_promotion_candidate
        or p.has_paper_ready
        or p.has_recent_information
    )


def _protection_for_row(row: dict[str, Any]) -> _ScopeProtection:
    return _ScopeProtection(
        has_promotion_candidate=int(row.get("promotion_candidate_count") or 0) > 0,
        has_paper_ready=int(row.get("paper_ready_count") or 0) > 0,
        has_recent_information=(
            int(row.get("exploratory_pass_count") or 0) > 0
        ),
        candidate_count=int(row.get("promotion_candidate_count") or 0)
        + int(row.get("paper_ready_count") or 0),
    )


def _build_evidence_block(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_count": int(row.get("campaign_count") or 0),
        "repeated_failure_count": int(row.get("rejection_count") or 0),
        "technical_failure_count": int(row.get("technical_failure_count") or 0),
        "information_gain_rate": None,
        "candidate_count": int(row.get("promotion_candidate_count") or 0)
        + int(row.get("paper_ready_count") or 0),
    }


def _decisions_for_hypothesis_row(
    row: dict[str, Any],
) -> list[StopDecision]:
    """All advisory decisions derivable from a single hypothesis-evidence row.

    A row may surface multiple recommendations (e.g. cooldown + review).
    Caller is responsible for de-duplication if it matters at higher
    aggregation levels.
    """
    decisions: list[StopDecision] = []
    protection = _protection_for_row(row)
    preset = str(row.get("preset_name") or "unknown")
    family = str(row.get("strategy_family") or "unknown")
    rejection = int(row.get("rejection_count") or 0)
    technical = int(row.get("technical_failure_count") or 0)
    dominant = row.get("dominant_failure_mode")
    evidence_block = _build_evidence_block(row)

    if technical >= STOP_TECHNICAL_FAILURE_REVIEW:
        decisions.append(
            StopDecision(
                scope_type="preset",
                scope_id=preset,
                recommended_decision=DECISION_REVIEW_REQUIRED,
                severity=SEVERITY_WARNING,
                reason_codes=["repeated_technical_failure"],
                evidence=evidence_block,
            )
        )

    if dominant == INSUFFICIENT_TRADES_REASON and rejection >= STOP_INSUFFICIENT_TRADES_COOLDOWN:
        decisions.append(
            StopDecision(
                scope_type="preset",
                scope_id=preset,
                recommended_decision=DECISION_COOLDOWN,
                severity=SEVERITY_INFO,
                reason_codes=["repeated_insufficient_trades"],
                evidence=evidence_block,
            )
        )

    if rejection >= STOP_REPEAT_REJECTION_FREEZE and not _is_protected(protection):
        decisions.append(
            StopDecision(
                scope_type="preset",
                scope_id=preset,
                recommended_decision=DECISION_FREEZE_PRESET,
                severity=SEVERITY_WARNING,
                reason_codes=["repeated_research_rejection_threshold"],
                evidence=evidence_block,
            )
        )

    if (
        rejection >= STOP_REPEAT_REJECTION_RETIRE
        and not _is_protected(protection)
        and technical < STOP_TECHNICAL_FAILURE_REVIEW
    ):
        # Retire is a stronger recommendation than freeze. Only fires
        # when sustained research rejection is the dominant story AND
        # no candidate evidence protects the scope.
        decisions.append(
            StopDecision(
                scope_type="strategy_family",
                scope_id=family,
                recommended_decision=DECISION_RETIRE_FAMILY,
                severity=SEVERITY_CRITICAL,
                reason_codes=["sustained_research_rejection"],
                evidence=evidence_block,
            )
        )

    return decisions


def _decisions_for_low_information(
    *,
    information_gain_history: list[dict[str, Any]] | None,
) -> list[StopDecision]:
    """REVIEW_REQUIRED when the recent IG window shows no meaningful work.

    Conservative: only triggers once we have at least
    ``STOP_NO_INFO_REVIEW`` samples to look at and *all* of them
    are non-meaningful. Returns a single global-scope decision so
    the operator notices the systemic stall.
    """
    if not information_gain_history:
        return []
    if len(information_gain_history) < STOP_NO_INFO_REVIEW:
        return []
    last_window = information_gain_history[-STOP_NO_INFO_REVIEW:]
    meaningful_count = sum(
        1
        for entry in last_window
        if (entry.get("information_gain") or {}).get("is_meaningful_campaign")
    )
    if meaningful_count > 0:
        return []
    return [
        StopDecision(
            scope_type="hypothesis",
            scope_id="GLOBAL_RECENT_WINDOW",
            recommended_decision=DECISION_REVIEW_REQUIRED,
            severity=SEVERITY_WARNING,
            reason_codes=["no_meaningful_information_in_recent_window"],
            evidence={
                "campaign_count": len(last_window),
                "repeated_failure_count": 0,
                "technical_failure_count": 0,
                "information_gain_rate": 0.0,
                "candidate_count": 0,
            },
        )
    ]


def derive_stop_conditions(
    evidence_ledger: dict[str, Any],
    *,
    information_gain_history: list[dict[str, Any]] | None = None,
) -> list[StopDecision]:
    """Pure derivation: ledger + optional IG history → advisory decisions."""
    decisions: list[StopDecision] = []
    rows = evidence_ledger.get("hypothesis_evidence") or []
    for row in rows:
        decisions.extend(_decisions_for_hypothesis_row(row))
    decisions.extend(
        _decisions_for_low_information(
            information_gain_history=information_gain_history,
        )
    )
    decisions.sort(
        key=lambda d: (
            d.scope_type,
            d.scope_id,
            d.recommended_decision,
        )
    )
    return decisions


def _decision_to_dict(d: StopDecision) -> dict[str, Any]:
    return {
        "scope_type": d.scope_type,
        "scope_id": d.scope_id,
        "recommended_decision": d.recommended_decision,
        "enforcement_state": d.enforcement_state,
        "severity": d.severity,
        "reason_codes": list(d.reason_codes),
        "evidence": dict(d.evidence),
        "cooldown_until_utc": d.cooldown_until_utc,
    }


def build_stop_conditions_payload(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    evidence_ledger: dict[str, Any],
    information_gain_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    decisions = derive_stop_conditions(
        evidence_ledger,
        information_gain_history=information_gain_history,
    )
    return {
        "schema_version": STOP_CONDITIONS_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "enforcement_state": ENFORCEMENT_STATE_ADVISORY,
        "decisions": [_decision_to_dict(d) for d in decisions],
    }


def write_stop_conditions_artifact(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    evidence_ledger: dict[str, Any],
    information_gain_history: list[dict[str, Any]] | None = None,
    output_path: Path = STOP_CONDITIONS_PATH,
) -> dict[str, Any]:
    payload = build_stop_conditions_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        evidence_ledger=evidence_ledger,
        information_gain_history=information_gain_history,
    )
    write_sidecar_atomic(output_path, payload)
    return payload


__all__ = [
    "DECISION_COOLDOWN",
    "DECISION_FREEZE_PRESET",
    "DECISION_NONE",
    "DECISION_RETIRE_FAMILY",
    "DECISION_RETIRE_HYPOTHESIS",
    "DECISION_REVIEW_REQUIRED",
    "ENFORCEMENT_STATE_ADVISORY",
    "INSUFFICIENT_TRADES_REASON",
    "SEVERITY_CRITICAL",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "STOP_CONDITIONS_PATH",
    "STOP_CONDITIONS_SCHEMA_VERSION",
    "STOP_INSUFFICIENT_TRADES_COOLDOWN",
    "STOP_NO_INFO_REVIEW",
    "STOP_REPEAT_REJECTION_FREEZE",
    "STOP_REPEAT_REJECTION_RETIRE",
    "STOP_TECHNICAL_FAILURE_REVIEW",
    "StopDecision",
    "build_stop_conditions_payload",
    "derive_stop_conditions",
    "write_stop_conditions_artifact",
]
