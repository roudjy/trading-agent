from __future__ import annotations

import pytest

from packages.qre_research.memory_aware_hypothesis_generation import (
    MemoryAwareGenerationError,
    prioritize_hypothesis_batch,
)


def _hypotheses() -> list[dict[str, object]]:
    return [
        {"hypothesis_id": "h1", "feature_family": "momentum", "base_priority": 0.5},
        {"hypothesis_id": "h2", "feature_family": "defensive", "base_priority": 0.6},
        {"hypothesis_id": "h3", "feature_family": "breakout", "base_priority": 0.4},
    ]


def test_memory_absent_produces_stable_baseline_ordering() -> None:
    first = prioritize_hypothesis_batch(_hypotheses())
    second = prioritize_hypothesis_batch(_hypotheses())

    assert first == second
    assert [row["hypothesis_id"] for row in first["hypotheses"]] == ["h2", "h1", "h3"]
    assert first["memory_applied_count"] == 0


def test_negative_lesson_memory_suppresses_matching_family() -> None:
    memory = {"lessons": [{"do_not_repeat_families": ["defensive"]}]}

    view = prioritize_hypothesis_batch(_hypotheses(), memory)

    defensive = next(row for row in view["hypotheses"] if row["hypothesis_family"] == "defensive")
    assert defensive["suppressed"] is True
    assert defensive["memory_reason"] == "negative_lesson_memory"


def test_positive_or_near_pass_feedback_increases_priority_without_certifying_alpha() -> None:
    memory = {"lessons": [{"near_pass_families": ["breakout"]}]}

    view = prioritize_hypothesis_batch(_hypotheses(), memory)
    breakout = next(row for row in view["hypotheses"] if row["hypothesis_family"] == "breakout")

    assert breakout["memory_action"] == "boost"
    assert breakout["final_priority"] > breakout["base_priority"]
    assert view["safety"]["strategy_synthesis_authority"] is False


def test_duplicate_prior_hypothesis_can_be_suppressed() -> None:
    memory = {"feedback_records": [{"hypothesis_family": "momentum", "feedback_decision": "reject_for_now"}]}

    view = prioritize_hypothesis_batch(_hypotheses(), memory)
    momentum = next(row for row in view["hypotheses"] if row["hypothesis_family"] == "momentum")

    assert momentum["suppressed"] is True
    assert momentum["memory_action"] == "suppress"


def test_dead_zone_memory_reduces_priority() -> None:
    memory = {"lessons": [{"dead_zone_families": ["momentum"]}]}

    view = prioritize_hypothesis_batch(_hypotheses(), memory)
    momentum = next(row for row in view["hypotheses"] if row["hypothesis_family"] == "momentum")

    assert momentum["memory_action"] == "deprioritize"
    assert momentum["final_priority"] < momentum["base_priority"]


def test_contradictory_memory_creates_warning() -> None:
    memory = {"contradictions": ["family_supported_and_rejected"]}

    view = prioritize_hypothesis_batch(_hypotheses(), memory)

    assert view["warnings"] == ["contradictory_memory:family_supported_and_rejected"]


def test_provider_leakage_is_blocked() -> None:
    with pytest.raises(MemoryAwareGenerationError, match="provider_leakage"):
        prioritize_hypothesis_batch([{"hypothesis_id": "h", "feature_family": "tiingo_momentum"}])


def test_no_hidden_stochasticity_or_execution_authority() -> None:
    view = prioritize_hypothesis_batch(_hypotheses(), {"lessons": [{"near_pass_families": ["breakout"]}]})

    assert view == prioritize_hypothesis_batch(_hypotheses(), {"lessons": [{"near_pass_families": ["breakout"]}]})
    safety = view["safety"]
    assert safety["stochastic_selector"] is False
    assert safety["creates_candidates"] is False
    assert safety["creates_strategies"] is False
    assert safety["runs_screening"] is False
    assert safety["trading_authority"] is False
