from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017o-2026-06-26"

COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "thesis_readiness",
    "data_readiness",
    "signal_density",
    "behavior_orthogonality",
    "prior_failure_risk",
    "null_control_feasibility",
    "regime_coverage",
    "historical_evidence",
    "information_gain",
    "compute_efficiency",
)

COMPONENT_AVAILABILITY_VALUES: Final[tuple[str, ...]] = (
    "present",
    "missing",
    "blocked",
    "derived_proxy",
)

PRIORITY_BAND_VALUES: Final[tuple[str, ...]] = (
    "blocked",
    "low",
    "medium",
    "high",
)

COMPONENT_WEIGHTS: Final[dict[str, float]] = {
    "thesis_readiness": 0.16,
    "data_readiness": 0.14,
    "signal_density": 0.10,
    "behavior_orthogonality": 0.08,
    "prior_failure_risk": 0.12,
    "null_control_feasibility": 0.10,
    "regime_coverage": 0.08,
    "historical_evidence": 0.10,
    "information_gain": 0.06,
    "compute_efficiency": 0.06,
}


def bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return round(number, 6)


def canonical_component_scores(
    scores: Mapping[str, Any] | None,
) -> dict[str, float]:
    source = scores or {}
    return {
        name: bounded_float(source.get(name, 0.0))
        for name in COMPONENT_NAMES
    }


def weighted_opportunity_score(scores: Mapping[str, Any] | None) -> float:
    canonical = canonical_component_scores(scores)
    total = sum(
        canonical[name] * COMPONENT_WEIGHTS[name]
        for name in COMPONENT_NAMES
    )
    return round(bounded_float(total), 6)


def priority_band(
    score: Any,
    *,
    blocked: bool = False,
) -> str:
    bounded = bounded_float(score)
    if blocked:
        return "blocked"
    if bounded >= 0.70:
        return "high"
    if bounded >= 0.40:
        return "medium"
    return "low"
