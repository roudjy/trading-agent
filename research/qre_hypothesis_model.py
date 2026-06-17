"""Generic QRE hypothesis object model.

The hypothesis model is a research-intelligence foundation only. It is
not strategy authority, not candidate authority, and not deployment
authority. It can be schema-validated and scored against the canonical
behavior catalog, but it does not authorize execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Iterable, Literal, Mapping

from research.qre_behavior_catalog import get_behavior_family, list_behavior_families


HypothesisStatus = Literal[
    "draft",
    "research_ready",
    "evidence_incomplete",
    "evidence_complete",
    "rejected",
    "suppressed",
    "deprecated",
]

HYPOTHESIS_MODEL_SCHEMA_VERSION: Final[str] = "1.0"
HYPOTHESIS_STATUS_VALUES: Final[tuple[str, ...]] = (
    "draft",
    "research_ready",
    "evidence_incomplete",
    "evidence_complete",
    "rejected",
    "suppressed",
    "deprecated",
)
EXECUTION_AUTHORITATIVE_STATUSES: Final[frozenset[str]] = frozenset()


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    behavior_id: str
    title: str
    description: str
    universe_ref: str | None = None
    universe_description: str | None = None
    symbols: tuple[str, ...] = ()
    preset_id: str | None = None
    timeframe: str | None = None
    expected_mechanism: str = ""
    expected_observables: tuple[str, ...] = ()
    falsification_criteria: tuple[str, ...] = ()
    required_evidence_types: tuple[str, ...] = ()
    required_data_capabilities: tuple[str, ...] = ()
    known_risks: tuple[str, ...] = ()
    status: HypothesisStatus = "draft"
    created_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    reason_record_refs: tuple[str, ...] = ()
    scope_hash: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "behavior_id": self.behavior_id,
            "title": self.title,
            "description": self.description,
            "universe_ref": self.universe_ref,
            "universe_description": self.universe_description,
            "symbols": list(self.symbols),
            "preset_id": self.preset_id,
            "timeframe": self.timeframe,
            "expected_mechanism": self.expected_mechanism,
            "expected_observables": list(self.expected_observables),
            "falsification_criteria": list(self.falsification_criteria),
            "required_evidence_types": list(self.required_evidence_types),
            "required_data_capabilities": list(self.required_data_capabilities),
            "known_risks": list(self.known_risks),
            "status": self.status,
            "created_at_utc": self.created_at_utc.isoformat(),
            "source": self.source,
            "reason_record_refs": list(self.reason_record_refs),
            "scope_hash": self.scope_hash,
        }


@dataclass(frozen=True)
class HypothesisValidationResult:
    valid: bool
    status: str
    scope_hash: str
    rejection_reasons: tuple[str, ...] = ()
    behavior_known: bool = False
    execution_authoritative: bool = False
    strategy_authority: bool = False
    candidate_authority: bool = False
    deployment_authority: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "status": self.status,
            "scope_hash": self.scope_hash,
            "rejection_reasons": list(self.rejection_reasons),
            "behavior_known": self.behavior_known,
            "execution_authoritative": self.execution_authoritative,
            "strategy_authority": self.strategy_authority,
            "candidate_authority": self.candidate_authority,
            "deployment_authority": self.deployment_authority,
        }


def _iso_or_blank(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _canonical_payload(hypothesis: Hypothesis | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(hypothesis, Hypothesis):
        payload = hypothesis.to_payload()
    else:
        payload = dict(hypothesis)
        symbols = payload.get("symbols")
        if isinstance(symbols, tuple):
            payload["symbols"] = list(symbols)
        if isinstance(payload.get("created_at_utc"), datetime):
            payload["created_at_utc"] = _iso_or_blank(payload["created_at_utc"])
        if isinstance(payload.get("reason_record_refs"), tuple):
            payload["reason_record_refs"] = list(payload["reason_record_refs"])
        if isinstance(payload.get("expected_observables"), tuple):
            payload["expected_observables"] = list(payload["expected_observables"])
        if isinstance(payload.get("falsification_criteria"), tuple):
            payload["falsification_criteria"] = list(payload["falsification_criteria"])
        if isinstance(payload.get("required_evidence_types"), tuple):
            payload["required_evidence_types"] = list(payload["required_evidence_types"])
        if isinstance(payload.get("required_data_capabilities"), tuple):
            payload["required_data_capabilities"] = list(payload["required_data_capabilities"])
        if isinstance(payload.get("known_risks"), tuple):
            payload["known_risks"] = list(payload["known_risks"])
    payload.setdefault("created_at_utc", "")
    payload.setdefault("scope_hash", "")
    return {
        key: payload.get(key)
        for key in (
            "hypothesis_id",
            "behavior_id",
            "title",
            "description",
            "universe_ref",
            "universe_description",
            "symbols",
            "preset_id",
            "timeframe",
            "expected_mechanism",
            "expected_observables",
            "falsification_criteria",
            "required_evidence_types",
            "required_data_capabilities",
            "known_risks",
            "status",
            "created_at_utc",
            "source",
            "reason_record_refs",
        )
    }


def compute_hypothesis_scope_hash(hypothesis: Hypothesis | Mapping[str, Any]) -> str:
    payload = _canonical_payload(hypothesis)
    if isinstance(payload.get("created_at_utc"), datetime):
        payload["created_at_utc"] = _iso_or_blank(payload["created_at_utc"])
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def validate_hypothesis(
    hypothesis: Hypothesis | Mapping[str, Any],
    *,
    provisional_behavior_ids: Iterable[str] = (),
) -> HypothesisValidationResult:
    payload = _canonical_payload(hypothesis)
    behavior_id = str(payload.get("behavior_id") or "").strip()
    status = str(payload.get("status") or "").strip()
    rejection_reasons: list[str] = []
    provisional_set = frozenset(str(item) for item in provisional_behavior_ids)

    if not behavior_id:
        rejection_reasons.append("missing_behavior_id")
    else:
        known_behavior = behavior_id in {item.behavior_id for item in list_behavior_families()}
        if not known_behavior and behavior_id not in provisional_set:
            rejection_reasons.append("unknown_behavior_id")

    if status not in HYPOTHESIS_STATUS_VALUES:
        rejection_reasons.append("unknown_status")

    if not str(payload.get("title") or "").strip():
        rejection_reasons.append("missing_title")

    if not str(payload.get("description") or "").strip():
        rejection_reasons.append("missing_description")

    if status == "research_ready" and not tuple(payload.get("falsification_criteria") or ()):
        rejection_reasons.append("missing_falsification_criteria")

    if status == "evidence_complete" and not tuple(payload.get("reason_record_refs") or ()):
        rejection_reasons.append("missing_accepted_evidence_refs")

    if status == "evidence_complete" and behavior_id and behavior_id not in provisional_set:
        try:
            get_behavior_family(behavior_id)
        except KeyError:
            rejection_reasons.append("unknown_behavior_id")

    scope_hash = compute_hypothesis_scope_hash(payload)
    execution_authoritative = status in EXECUTION_AUTHORITATIVE_STATUSES
    valid = not rejection_reasons
    return HypothesisValidationResult(
        valid=valid,
        status=status or "unknown",
        scope_hash=scope_hash,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        behavior_known=bool(behavior_id) and (
            behavior_id in {item.behavior_id for item in list_behavior_families()}
            or behavior_id in provisional_set
        ),
        execution_authoritative=execution_authoritative,
        strategy_authority=False,
        candidate_authority=False,
        deployment_authority=False,
    )
