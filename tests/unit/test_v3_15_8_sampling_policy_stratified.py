"""v3.15.8 — deterministic stratified sampling for grids 9..16.

Pins:
  - byte-identical sample list across repeated calls,
  - stable indices independent of dict insertion order,
  - >= MIN_STRATIFIED_COVERAGE_PCT coverage by construction,
  - first and last combinations always included,
  - cap of MAX_STRATIFIED_GRID_SIZE samples never exceeded.
"""

from __future__ import annotations

import pytest

from research.candidate_pipeline import (
    MAX_FULL_COVERAGE_GRID_SIZE,
    MAX_STRATIFIED_GRID_SIZE,
    MIN_STRATIFIED_COVERAGE_PCT,
    SAMPLING_POLICY_STRATIFIED_SMALL,
    _stratified_indices,
    sampling_plan_for_param_grid,
)


@pytest.mark.parametrize(
    "size",
    list(range(MAX_FULL_COVERAGE_GRID_SIZE + 1, MAX_STRATIFIED_GRID_SIZE + 1)),
)
def test_stratified_indices_meet_coverage_floor(size: int) -> None:
    indices = _stratified_indices(size)
    assert len(indices) / size >= MIN_STRATIFIED_COVERAGE_PCT
    assert indices == sorted(indices)
    assert len(indices) <= MAX_STRATIFIED_GRID_SIZE
    # endpoints always present
    assert indices[0] == 0
    assert indices[-1] == size - 1


def test_stratified_indices_are_byte_identical_across_calls() -> None:
    for size in range(MAX_FULL_COVERAGE_GRID_SIZE + 1, MAX_STRATIFIED_GRID_SIZE + 1):
        first = _stratified_indices(size)
        for _ in range(5):
            assert _stratified_indices(size) == first


def test_stratified_plan_is_dict_insertion_order_independent() -> None:
    """Hash-randomness immunity: regardless of input dict key
    insertion order the samples list is byte-identical because
    keys are sorted before ``itertools.product``.
    """
    plan_a = sampling_plan_for_param_grid({"a": [1, 2, 3], "b": [10, 20, 30, 40]})
    plan_b = sampling_plan_for_param_grid({"b": [10, 20, 30, 40], "a": [1, 2, 3]})
    assert plan_a.samples == plan_b.samples
    assert plan_a.sampled_parameter_digest == plan_b.sampled_parameter_digest


def test_stratified_plan_for_2x6_grid_is_stratified_small() -> None:
    plan = sampling_plan_for_param_grid({"a": [1, 2], "b": list(range(6))})
    assert plan.grid_size == 12
    assert plan.sampling_policy == SAMPLING_POLICY_STRATIFIED_SMALL
    assert plan.coverage_pct is not None and plan.coverage_pct >= MIN_STRATIFIED_COVERAGE_PCT
