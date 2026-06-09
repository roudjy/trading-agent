"""Deterministic QRE tail/entropy hardening scaffold.

This module provides read-only diagnostics for fragile candidate distributions:
tail losses, drawdown concentration, entropy, and single-trade concentration.
It does not promote candidates, register strategies, fetch data, or authorize
paper/shadow/live/broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"


RISK_STATES: tuple[str, ...] = (
    "insufficient_return_data",
    "tail_entropy_clear",
    "tail_entropy_watch",
    "tail_entropy_blocked",
)


@dataclass(frozen=True)
class TailEntropyDiagnostic:
    observation_count: int
    negative_observation_count: int
    worst_observation: float | None
    best_observation: float | None
    mean_observation: float | None
    largest_abs_contribution_share: float | None
    negative_contribution_share: float | None
    sign_entropy_bits: float | None
    risk_state: str
    explanation: str


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_values(values: Iterable[Any]) -> list[float]:
    return [value for raw in values for value in [_to_float(raw)] if value is not None]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _largest_abs_contribution_share(values: list[float]) -> float | None:
    total_abs = sum(abs(value) for value in values)
    if total_abs == 0:
        return 0.0
    return max(abs(value) for value in values) / total_abs


def _negative_contribution_share(values: list[float]) -> float | None:
    total_abs = sum(abs(value) for value in values)
    if total_abs == 0:
        return 0.0
    return sum(abs(value) for value in values if value < 0) / total_abs


def _sign_entropy_bits(values: list[float]) -> float | None:
    if not values:
        return None

    positive_count = sum(1 for value in values if value > 0)
    negative_count = sum(1 for value in values if value < 0)
    zero_count = sum(1 for value in values if value == 0)
    total = positive_count + negative_count + zero_count
    if total == 0:
        return None

    entropy = 0.0
    for count in (positive_count, negative_count, zero_count):
        if count == 0:
            continue
        probability = count / total
        entropy -= probability * log2(probability)
    return entropy


def diagnose_tail_entropy(
    observations: Iterable[Any],
    *,
    min_observations: int = 5,
    max_single_abs_share: float = 0.50,
    max_negative_abs_share: float = 0.70,
    min_sign_entropy_bits: float = 0.70,
) -> TailEntropyDiagnostic:
    """Diagnose tail/entropy fragility for a sequence of numeric observations.

    Favorable diagnostics are context only and never authorize promotion or execution.
    """

    values = _numeric_values(observations)
    observation_count = len(values)
    negative_count = sum(1 for value in values if value < 0)

    worst = min(values) if values else None
    best = max(values) if values else None
    average = _mean(values)
    largest_share = _largest_abs_contribution_share(values) if values else None
    negative_share = _negative_contribution_share(values) if values else None
    entropy = _sign_entropy_bits(values)

    if observation_count < min_observations:
        risk_state = "insufficient_return_data"
        explanation = "Not enough numeric observations to assess tail/entropy fragility."
    elif (
        largest_share is not None
        and negative_share is not None
        and entropy is not None
        and (
            largest_share > max_single_abs_share
            or negative_share > max_negative_abs_share
            or entropy < min_sign_entropy_bits
        )
    ):
        risk_state = "tail_entropy_blocked"
        explanation = "Tail/entropy concentration exceeds configured hardening thresholds."
    elif (
        largest_share is not None
        and negative_share is not None
        and entropy is not None
        and (
            largest_share > max_single_abs_share * 0.8
            or negative_share > max_negative_abs_share * 0.8
            or entropy < min_sign_entropy_bits * 1.2
        )
    ):
        risk_state = "tail_entropy_watch"
        explanation = "Tail/entropy concentration is near configured thresholds."
    else:
        risk_state = "tail_entropy_clear"
        explanation = "Tail/entropy diagnostics are within configured context-only thresholds."

    return TailEntropyDiagnostic(
        observation_count=observation_count,
        negative_observation_count=negative_count,
        worst_observation=worst,
        best_observation=best,
        mean_observation=average,
        largest_abs_contribution_share=largest_share,
        negative_contribution_share=negative_share,
        sign_entropy_bits=entropy,
        risk_state=risk_state,
        explanation=explanation,
    )


def tail_entropy_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "risk_states": list(RISK_STATES),
        "authority": {
            "tail_entropy_diagnostics_are_context_only": True,
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