"""Bridge campaign or screening evidence into canonical memory contracts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 1
PROVIDER_TERMS: Final[tuple[str, ...]] = ("tiingo", "yfinance", "alpaca", "binance", "kraken", "coinbase")
NEGATIVE_DECISIONS: Final[frozenset[str]] = frozenset({"screening_fail", "null_not_beaten", "blocked_unsafe_input"})
SAFETY: Final[dict[str, bool]] = {
    "research_only": True,
    "memory_only": True,
    "creates_candidates": False,
    "creates_strategies": False,
    "creates_presets": False,
    "creates_campaigns": False,
    "runs_campaign": False,
    "runs_screening": False,
    "promotes_candidates": False,
    "trading_authority": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}


class EvidenceMemoryBridgeError(ValueError):
    """Raised when evidence cannot be safely canonicalized."""


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _required(payload: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "", [])]
    if missing:
        raise EvidenceMemoryBridgeError("missing_required_fields:" + ",".join(missing))


def _assert_no_provider_leakage(payload: Any, path: tuple[str, ...] = ()) -> None:
    if "provenance" in path:
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if any(term in str(key).lower() for term in PROVIDER_TERMS):
                raise EvidenceMemoryBridgeError("provider_leakage:" + ".".join((*path, str(key))))
            _assert_no_provider_leakage(value, (*path, str(key)))
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            _assert_no_provider_leakage(value, (*path, str(index)))
        return
    if any(term in str(payload).lower() for term in PROVIDER_TERMS):
        raise EvidenceMemoryBridgeError("provider_leakage:" + ".".join(path))


def evidence_pack_from_screening_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Create canonical EvidencePack from a screening or campaign result."""

    _required(result, ("screening_result_id", "candidate_id", "decision", "metrics"))
    _assert_no_provider_leakage(result)
    evidence_refs = [str(result["screening_result_id"])]
    payload = {
        "canonical_name": "EvidencePack",
        "schema_version": SCHEMA_VERSION,
        "evidence_pack_id": "epack_" + _digest({"screening": result["screening_result_id"], "metrics": result["metrics"]}),
        "campaign_run_id": result.get("campaign_run_id", "campaign_run_not_executed"),
        "screening_result_refs": evidence_refs,
        "decision_basis": {
            "screening_decision": result["decision"],
            "metrics": result["metrics"],
            "null_control": result.get("null_control", {}),
            "negative_result_preserved": result["decision"] in NEGATIVE_DECISIONS,
            "contradictions": list(result.get("contradictions") or []),
        },
        "diagnostics_refs": list(result.get("diagnostics_refs") or []),
        "ledger_refs": [],
        "provenance": {"candidate_id": result["candidate_id"], "screening_result_id": result["screening_result_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def evidence_ledger_entry_from_screening_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Create a canonical EvidenceLedger entry from a screening result."""

    pack = evidence_pack_from_screening_result(result)
    decision = str(result["decision"])
    evidence_decision = {
        "screening_pass": "retain_research_evidence",
        "null_not_beaten": "weak_research_evidence",
        "screening_fail": "weak_research_evidence",
        "insufficient_evidence": "insufficient_research_evidence",
        "blocked_unsafe_input": "blocked_research_evidence",
    }.get(decision, "insufficient_research_evidence")
    payload = {
        "canonical_name": "EvidenceLedger",
        "schema_version": SCHEMA_VERSION,
        "evidence_id": "evid_" + _digest({"pack": pack["evidence_pack_id"], "decision": evidence_decision}),
        "evidence_kind": "canonical_screening_evidence",
        "metrics_digest": "sha256:" + _digest(result["metrics"]),
        "evidence_decision": evidence_decision,
        "metrics_summary": dict(result["metrics"]),
        "null_control_summary": dict(result.get("null_control", {})),
        "audit_flags": dict(SAFETY),
        "provenance": {"evidence_pack_id": pack["evidence_pack_id"], "screening_result_id": result["screening_result_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def disposition_from_evidence_pack(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    """Create deterministic Disposition from canonical EvidencePack."""

    _required(evidence_pack, ("canonical_name", "evidence_pack_id", "decision_basis"))
    if evidence_pack.get("canonical_name") != "EvidencePack":
        raise EvidenceMemoryBridgeError("not_evidence_pack")
    _assert_no_provider_leakage(evidence_pack)
    basis = evidence_pack["decision_basis"]
    if not isinstance(basis, Mapping):
        raise EvidenceMemoryBridgeError("invalid_decision_basis")
    screening_decision = str(basis.get("screening_decision") or "insufficient_evidence")
    disposition = {
        "screening_pass": "retain_for_more_research",
        "null_not_beaten": "modify_or_deprioritize",
        "screening_fail": "reject_for_now",
        "insufficient_evidence": "needs_more_evidence",
        "blocked_unsafe_input": "block_until_repaired",
    }.get(screening_decision, "needs_more_evidence")
    payload = {
        "canonical_name": "Disposition",
        "schema_version": SCHEMA_VERSION,
        "disposition_id": "disp_" + _digest({"pack": evidence_pack["evidence_pack_id"], "decision": disposition}),
        "evidence_pack_id": evidence_pack["evidence_pack_id"],
        "decision": disposition,
        "reason_codes": [screening_decision],
        "next_actions": ["write_feedback_record"],
        "operator_notes": [],
        "provenance": {"evidence_pack_id": evidence_pack["evidence_pack_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def feedback_record_from_disposition(disposition: Mapping[str, Any]) -> dict[str, Any]:
    """Create canonical FeedbackRecord from a valid Disposition."""

    _required(disposition, ("canonical_name", "disposition_id", "decision", "evidence_pack_id"))
    if disposition.get("canonical_name") != "Disposition":
        raise EvidenceMemoryBridgeError("not_disposition")
    _assert_no_provider_leakage(disposition)
    decision = str(disposition["decision"])
    next_action = {
        "retain_for_more_research": "retain_hypothesis_family",
        "modify_or_deprioritize": "modify_hypothesis_parameters_later",
        "reject_for_now": "suppress_matching_candidate_family",
        "needs_more_evidence": "collect_more_data",
        "block_until_repaired": "repair_input_contract",
    }.get(decision, "collect_more_data")
    payload = {
        "canonical_name": "FeedbackRecord",
        "schema_version": SCHEMA_VERSION,
        "feedback_id": "fb_" + _digest({"disposition": disposition["disposition_id"], "decision": decision}),
        "subject_id": disposition["evidence_pack_id"],
        "feedback_decision": decision,
        "next_action": next_action,
        "feedback_reasons": list(disposition.get("reason_codes") or []),
        "consumable_by_next_run": True,
        "provenance": {"disposition_id": disposition["disposition_id"], "evidence_pack_id": disposition["evidence_pack_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def lesson_memory_from_feedback_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compress feedback records into deterministic LessonMemory."""

    if not records:
        raise EvidenceMemoryBridgeError("missing_feedback_records")
    for record in records:
        _required(record, ("canonical_name", "feedback_id", "feedback_decision", "next_action"))
        if record.get("canonical_name") != "FeedbackRecord":
            raise EvidenceMemoryBridgeError("not_feedback_record")
        _assert_no_provider_leakage(record)
    counts = Counter(str(record["feedback_decision"]) for record in records)
    negative = [record["feedback_id"] for record in records if record["feedback_decision"] in {"reject_for_now", "modify_or_deprioritize"}]
    payload = {
        "canonical_name": "LessonMemory",
        "schema_version": SCHEMA_VERSION,
        "lesson_id": "lesson_" + _digest({"feedback": [record["feedback_id"] for record in records], "counts": dict(counts)}),
        "disposition_id": str(records[-1].get("provenance", {}).get("disposition_id", "multiple_dispositions")),
        "lesson_type": "research_feedback_summary",
        "do_not_repeat": list(negative),
        "generator_constraints": ["preserve_negative_results", "explain_memory_influence"],
        "recommended_next_question": "Use canonical feedback before proposing adjacent hypotheses.",
        "provenance": {"feedback_ids": [record["feedback_id"] for record in records]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def research_memory_from_lessons(lessons: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Create read-only ResearchMemory from LessonMemory records."""

    if not lessons:
        raise EvidenceMemoryBridgeError("missing_lesson_memory")
    for lesson in lessons:
        _required(lesson, ("canonical_name", "lesson_id", "do_not_repeat"))
        if lesson.get("canonical_name") != "LessonMemory":
            raise EvidenceMemoryBridgeError("not_lesson_memory")
        _assert_no_provider_leakage(lesson)
    payload = {
        "canonical_name": "ResearchMemory",
        "schema_version": SCHEMA_VERSION,
        "research_memory_id": "rmem_" + _digest({"lessons": [lesson["lesson_id"] for lesson in lessons]}),
        "lesson_refs": [lesson["lesson_id"] for lesson in lessons],
        "feedback_refs": [feedback_id for lesson in lessons for feedback_id in lesson.get("provenance", {}).get("feedback_ids", [])],
        "terminal_outcomes": [],
        "active_contradictions": [],
        "provenance": {"lesson_count": len(lessons)},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


__all__ = [
    "EvidenceMemoryBridgeError",
    "SAFETY",
    "disposition_from_evidence_pack",
    "evidence_ledger_entry_from_screening_result",
    "evidence_pack_from_screening_result",
    "feedback_record_from_disposition",
    "lesson_memory_from_feedback_records",
    "research_memory_from_lessons",
]
