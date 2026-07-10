"""Canonical QRE rejection and blocking reason records.

The taxonomy is provider-agnostic and research-only. It explains why a
candidate or funnel object is blocked without running campaigns, creating
strategies, or granting execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

ReasonSeverity = Literal["info", "warning", "blocking", "terminal"]
EvidencePolarity = Literal["missing_evidence", "negative_evidence", "governance_rejection", "policy_rejection"]


class RejectionReasonCode(StrEnum):
    INSUFFICIENT_DATA = "insufficient_data"
    INSUFFICIENT_TRADES = "insufficient_trades"
    DATA_QUALITY_FAILED = "data_quality_failed"
    SOURCE_IDENTITY_UNRESOLVED = "source_identity_unresolved"
    PROVIDER_SCOPE_VIOLATION = "provider_scope_violation"
    DUPLICATE_HYPOTHESIS = "duplicate_hypothesis"
    DUPLICATE_ACTIVE_RESEARCH_PATH = "duplicate_active_research_path"
    MISSING_FALSIFICATION_CRITERIA = "missing_falsification_criteria"
    MISSING_EXPECTED_OBSERVABLES = "missing_expected_observables"
    PRIMITIVE_MISSING = "primitive_missing"
    STRATEGY_MAPPING_FAILED = "strategy_mapping_failed"
    PRESET_BOUNDS_INVALID = "preset_bounds_invalid"
    CAMPAIGN_BUDGET_EXCEEDED = "campaign_budget_exceeded"
    NULL_MODEL_NOT_BEATEN = "null_model_not_beaten"
    COST_MODEL_FAILED = "cost_model_failed"
    OOS_NOT_AVAILABLE = "oos_not_available"
    SCREENING_CRITERIA_NOT_MET = "screening_criteria_not_met"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    MATURITY_GATE_FAILED = "maturity_gate_failed"
    ARCHITECTURE_GATE_FAILED = "architecture_gate_failed"
    OPERATOR_DECISION_REQUIRED = "operator_decision_required"
    POLICY_DENIED = "policy_denied"


CANONICAL_REASON_CODES: Final[tuple[str, ...]] = tuple(code.value for code in RejectionReasonCode)
PROVIDER_SPECIFIC_TERMS: Final[tuple[str, ...]] = (
    "alpaca",
    "binance",
    "coinbase",
    "kraken",
    "tiingo",
    "yfinance",
)
GOVERNANCE_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        RejectionReasonCode.MATURITY_GATE_FAILED.value,
        RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value,
        RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value,
        RejectionReasonCode.POLICY_DENIED.value,
    }
)
MISSING_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        RejectionReasonCode.INSUFFICIENT_DATA.value,
        RejectionReasonCode.INSUFFICIENT_TRADES.value,
        RejectionReasonCode.OOS_NOT_AVAILABLE.value,
        RejectionReasonCode.EVIDENCE_INCOMPLETE.value,
        RejectionReasonCode.MISSING_FALSIFICATION_CRITERIA.value,
        RejectionReasonCode.MISSING_EXPECTED_OBSERVABLES.value,
    }
)
NEGATIVE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        RejectionReasonCode.DATA_QUALITY_FAILED.value,
        RejectionReasonCode.NULL_MODEL_NOT_BEATEN.value,
        RejectionReasonCode.COST_MODEL_FAILED.value,
        RejectionReasonCode.SCREENING_CRITERIA_NOT_MET.value,
    }
)


@dataclass(frozen=True, slots=True)
class ReasonRecord:
    code: str
    stage: str
    object_id: str
    severity: ReasonSeverity
    explanation: str
    next_action: str
    evidence_polarity: EvidencePolarity
    terminal: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stage": self.stage,
            "object_id": self.object_id,
            "severity": self.severity,
            "explanation": self.explanation,
            "next_action": self.next_action,
            "evidence_polarity": self.evidence_polarity,
            "terminal": self.terminal,
        }


def reason_polarity(code: str) -> EvidencePolarity:
    if code in MISSING_EVIDENCE_CODES:
        return "missing_evidence"
    if code in NEGATIVE_EVIDENCE_CODES:
        return "negative_evidence"
    if code in GOVERNANCE_REASON_CODES:
        return "governance_rejection" if code != RejectionReasonCode.POLICY_DENIED.value else "policy_rejection"
    return "missing_evidence"


def validate_reason_record(record: ReasonRecord) -> list[str]:
    errors: list[str] = []
    if record.code not in CANONICAL_REASON_CODES:
        errors.append(f"unknown_reason_code:{record.code}")
    if not record.stage:
        errors.append("missing_stage")
    if not record.object_id:
        errors.append("missing_object_id")
    if not record.explanation:
        errors.append("missing_explanation")
    if not record.next_action:
        errors.append("missing_next_action")
    lowered = " ".join((record.code, record.explanation, record.next_action)).lower()
    leaked = [term for term in PROVIDER_SPECIFIC_TERMS if term in lowered]
    errors.extend(f"provider_specific_reason_leakage:{term}" for term in leaked)
    expected_polarity = reason_polarity(record.code)
    if record.evidence_polarity != expected_polarity:
        errors.append(f"reason_polarity_mismatch:{record.code}:{record.evidence_polarity}:{expected_polarity}")
    return errors


def make_reason_record(
    *,
    code: str,
    stage: str,
    object_id: str,
    explanation: str,
    next_action: str,
    severity: ReasonSeverity = "blocking",
    terminal: bool = False,
) -> ReasonRecord:
    record = ReasonRecord(
        code=code,
        stage=stage,
        object_id=object_id,
        severity=severity,
        explanation=explanation,
        next_action=next_action,
        evidence_polarity=reason_polarity(code),
        terminal=terminal,
    )
    errors = validate_reason_record(record)
    if errors:
        raise ValueError(";".join(errors))
    return record


def feedback_memory_payload(record: ReasonRecord) -> dict[str, object]:
    return {
        "feedback_record": record.as_dict(),
        "lesson_memory": {
            "object_id": record.object_id,
            "stage": record.stage,
            "reason_code": record.code,
            "failure_mode": record.evidence_polarity,
            "next_action": record.next_action,
        },
        "research_memory": {
            "suppress_if_unchanged": record.terminal,
            "requires_changed_condition": record.code
            in {
                RejectionReasonCode.DUPLICATE_HYPOTHESIS.value,
                RejectionReasonCode.DUPLICATE_ACTIVE_RESEARCH_PATH.value,
                RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value,
                RejectionReasonCode.POLICY_DENIED.value,
            },
            "canonical_reason_code": record.code,
        },
    }


def validate_reason_taxonomy() -> list[str]:
    errors: list[str] = []
    if len(CANONICAL_REASON_CODES) != len(set(CANONICAL_REASON_CODES)):
        errors.append("duplicate_reason_code")
    for code in CANONICAL_REASON_CODES:
        if any(term in code for term in PROVIDER_SPECIFIC_TERMS):
            errors.append(f"provider_specific_reason_code:{code}")
    return errors


__all__ = [
    "CANONICAL_REASON_CODES",
    "GOVERNANCE_REASON_CODES",
    "MISSING_EVIDENCE_CODES",
    "NEGATIVE_EVIDENCE_CODES",
    "PROVIDER_SPECIFIC_TERMS",
    "ReasonRecord",
    "RejectionReasonCode",
    "feedback_memory_payload",
    "make_reason_record",
    "reason_polarity",
    "validate_reason_record",
    "validate_reason_taxonomy",
]
