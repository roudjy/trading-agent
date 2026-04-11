import inspect

import numpy as np
import pytest

from research.statistical_defensibility import (
    bootstrap_metric_ci,
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)


def test_psr_deterministic_for_fixed_inputs():
    first = probabilistic_sharpe_ratio(1.2, 120, 0.1, 3.2)
    second = probabilistic_sharpe_ratio(1.2, 120, 0.1, 3.2)

    assert first == second


def test_psr_increases_monotonically_with_n_obs_when_skew_kurt_fixed():
    small_sample = probabilistic_sharpe_ratio(0.8, 30, 0.0, 3.0)
    large_sample = probabilistic_sharpe_ratio(0.8, 120, 0.0, 3.0)

    assert small_sample is not None
    assert large_sample is not None
    assert large_sample > small_sample


def test_psr_handles_zero_or_negative_observed_sharpe():
    zero_sharpe = probabilistic_sharpe_ratio(0.0, 50, 0.0, 3.0)
    negative_sharpe = probabilistic_sharpe_ratio(-0.5, 50, 0.0, 3.0)

    assert zero_sharpe == pytest.approx(0.5)
    assert negative_sharpe is not None
    assert 0.0 <= negative_sharpe < 0.5


def test_dsr_deterministic_for_fixed_inputs():
    first = deflated_sharpe_ratio(1.0, 120, 0.0, 3.0, 12, 0.09)
    second = deflated_sharpe_ratio(1.0, 120, 0.0, 3.0, 12, 0.09)

    assert first == second


def test_dsr_decreases_monotonically_with_n_trials():
    fewer_trials = deflated_sharpe_ratio(1.0, 120, 0.0, 3.0, 4, 0.09)
    more_trials = deflated_sharpe_ratio(1.0, 120, 0.0, 3.0, 40, 0.09)

    assert fewer_trials is not None
    assert more_trials is not None
    assert more_trials < fewer_trials


@pytest.mark.parametrize("n_trials", [None, 0])
def test_dsr_requires_explicit_n_trials(n_trials):
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, 120, 0.0, 3.0, n_trials, 0.09)


def test_bootstrap_metric_ci_reproducible_with_fixed_seed():
    samples = np.array([0.01, -0.02, 0.015, 0.005, -0.01])

    first = bootstrap_metric_ci(samples, np.mean, n_resamples=100, seed=11)
    second = bootstrap_metric_ci(samples, np.mean, n_resamples=100, seed=11)

    assert first == second


def test_bootstrap_metric_ci_uses_default_rng_not_global_state():
    samples = np.array([0.01, -0.02, 0.015, 0.005, -0.01])

    np.random.seed(1)
    first = bootstrap_metric_ci(samples, np.mean, n_resamples=100, seed=17)
    np.random.seed(999)
    second = bootstrap_metric_ci(samples, np.mean, n_resamples=100, seed=17)

    assert first == second


def test_bootstrap_independence_assumption_is_documented():
    """The bootstrap here is IID-with-replacement on daily returns, not block bootstrap."""
    docstring = inspect.getdoc(bootstrap_metric_ci)

    assert docstring is not None
    assert "IID" in docstring
    assert "serial dependence" in docstring


def test_psr_benchmark_sharpe_defaults_to_zero():
    signature = inspect.signature(probabilistic_sharpe_ratio)

    assert signature.parameters["benchmark_sharpe"].default == 0.0
