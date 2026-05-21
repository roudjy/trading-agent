"""Deterministic closed-form opportunity scoring.

The score is expected research value, not alpha certainty, prediction
probability, promotion authority, or execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from reporting import reason_records as _rr


SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"

ACTIVE_DIAGNOSTICS: Final[tuple[str, ...]] = (
    "null_model",
    "tail_asymmetry",
    "entropy_structure",
)

DEFAULT_TAIL_FILTER_THRESHOLD: Final[float] = 0.75
DEFAULT_ENTROPY_FILTER_THRESHOLD: Final[float] = 0.75
DEFAULT_NULL_BEAT_MARGIN_THRESHOLD: Final[float] = 0.05
DEFAULT_EVIDENCE_QUORUM_MAX: Final[int] = 3
DEFAULT_MULTIPLICITY_BUDGET_MAX: Final[int] = 10

COMPONENT_WEIGHTS: Final[dict[str, float]] = {
    "null_model": 0.30,
    "tail_asymmetry": 0.20,
    "entropy_structure": 0.20,
    "evidence_quorum": 0.15,
    "preset_feasibility": 0.10,
    "multiplicity_budget": 0.05,
}

SCORING_DECISIONS: Final[tuple[str, ...]] = _rr.DECISIONS_BY_KIND["scoring"]


@dataclass(frozen=True)
class OpportunityScore:
    hypothesis_id: str
    decision: str
    opportunity_probability_score: float
    reason_codes: tuple[str, ...]
    reason_text: str
    components: dict[str, float]
    scoring_reason_record_id: str
    inputs_digest: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "opportunity_probability_score": (
                self.opportunity_probability_score
            ),
            "reason_codes": list(self.reason_codes),
            "reason_text": self.reason_text,
            "components": dict(sorted(self.components.items())),
            "scoring_reason_record_id": self.scoring_reason_record_id,
            "inputs_digest": self.inputs_digest,
        }


def _bounded_float(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    f = float(value)
    if f != f:
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _bounded_int(value: Any, *, maximum: int) -> int:
    if not isinstance(value, int):
        return 0
    if value < 0:
        return 0
    if value > maximum:
        return maximum
    return value


def normalise_inputs(
    diagnostics: Mapping[str, Any] | None,
    *,
    preset_feasible: bool,
) -> dict[str, object]:
    src = diagnostics or {}
    null_margin = _bounded_float(src.get("null_model_beat_margin"))
    tail_fragility = _bounded_float(src.get("tail_fragility_score"))
    entropy_conflict = _bounded_float(src.get("entropy_conflict_score"))
    quorum_count = _bounded_int(
        src.get("evidence_quorum_count"),
        maximum=DEFAULT_EVIDENCE_QUORUM_MAX,
    )
    budget_remaining = _bounded_int(
        src.get("multiplicity_budget_remaining"),
        maximum=DEFAULT_MULTIPLICITY_BUDGET_MAX,
    )
    return {
        "null_model_beat_margin": null_margin,
        "tail_fragility_score": tail_fragility,
        "entropy_conflict_score": entropy_conflict,
        "evidence_quorum_count": quorum_count,
        "multiplicity_budget_remaining": budget_remaining,
        "preset_feasible": bool(preset_feasible),
    }


def score_components(inputs: Mapping[str, object]) -> dict[str, float]:
    quorum = (
        int(inputs["evidence_quorum_count"])
        / float(DEFAULT_EVIDENCE_QUORUM_MAX)
    )
    budget = (
        int(inputs["multiplicity_budget_remaining"])
        / float(DEFAULT_MULTIPLICITY_BUDGET_MAX)
    )
    return {
        "null_model": _bounded_float(inputs["null_model_beat_margin"]),
        "tail_asymmetry": 1.0 - _bounded_float(
            inputs["tail_fragility_score"]
        ),
        "entropy_structure": 1.0 - _bounded_float(
            inputs["entropy_conflict_score"]
        ),
        "evidence_quorum": _bounded_float(quorum),
        "preset_feasibility": 1.0 if inputs["preset_feasible"] else 0.0,
        "multiplicity_budget": _bounded_float(budget),
    }


def opportunity_probability_score(inputs: Mapping[str, object]) -> float:
    components = score_components(inputs)
    raw = sum(
        components[name] * COMPONENT_WEIGHTS[name]
        for name in sorted(COMPONENT_WEIGHTS)
    )
    return round(_bounded_float(raw), 6)


def _decision_for(inputs: Mapping[str, object]) -> tuple[str, tuple[str, ...], str]:
    if not inputs["preset_feasible"]:
        return (
            "filter_cost",
            ("cost_gate_fail",),
            "No stable enabled preset resolves for this hypothesis.",
        )
    if (
        _bounded_float(inputs["null_model_beat_margin"])
        < DEFAULT_NULL_BEAT_MARGIN_THRESHOLD
    ):
        return (
            "filter_null",
            ("null_p_value_above_threshold",),
            "Null-model beat margin is below the discovery threshold.",
        )
    if (
        _bounded_float(inputs["tail_fragility_score"])
        >= DEFAULT_TAIL_FILTER_THRESHOLD
    ):
        return (
            "filter_tail",
            ("tail_fragility_high",),
            "Left-tail fragility is above the discovery threshold.",
        )
    if (
        _bounded_float(inputs["entropy_conflict_score"])
        >= DEFAULT_ENTROPY_FILTER_THRESHOLD
    ):
        return (
            "filter_entropy",
            ("entropy_regime_incompatible",),
            "Entropy structure is incompatible with the behavior premise.",
        )
    return (
        "keep",
        (
            "null_p_value_below_threshold",
            "tail_fragility_low",
            "entropy_regime_compatible",
            "cost_gate_pass",
        ),
        "All active diagnostics pass as filters; proposal seed may be emitted.",
    )


def score_opportunity(
    hypothesis_id: str,
    diagnostics: Mapping[str, Any] | None,
    *,
    preset_feasible: bool,
    frozen_utc: str,
) -> OpportunityScore:
    inputs = normalise_inputs(diagnostics, preset_feasible=preset_feasible)
    components = score_components(inputs)
    score = opportunity_probability_score(inputs)
    decision, reason_codes, reason_text = _decision_for(inputs)
    reason_inputs = {
        "hypothesis_id": hypothesis_id,
        "active_diagnostics": list(ACTIVE_DIAGNOSTICS),
        "inputs": inputs,
        "components": dict(sorted(components.items())),
        "component_weights": dict(sorted(COMPONENT_WEIGHTS.items())),
        "score_semantics": "expected_research_value_not_probability",
    }
    record = _rr.build_record(
        decision_kind=_rr.DECISION_KIND_SCORING,
        subject_id=hypothesis_id,
        decision=decision,
        reason_codes=reason_codes,
        reason_text=reason_text,
        inputs=reason_inputs,
        frozen_utc=frozen_utc,
    )
    return OpportunityScore(
        hypothesis_id=hypothesis_id,
        decision=decision,
        opportunity_probability_score=score,
        reason_codes=reason_codes,
        reason_text=reason_text,
        components=components,
        scoring_reason_record_id=record["record_id"],
        inputs_digest=record["inputs_digest"],
    )
