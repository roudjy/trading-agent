"""v3.15.8 — grid introspection in ``sampling_plan_for_param_grid``.

Pins the closed table from REV 3 §5.3:

    None / non-dict       -> grid_size_unavailable, [{}]
    malformed expansion   -> grid_size_unavailable, [{}]
    {}                    -> empty_grid, [{}], coverage 1.0
    1..8                  -> full_coverage, all combos
    9..16                 -> stratified_small, coverage >= 0.80
    > 16                  -> legacy_large_grid, first/middle/last
"""

from __future__ import annotations

import pytest

from research.candidate_pipeline import (
    COVERAGE_WARNING_GRID_UNAVAILABLE,
    MAX_FULL_COVERAGE_GRID_SIZE,
    MAX_STRATIFIED_GRID_SIZE,
    MIN_STRATIFIED_COVERAGE_PCT,
    SAMPLING_POLICY_EMPTY_GRID,
    SAMPLING_POLICY_FULL_COVERAGE,
    SAMPLING_POLICY_GRID_UNAVAILABLE,
    SAMPLING_POLICY_LEGACY_LARGE_GRID,
    SAMPLING_POLICY_STRATIFIED_SMALL,
    sampling_plan_for_param_grid,
)


def _grid_of(size: int, key: str = "p") -> dict[str, list[int]]:
    """Single-axis grid producing ``size`` combinations."""
    return {key: list(range(size))}


def test_none_input_yields_grid_size_unavailable() -> None:
    plan = sampling_plan_for_param_grid(None)
    assert plan.grid_size is None
    assert plan.coverage_pct is None
    assert plan.sampling_policy == SAMPLING_POLICY_GRID_UNAVAILABLE
    assert plan.coverage_warning == COVERAGE_WARNING_GRID_UNAVAILABLE
    assert plan.samples == [{}]
    assert plan.sampled_count == 1


def test_non_dict_input_yields_grid_size_unavailable() -> None:
    plan = sampling_plan_for_param_grid("not a dict")  # type: ignore[arg-type]
    assert plan.grid_size is None
    assert plan.sampling_policy == SAMPLING_POLICY_GRID_UNAVAILABLE


def test_malformed_axis_yields_grid_size_unavailable() -> None:
    """A non-iterable parameter value crashes ``itertools.product``;
    the planner traps it and returns a fallback rather than letting
    the screening loop crash on a bad config row.
    """
    plan = sampling_plan_for_param_grid({"a": 5})  # 5 is not iterable
    assert plan.grid_size is None
    assert plan.sampling_policy == SAMPLING_POLICY_GRID_UNAVAILABLE
    assert plan.coverage_warning == COVERAGE_WARNING_GRID_UNAVAILABLE


def test_all_empty_axes_yields_grid_size_unavailable() -> None:
    plan = sampling_plan_for_param_grid({"a": []})
    assert plan.grid_size is None
    assert plan.sampling_policy == SAMPLING_POLICY_GRID_UNAVAILABLE


def test_empty_dict_is_empty_grid() -> None:
    plan = sampling_plan_for_param_grid({})
    assert plan.grid_size == 1
    assert plan.sampled_count == 1
    assert plan.coverage_pct == 1.0
    assert plan.sampling_policy == SAMPLING_POLICY_EMPTY_GRID
    assert plan.coverage_warning is None
    assert plan.samples == [{}]


@pytest.mark.parametrize("size", list(range(1, MAX_FULL_COVERAGE_GRID_SIZE + 1)))
def test_full_coverage_for_grids_up_to_8(size: int) -> None:
    plan = sampling_plan_for_param_grid(_grid_of(size))
    assert plan.grid_size == size
    assert plan.sampled_count == size
    assert plan.coverage_pct == 1.0
    assert plan.sampling_policy == SAMPLING_POLICY_FULL_COVERAGE
    assert plan.coverage_warning is None


@pytest.mark.parametrize("size", list(range(MAX_FULL_COVERAGE_GRID_SIZE + 1, MAX_STRATIFIED_GRID_SIZE + 1)))
def test_stratified_for_grids_9_to_16(size: int) -> None:
    plan = sampling_plan_for_param_grid(_grid_of(size))
    assert plan.grid_size == size
    assert plan.sampling_policy == SAMPLING_POLICY_STRATIFIED_SMALL
    assert plan.coverage_pct is not None
    assert plan.coverage_pct >= MIN_STRATIFIED_COVERAGE_PCT
    # endpoints always included
    assert plan.samples[0] == {"p": 0}
    assert plan.samples[-1] == {"p": size - 1}


def test_legacy_for_grids_above_16_keeps_first_middle_last() -> None:
    size = 17
    plan = sampling_plan_for_param_grid(_grid_of(size))
    assert plan.grid_size == size
    assert plan.sampling_policy == SAMPLING_POLICY_LEGACY_LARGE_GRID
    assert plan.sampled_count == 3
    assert plan.coverage_warning is None
    # first / middle / last
    assert plan.samples[0] == {"p": 0}
    assert plan.samples[1] == {"p": size // 2}
    assert plan.samples[-1] == {"p": size - 1}


def test_legacy_large_grid_64_combinations() -> None:
    plan = sampling_plan_for_param_grid(_grid_of(64))
    assert plan.grid_size == 64
    assert plan.sampling_policy == SAMPLING_POLICY_LEGACY_LARGE_GRID
    assert plan.sampled_count == 3


def test_legacy_max_samples_kwarg_is_honoured_only_for_large_grids() -> None:
    plan_small = sampling_plan_for_param_grid(_grid_of(8), max_samples_for_legacy=2)
    assert plan_small.sampled_count == 8  # full coverage; max ignored
    plan_large = sampling_plan_for_param_grid(_grid_of(20), max_samples_for_legacy=2)
    assert plan_large.sampled_count == 2  # legacy cap honoured
