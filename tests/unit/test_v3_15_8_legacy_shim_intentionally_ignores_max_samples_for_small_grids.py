"""v3.15.8 — INTENTIONAL behavioural shift in the legacy shim.

``screening_param_samples(grid, max_samples=N)`` is preserved for
back-compat as a thin wrapper around ``sampling_plan_for_param_grid``.
For grid_size <= ``MAX_STRATIFIED_GRID_SIZE`` the v3.15.8 sampling
policy applies and ``max_samples`` is intentionally ignored — this
is the deliberate fix for the v3.15.7 under-sampling defect.

This test pins the behavioural shift so a future refactor that
silently re-honours ``max_samples`` for small grids cannot ship.
"""

from __future__ import annotations

import inspect

from research.candidate_pipeline import (
    LEGACY_LARGE_GRID_SAMPLE_COUNT,
    MAX_STRATIFIED_GRID_SIZE,
    screening_param_samples,
)


def test_shim_returns_8_samples_for_grid_8_even_when_max_is_3() -> None:
    samples = screening_param_samples({"a": list(range(8))}, max_samples=3)
    assert len(samples) == 8


def test_shim_returns_full_n_for_n_le_max_full_coverage_grid_size() -> None:
    """For n in [1..8] (full coverage regime) the shim's max_samples
    has no effect — the sampler returns all combinations.
    """
    for n in (1, 2, 3, 5, 8):
        samples = screening_param_samples({"a": list(range(n))}, max_samples=1)
        assert len(samples) == n, (
            f"shim returned {len(samples)} samples for grid_size={n}; "
            f"expected full coverage (n={n})"
        )


def test_shim_returns_stratified_count_for_n_in_9_to_16() -> None:
    """For n in [9..MAX_STRATIFIED_GRID_SIZE] the shim returns the
    deterministic stratified sample count, not max_samples.
    """
    for n in range(9, MAX_STRATIFIED_GRID_SIZE + 1):
        samples = screening_param_samples({"a": list(range(n))}, max_samples=2)
        assert len(samples) >= max(8, int(0.80 * n))
        assert len(samples) <= MAX_STRATIFIED_GRID_SIZE


def test_shim_honours_max_samples_for_legacy_large_grids() -> None:
    """For n > MAX_STRATIFIED_GRID_SIZE the shim still honours
    max_samples (legacy first/middle/last cap).
    """
    samples_default = screening_param_samples({"a": list(range(20))})
    assert len(samples_default) == LEGACY_LARGE_GRID_SAMPLE_COUNT
    samples_capped = screening_param_samples({"a": list(range(20))}, max_samples=2)
    assert len(samples_capped) == 2


def test_shim_signature_unchanged() -> None:
    sig = inspect.signature(screening_param_samples)
    params = list(sig.parameters.keys())
    assert params == ["param_grid", "max_samples"]
    assert sig.parameters["max_samples"].default == LEGACY_LARGE_GRID_SAMPLE_COUNT


def test_shim_returns_list_of_dicts() -> None:
    samples = screening_param_samples({"a": [1, 2]})
    assert isinstance(samples, list)
    for sample in samples:
        assert isinstance(sample, dict)
