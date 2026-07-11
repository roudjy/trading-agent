"""Governed multi-window evidence closure for offline QRE replay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from packages.qre_research import governed_offline_artifacts as artifacts
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import single_dataset_offline_replay as replay

WindowName = Literal["in_sample", "out_of_sample", "null_model", "cost_model", "trade_count", "data_quality"]
WindowStatus = Literal["missing", "failed", "passed", "not_applicable"]
ClosureDisposition = Literal["evidence_closed_for_offline_memory", "blocked_missing_evidence", "rejected_negative_evidence"]

REQUIRED_WINDOWS: Final[tuple[WindowName, ...]] = (
    "in_sample",
    "out_of_sample",
    "null_model",
    "cost_model",
    "trade_count",
    "data_quality",
)
MISSING_WINDOW_REASON_CODES: Final[dict[WindowName, str]] = {
    "in_sample": reasons.RejectionReasonCode.INSUFFICIENT_DATA.value,
    "out_of_sample": reasons.RejectionReasonCode.OOS_NOT_AVAILABLE.value,
    "null_model": reasons.RejectionReasonCode.EVIDENCE_INCOMPLETE.value,
    "cost_model": reasons.RejectionReasonCode.EVIDENCE_INCOMPLETE.value,
    "trade_count": reasons.RejectionReasonCode.INSUFFICIENT_TRADES.value,
    "data_quality": reasons.RejectionReasonCode.INSUFFICIENT_DATA.value,
}
FAILED_WINDOW_REASON_CODES: Final[dict[WindowName, str]] = {
    "in_sample": reasons.RejectionReasonCode.SCREENING_CRITERIA_NOT_MET.value,
    "out_of_sample": reasons.RejectionReasonCode.SCREENING_CRITERIA_NOT_MET.value,
    "null_model": reasons.RejectionReasonCode.NULL_MODEL_NOT_BEATEN.value,
    "cost_model": reasons.RejectionReasonCode.COST_MODEL_FAILED.value,
    "trade_count": reasons.RejectionReasonCode.INSUFFICIENT_TRADES.value,
    "data_quality": reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value,
}


@dataclass(frozen=True, slots=True)
class EvidenceWindow:
    name: WindowName
    status: WindowStatus
    reason_codes: tuple[str, ...]
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class MultiwindowEvidenceClosure:
    closure_id: str
    replay_id: str
    evidence_windows: tuple[EvidenceWindow, ...]
    evidence_complete: bool
    disposition: ClosureDisposition
    reason_records: tuple[reasons.ReasonRecord, ...]
    memory_feedback_records: tuple[dict[str, object], ...]
    artifact_envelope: dict[str, object]
    artifact_path: Path
    latest_path: Path
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "closure_id": self.closure_id,
            "replay_id": self.replay_id,
            "evidence_windows": [window.as_dict() for window in self.evidence_windows],
            "evidence_complete": self.evidence_complete,
            "disposition": self.disposition,
            "reason_records": [record.as_dict() for record in self.reason_records],
            "memory_feedback_records": list(self.memory_feedback_records),
            "artifact_envelope": dict(self.artifact_envelope),
            "artifact_path": self.artifact_path.as_posix(),
            "latest_path": self.latest_path.as_posix(),
            "safety": dict(self.safety),
        }


def _next_action(name: WindowName, status: WindowStatus) -> str:
    if status == "missing":
        return f"collect_{name}_evidence"
    if status == "failed":
        return f"review_{name}_failure"
    return "retain_window_evidence"


def _window(name: WindowName, status: WindowStatus) -> EvidenceWindow:
    if status == "missing":
        reason_codes = (MISSING_WINDOW_REASON_CODES[name],)
    elif status == "failed":
        reason_codes = (FAILED_WINDOW_REASON_CODES[name],)
    else:
        reason_codes = ()
    return EvidenceWindow(name=name, status=status, reason_codes=reason_codes, next_action=_next_action(name, status))


def _reason_records(
    closure_id: str,
    windows: tuple[EvidenceWindow, ...],
) -> tuple[reasons.ReasonRecord, ...]:
    records: list[reasons.ReasonRecord] = []
    for window in windows:
        for code in window.reason_codes:
            records.append(
                reasons.make_reason_record(
                    code=code,
                    stage=f"EvidenceWindow:{window.name}",
                    object_id=closure_id,
                    explanation=f"Governed offline evidence window {window.name} is {window.status}.",
                    next_action=window.next_action,
                    terminal=window.status == "failed",
                )
            )
    return tuple(records)


def _disposition(windows: tuple[EvidenceWindow, ...]) -> ClosureDisposition:
    if any(window.status == "failed" for window in windows):
        return "rejected_negative_evidence"
    if any(window.status == "missing" for window in windows):
        return "blocked_missing_evidence"
    return "evidence_closed_for_offline_memory"


def run_multiwindow_evidence_closure(
    *,
    closure_id: str,
    replay_result: replay.SingleDatasetReplayResult,
    window_statuses: dict[WindowName, WindowStatus],
    artifact_dir: Path,
) -> MultiwindowEvidenceClosure:
    windows = tuple(_window(name, window_statuses.get(name, "missing")) for name in REQUIRED_WINDOWS)
    reason_records = _reason_records(closure_id, windows)
    missing_codes = tuple(
        code
        for window in windows
        for code in window.reason_codes
        if reasons.reason_polarity(code) == "missing_evidence"
    )
    negative_codes = tuple(
        code
        for window in windows
        for code in window.reason_codes
        if reasons.reason_polarity(code) == "negative_evidence"
    )
    disposition = _disposition(windows)
    envelope = dict(replay_result.artifact_envelope)
    envelope["run_id"] = closure_id
    evidence_pack = dict(envelope["evidence_pack"])
    evidence_pack["complete"] = disposition == "evidence_closed_for_offline_memory"
    evidence_pack["evidence_windows"] = [window.as_dict() for window in windows]
    evidence_pack["missing_evidence"] = sorted(set(evidence_pack["missing_evidence"]) | set(missing_codes))
    evidence_pack["negative_evidence"] = sorted(set(evidence_pack["negative_evidence"]) | set(negative_codes))
    evidence_pack["null_model_beaten"] = _field_status(windows, "null_model")
    evidence_pack["cost_model_passed"] = _field_status(windows, "cost_model")
    evidence_pack["trade_count"] = _field_status(windows, "trade_count")
    envelope["evidence_pack"] = evidence_pack
    envelope["disposition"] = {
        "decision": disposition,
        "reasons": sorted({code for record in reason_records for code in (record.code,)}),
        "next_action": "advance_to_memory_feedback" if evidence_pack["complete"] else "resolve_evidence_windows",
    }
    feedback = tuple(reasons.feedback_memory_payload(record) for record in reason_records)
    envelope["memory_feedback"] = {
        "lessons": [record["lesson_memory"] for record in feedback],
        "suppressions": list(replay_result.artifact_envelope["memory_feedback"]["suppressions"]),
        "prioritization_hints": list(replay_result.artifact_envelope["memory_feedback"]["prioritization_hints"]),
    }
    run_path, latest_path = artifacts.write_artifact(envelope, artifact_dir)
    return MultiwindowEvidenceClosure(
        closure_id=closure_id,
        replay_id=replay_result.replay_id,
        evidence_windows=windows,
        evidence_complete=bool(evidence_pack["complete"]),
        disposition=disposition,
        reason_records=reason_records,
        memory_feedback_records=feedback,
        artifact_envelope=envelope,
        artifact_path=run_path,
        latest_path=latest_path,
        safety={
            "offline_only": True,
            "runtime_behavior_changed": False,
            "strategy_synthesis_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
            "broker_authority": False,
            "risk_authority": False,
            "order_authority": False,
            "capital_allocation_authority": False,
        },
    )


def _field_status(windows: tuple[EvidenceWindow, ...], name: WindowName) -> str:
    return next(window.status for window in windows if window.name == name)


def closure_reason_distribution(closures: tuple[MultiwindowEvidenceClosure, ...]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for closure in closures:
        for record in closure.reason_records:
            distribution[record.code] = distribution.get(record.code, 0) + 1
    return distribution


__all__ = [
    "EvidenceWindow",
    "MultiwindowEvidenceClosure",
    "REQUIRED_WINDOWS",
    "closure_reason_distribution",
    "run_multiwindow_evidence_closure",
]
